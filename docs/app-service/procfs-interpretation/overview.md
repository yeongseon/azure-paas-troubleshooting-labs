---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-11
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# procfs Interpretation on App Service Linux

!!! success "Status: Published"

## 1. Question

How reliable is `/proc` filesystem data inside an App Service Linux container, and what are the known interpretation limits when comparing procfs values with Azure Monitor metrics?

## 2. Why this matters

Support engineers and developers frequently use procfs (`/proc/meminfo`, `/proc/stat`, `/proc/loadavg`) to diagnose issues on App Service Linux. However, the values reported by procfs inside a container may reflect the host, the cgroup, or the container depending on the kernel version, cgroup version (v1 vs. v2), and how the App Service sandbox is configured.

Misinterpreting procfs data leads to incorrect memory or CPU conclusions — for example, seeing 32GB total memory in `/proc/meminfo` on a B1 plan with 1.75GB allocated.

## 3. Customer symptom

"The memory/CPU values I read from /proc don't match Azure Monitor" or "My app shows 32GB total memory but the plan only has 1.75GB."

## 4. Hypothesis

When diagnosing App Service Linux containers, procfs values can be partially host-scoped while cgroup files are quota-scoped. For memory and CPU limits, cgroup values will align more closely with plan constraints and Azure Monitor than raw procfs totals.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1, P1v3, P2v3 |
| Region | Korea Central |
| Runtime | Python 3.11, Node.js 20 |
| OS | Linux |
| Date tested | 2026-04-11 |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- App Service SKU/plan
- Runtime (Python, Node.js)
- Cgroup version exposure

**Observed:**

- `/proc/meminfo` values vs. cgroup memory limits
- `/proc/stat` CPU values vs. cgroup CPU quota
- `/proc/loadavg` vs. Azure Monitor CPU percentage
- Discrepancies between procfs, cgroup, and Azure Monitor

## 7. Instrumentation

- App Service SSH session for procfs and cgroup reads
- Application logs capturing periodic snapshots of `/proc/*` and cgroup files
- Azure Monitor metrics for CPU percentage, memory working set, and instance counters
- Kudu/Log Stream for runtime logs and timestamp alignment
- Azure CLI queries for app configuration and plan metadata

## 8. Procedure

### 8.1 Infrastructure setup

Create one resource group in `koreacentral`, three Linux App Service plans (`B1`, `P1v3`, `P1mv3`), and two web apps per SKU (Python 3.11 and Node.js 20).

```bash
RG="rg-procfs-lab"
LOCATION="koreacentral"

PLAN_B1="plan-procfs-b1"
PLAN_P1V3="plan-procfs-p1v3"
PLAN_P1MV3="plan-procfs-p1mv3"

APP_PY_B1="app-procfs-py-b1"
APP_NODE_B1="app-procfs-node-b1"
APP_PY_P1V3="app-procfs-py-p1v3"
APP_NODE_P1V3="app-procfs-node-p1v3"
APP_PY_P1MV3="app-procfs-py-p1mv3"
APP_NODE_P1MV3="app-procfs-node-p1mv3"

az group create --name "$RG" --location "$LOCATION"

az appservice plan create --resource-group "$RG" --name "$PLAN_B1" --location "$LOCATION" --is-linux --sku B1
az appservice plan create --resource-group "$RG" --name "$PLAN_P1V3" --location "$LOCATION" --is-linux --sku P1v3
az appservice plan create --resource-group "$RG" --name "$PLAN_P1MV3" --location "$LOCATION" --is-linux --sku P1mv3

az webapp create --resource-group "$RG" --plan "$PLAN_B1" --name "$APP_PY_B1" --runtime "PYTHON|3.11"
az webapp create --resource-group "$RG" --plan "$PLAN_B1" --name "$APP_NODE_B1" --runtime "NODE|20-lts"

az webapp create --resource-group "$RG" --plan "$PLAN_P1V3" --name "$APP_PY_P1V3" --runtime "PYTHON|3.11"
az webapp create --resource-group "$RG" --plan "$PLAN_P1V3" --name "$APP_NODE_P1V3" --runtime "NODE|20-lts"

az webapp create --resource-group "$RG" --plan "$PLAN_P1MV3" --name "$APP_PY_P1MV3" --runtime "PYTHON|3.11"
az webapp create --resource-group "$RG" --plan "$PLAN_P1MV3" --name "$APP_NODE_P1MV3" --runtime "NODE|20-lts"
```

### 8.2 Application code

Use minimal apps exposing `GET /procinfo`, returning procfs fields and cgroup limits in JSON. Implement cgroup v1/v2 fallback so results are comparable across worker images.

```python
from flask import Flask, jsonify
from pathlib import Path

app = Flask(__name__)


def read_text(path):
    p = Path(path)
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def read_first_existing(paths):
    for path in paths:
        value = read_text(path)
        if value is not None:
            return value
    return None


def parse_meminfo():
    fields = {"MemTotal": None, "MemFree": None, "MemAvailable": None}
    content = read_text("/proc/meminfo") or ""
    for line in content.splitlines():
        for key in fields:
            if line.startswith(f"{key}:"):
                fields[key] = line.split(":", 1)[1].strip()
    return fields


@app.get("/procinfo")
def procinfo():
    stat_line = (read_text("/proc/stat") or "").splitlines()
    return jsonify(
        {
            "meminfo": parse_meminfo(),
            "proc_stat_first_line": stat_line[0] if stat_line else None,
            "proc_loadavg": read_text("/proc/loadavg"),
            "cgroup_memory_limit": read_first_existing(
                [
                    "/sys/fs/cgroup/memory/memory.limit_in_bytes",
                    "/sys/fs/cgroup/memory.max",
                ]
            ),
            "cgroup_cpu_quota": read_first_existing(
                [
                    "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
                    "/sys/fs/cgroup/cpu.max",
                ]
            ),
        }
    )
```

```javascript
const express = require("express");
const fs = require("fs");

const app = express();

function readText(path) {
    try {
        return fs.readFileSync(path, "utf8").trim();
    } catch {
        return null;
    }
}

function readFirstExisting(paths) {
    for (const path of paths) {
        const value = readText(path);
        if (value !== null) {
            return value;
        }
    }
    return null;
}

function parseMeminfo() {
    const result = { MemTotal: null, MemFree: null, MemAvailable: null };
    const content = readText("/proc/meminfo") || "";
    for (const line of content.split("\n")) {
        for (const key of Object.keys(result)) {
            if (line.startsWith(`${key}:`)) {
                result[key] = line.split(":")[1].trim();
            }
        }
    }
    return result;
}

app.get("/procinfo", (_req, res) => {
    const stat = (readText("/proc/stat") || "").split("\n");
    res.json({
        meminfo: parseMeminfo(),
        proc_stat_first_line: stat[0] || null,
        proc_loadavg: readText("/proc/loadavg"),
        cgroup_memory_limit: readFirstExisting([
            "/sys/fs/cgroup/memory/memory.limit_in_bytes",
            "/sys/fs/cgroup/memory.max"
        ]),
        cgroup_cpu_quota: readFirstExisting([
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
            "/sys/fs/cgroup/cpu.max"
        ])
    });
});
```

### 8.3 Deploy

Deploy each app using `az webapp up` from its runtime folder (zip deployment path), then confirm HTTP 200 from `/procinfo`.

```bash
RG="rg-procfs-lab"
LOCATION="koreacentral"

# Python apps (run in Python app folder)
az webapp up --name "$APP_PY_B1" --resource-group "$RG" --runtime "PYTHON:3.11" --location "$LOCATION"
az webapp up --name "$APP_PY_P1V3" --resource-group "$RG" --runtime "PYTHON:3.11" --location "$LOCATION"
az webapp up --name "$APP_PY_P1MV3" --resource-group "$RG" --runtime "PYTHON:3.11" --location "$LOCATION"

# Node.js apps (run in Node.js app folder)
az webapp up --name "$APP_NODE_B1" --resource-group "$RG" --runtime "NODE:20-lts" --location "$LOCATION"
az webapp up --name "$APP_NODE_P1V3" --resource-group "$RG" --runtime "NODE:20-lts" --location "$LOCATION"
az webapp up --name "$APP_NODE_P1MV3" --resource-group "$RG" --runtime "NODE:20-lts" --location "$LOCATION"
```

### 8.4 Test execution

This is a config interpretation experiment (no load generation). For each SKU x runtime app (`6` total), collect five samples at one-minute intervals and align each sample to manual SSH reads.

```bash
RG="rg-procfs-lab"
APP_NAME="$APP_PY_B1"  # Replace per target app

for run in 1 2 3 4 5; do
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  curl --silent "https://${APP_NAME}.azurewebsites.net/procinfo"
  sleep 60
done
```

For each timestamp window, open SSH for the same app and capture matching raw values:

```bash
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable"
head -n 1 /proc/stat
cat /proc/loadavg
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us
cat /sys/fs/cgroup/cpu.max
```

At the same timestamps, export Azure Monitor metrics (`CpuPercentage`, memory working set) so endpoint output, SSH snapshots, and platform telemetry can be compared on one timeline.

### 8.5 Data collection

Build a comparison table per app and timestamp with these columns:

- `Procfs MemTotal` from `/proc/meminfo`
- `Cgroup memory limit` from cgroup file
- `Expected plan memory` from SKU reference
- `/proc/stat` first line fields
- `Cgroup CPU quota`
- Azure Monitor `CpuPercentage`
- Azure Monitor memory working set

Use Azure Monitor metric queries for each app to pull CPU and memory values for the exact sample window:

```bash
RG="rg-procfs-lab"
APP_NAME="$APP_PY_B1"
APP_ID=$(az webapp show --resource-group "$RG" --name "$APP_NAME" --query id --output tsv)

az monitor metrics list --resource "$APP_ID" --metric "CpuPercentage" --interval "PT1M"
az monitor metrics list --resource "$APP_ID" --metric "MemoryWorkingSet" --interval "PT1M"
```

Interpretation focus: whether cgroup limits track SKU constraints and Azure Monitor more consistently than raw procfs totals.

### 8.6 Cleanup

Delete the entire lab resource group after data export and note capture are complete.

```bash
RG="rg-procfs-lab"
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- `/proc/meminfo` `MemTotal` may reflect host-visible memory and not strict plan memory quota
- Cgroup memory limit files are expected to map to SKU constraints more directly than procfs totals
- CPU quota behavior is expected to be clearer in cgroup controls than in aggregate `/proc/stat` values
- Azure Monitor trends should correlate better with quota-scoped metrics than with host-scoped procfs fields

## 10. Results

### Memory: procfs vs cgroup vs SKU specification

| SKU | SKU Spec Memory | `/proc/meminfo` MemTotal | Cgroup Memory Limit | Cgroup Memory Usage (avg) | Azure Monitor MemoryWorkingSet (avg) |
|-----|-----------------|--------------------------|---------------------|---------------------------|--------------------------------------|
| B1  | 1.75 GB         | 1,900,180 kB (~1.81 GB)  | 9,223,372,036,854,771,712 (unlimited) | ~71 MB | ~66 MB |
| P1v3 | 8 GB           | 8,088,104 kB (~7.71 GB)  | 9,223,372,036,854,771,712 (unlimited) | ~66 MB | ~65 MB |
| P2v3 | 16 GB          | 16,328,612 kB (~15.57 GB) | 9,223,372,036,854,771,712 (unlimited) | ~67 MB | ~67 MB |

!!! warning "Key finding: cgroup memory limit is NOT enforced"
    The cgroup `memory.limit_in_bytes` returned `9223372036854771712` (2^63 − 1, effectively unlimited) on **all three SKUs**. This means cgroup memory files do NOT reflect the App Service plan quota. The memory limit is enforced at a different layer (sandbox/hypervisor), not via cgroup.

### Memory: procfs MemTotal vs SKU specification

| SKU | SKU Spec | MemTotal | Ratio | Interpretation |
|-----|----------|----------|-------|----------------|
| B1  | 1.75 GB  | 1.81 GB  | 1.03× | Close match — MemTotal reflects allocated VM/sandbox |
| P1v3 | 8 GB    | 7.71 GB  | 0.96× | Close match — small overhead for OS/kernel |
| P2v3 | 16 GB   | 15.57 GB | 0.97× | Close match — consistent overhead pattern |

!!! tip "procfs MemTotal is usable as a rough SKU indicator"
    Unlike cgroup limits (which are unlimited), `/proc/meminfo` `MemTotal` tracks the SKU specification within ~3-5% and can be used to identify the allocated VM size.

### CPU: procfs vs cgroup vs Azure Monitor

| SKU | SKU Spec vCPU | Cgroup CPU Quota | Cgroup CPU Period | Azure Monitor CpuPercentage (avg) | `/proc/loadavg` 1-min (avg) |
|-----|---------------|------------------|-------------------|-----------------------------------|-----------------------------|
| B1  | 1             | -1 (unlimited)   | 100,000 µs        | 80.6%                             | 17.73                       |
| P1v3 | 2            | -1 (unlimited)   | 100,000 µs        | 6.6%                              | 0.33                        |
| P2v3 | 4            | -1 (unlimited)   | 100,000 µs        | 3.1%                              | 0.23                        |

!!! warning "Key finding: cgroup CPU quota is also NOT enforced"
    `cpu.cfs_quota_us` returned `-1` (unlimited) on all SKUs. CPU throttling on App Service Linux is not implemented via cgroup CPU quota.

### Azure Monitor MemoryPercentage (plan-level)

| Plan | MemoryPercentage (stable avg) | Interpretation |
|------|-------------------------------|----------------|
| B1   | 73%                           | High — B1 has limited memory, baseline OS + app uses most of it |
| P1v3 | 27%                           | Moderate — 8 GB plan with light workload |
| P2v3 | 15%                           | Low — 16 GB plan with same workload |

### Sample comparison: cgroup usage vs Azure Monitor MemoryWorkingSet

| SKU | Cgroup `memory.usage_in_bytes` (avg) | Azure Monitor `MemoryWorkingSet` (avg) | Difference |
|-----|--------------------------------------|----------------------------------------|------------|
| B1  | 71.3 MB                              | 66.4 MB                                | ~5 MB      |
| P1v3 | 65.8 MB                             | 65.3 MB                                | ~0.5 MB    |
| P2v3 | 67.4 MB                             | 66.9 MB                                | ~0.5 MB    |

Cgroup `memory.usage_in_bytes` and Azure Monitor `MemoryWorkingSet` show close alignment (within 5 MB). Both reflect the app process working set, not the total VM memory.

## 11. Interpretation

1. **procfs exposes VM-level memory, not plan-level quota.** `/proc/meminfo` `MemTotal` reflects the underlying VM size **[Observed]**, which closely matches the SKU specification **[Measured]** (within ~3-5%). It does NOT show cgroup or sandbox memory limits **[Observed]**.

2. **Cgroup memory and CPU limits are set to unlimited.** Both `memory.limit_in_bytes` and `cpu.cfs_quota_us` return their maximum/unlimited values **[Measured]**. App Service Linux does not use cgroup v1 limits to enforce plan quotas **[Observed]**. Resource enforcement happens at the sandbox/hypervisor layer, invisible to the container **[Inferred]**.

3. **Cgroup memory _usage_ is accurate.** While the cgroup _limit_ is meaningless, `memory.usage_in_bytes` closely tracks Azure Monitor's `MemoryWorkingSet` metric **[Measured]** (within 5 MB), making it a reliable indicator of actual app memory consumption **[Inferred]**.

4. **`/proc/loadavg` shows host-level load, not container load.** The B1 plan showed load averages of 8-30 with a single-vCPU plan **[Measured]**, indicating load from co-tenants on the shared host **[Inferred]**. Premium plans (dedicated hosts) showed expected low load values **[Measured]**.

5. **Azure Monitor plan-level metrics are the only reliable source for quota-relative measurements.** `CpuPercentage` and `MemoryPercentage` at the plan level are computed by the platform and correctly reflect usage relative to the plan's allocated resources **[Inferred]**.

## 12. What this proves

!!! success "Evidence-based conclusions"

    1. `/proc/meminfo` `MemTotal` is a reasonable proxy for the VM size allocated to the plan **[Measured]** (within 3-5% of SKU spec).
    2. Cgroup `memory.usage_in_bytes` tracks Azure Monitor `MemoryWorkingSet` **[Measured]** within ~5 MB.
    3. Cgroup memory and CPU _limits_ are **not** enforced via cgroup on App Service Linux **[Observed]** — they return unlimited values **[Measured]**.
    4. `/proc/loadavg` on shared plans (B1) reflects host-level contention **[Observed]**, not container-specific load.
    5. For quota-relative metrics, only Azure Monitor plan-level `CpuPercentage` and `MemoryPercentage` are reliable **[Inferred]**.

## 13. What this does NOT prove

- This does not prove that cgroup limits are _never_ enforced — future App Service worker images or cgroup v2 migrations could change this behavior.
- This does not prove that `/proc/meminfo` will always match SKU specs — shared plans may show different values under different host configurations.
- This does not test OOM-kill behavior — even though cgroup limits are unlimited, the sandbox may kill processes that exceed plan memory through other mechanisms.
- Node.js runtime was not validated in this run due to deployment issues — procfs behavior may vary by runtime container image.

## 14. Support takeaway

!!! tip "For support engineers"
    When a customer reports that their container shows 8 GB or 16 GB total memory on a B1 plan, check what tool they're using:

    - **`/proc/meminfo` `MemTotal`** — This should actually show ~1.81 GB on B1, matching the VM size. If it shows much more, they may be on a different plan than they think.
    - **`free` command** — Uses `/proc/meminfo` under the hood, same caveats apply.
    - **Cgroup `memory.limit_in_bytes`** — This shows ~8 EB (unlimited). Do NOT use this to determine plan quota.
    - **Azure Monitor `MemoryPercentage`** — This is the **only reliable** way to see how much of the plan quota is used.

    For CPU diagnostics:

    - **`/proc/loadavg`** on shared plans (B-tier) may show high values from co-tenant load. This is **misleading** for container-specific CPU analysis.
    - **Azure Monitor `CpuPercentage`** at the plan level is the reliable metric.
    - **Cgroup `cpu.cfs_quota_us` = -1** means unlimited — do NOT conclude that the container has unlimited CPU.

## 15. Reproduction notes

- Capture procfs and cgroup snapshots at fixed intervals so timestamps align with Azure Monitor granularity.
- Validate container instance restarts before each run to avoid mixing old and new process contexts.
- Record the exact SKU and runtime because procfs presentation can vary by worker image generation.
- Keep load profile stable during collection to isolate interpretation differences from workload effects.

## 16. Related guide / official docs

- [Microsoft Learn: App Service Linux containers](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
- [cgroup v1 memory documentation](https://www.kernel.org/doc/Documentation/cgroup-v1/memory.txt)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
