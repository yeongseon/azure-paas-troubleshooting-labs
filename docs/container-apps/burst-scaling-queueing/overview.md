---
hide:
  - toc
validation:
  az_cli:
    last_tested: null
    result: not_tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Burst Scaling Queueing Before Replica Add

!!! info "Status: Draft - Awaiting Execution"
    Experiment designed but not yet executed. This draft targets a common Container Apps support question: under sudden HTTP bursts, how much latency/error budget is lost while HTTP autoscaling is still deciding to add replicas, and which knobs actually reduce the failure window?

## 1. Question

Under sudden HTTP burst traffic, how much queueing happens before Azure Container Apps adds replicas, and which HTTP scaling settings actually reduce `5xx` rates and tail latency during scale-out?

## 2. Why this matters

Customers often interpret burst-time `502`/`503` responses or very high `p95`/`p99` latency as evidence that Container Apps "could not handle load," even when average load is low and steady-state throughput is acceptable. In practice, the confusing part is the **transition window** between the moment traffic surges and the moment new replicas become available.

This matters for support because:

- many workloads are mostly idle, then receive webhook, campaign, or API burst traffic
- `minReplicas=1` is commonly assumed to solve all burst issues, even though it only removes scale-from-zero delay
- the default HTTP scaler threshold (`concurrentRequests=10`) may fit steady traffic but react too slowly to short spikes
- customers often tune `cooldownPeriod` expecting faster scale-out, even though it primarily affects scale-in timing
- tail latency and `5xx` responses during the first 10-60 seconds can be more important than average throughput

The experiment is intended to separate:

1. cold-start contribution when the app begins at `0` replicas
2. warm burst queueing when the app begins at `1` replica
3. the effect of `concurrentRequests` threshold on scale trigger sensitivity
4. the effect of `pollingInterval` on how quickly scaling reacts to the burst
5. the non-effect of `cooldownPeriod` on the initial scale-out decision

## 3. Customer symptom

Typical ticket phrasing:

- "Short traffic spikes cause timeouts before autoscale catches up."
- "Container Apps eventually scales out, but users already got `503` or very slow responses."
- "`minReplicas=1` helped cold starts but did not stop burst failures."
- "We lowered `cooldownPeriod`, but burst latency did not improve."
- "What should we tune first: min replicas, concurrent requests, or polling interval?"

## 4. Hypothesis

1. **Default HTTP scaling** with `concurrentRequests=10` may not react quickly enough for short bursts, causing transient queueing on the initial replica before additional replicas are ready.
2. **`pollingInterval`** is a major contributor to burst response lag; lower values such as `10s` should reduce time-to-scale compared with `30s` or `60s`.
3. **`cooldownPeriod`** affects how long replicas remain after traffic falls, but should not materially improve initial scale-out speed.
4. **`minReplicas > 0`** removes scale-from-zero cold start, but does not by itself eliminate queueing during a burst that exceeds one replica's capacity.
5. **Lower `concurrentRequests` thresholds** (for example `5`) should trigger scale-out earlier than `10`, `20`, or `50`, reducing `p99` latency and `5xx` rate at the cost of more aggressive scaling.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 custom container |
| OS | Linux |
| Test app | HTTP service with configurable per-request latency and request timing headers |
| Ingress | External, target port `8080` |
| Scaling | HTTP rule with configurable `concurrentRequests`; environment-level `pollingInterval` and `cooldownPeriod` |
| Load tools | `hey` or `wrk` from external Linux VM / Cloud Shell |
| Logging | Log Analytics + Container Apps system/console logs + Azure Monitor metrics |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Performance / scaling behavior comparison

**Controlled:**

- same Container Apps environment and region
- same app image and code
- same CPU / memory allocation per replica
- same target port and ingress mode
- same maximum replica limit unless explicitly changed
- same burst duration, request payload size, and client location for comparable runs
- same baseline artificial server latency (for example `250 ms`) unless noted otherwise

**Independent variables:**

- starting replica count: `0` vs `1`
- HTTP scaler `concurrentRequests`: `5`, `10`, `20`, `50`
- environment `pollingInterval`: `10`, `30`, `60` seconds
- environment `cooldownPeriod`: baseline `300` seconds, optional comparison `60` seconds
- burst profile: short spike, step burst, sustained burst

**Observed:**

- time from burst start to first additional replica creation
- time from burst start to first additional replica becoming ready
- replica count over time
- HTTP status distribution (`200`, `429`, `502`, `503`, client timeout)
- `p50`, `p95`, `p99`, and max latency during the burst window
- request queueing signal inferred from app-side wait time and latency inflation
- scale-related system log messages
- app-side timestamps showing when each replica began serving requests

**Independent run definition**: one clean deployment or configuration state, followed by one burst test after confirming the intended starting replica count and idle/warm condition

**Planned runs per configuration**: minimum `5` independent runs

**Warm-up exclusion rule**: exclude pre-burst verification requests from latency analysis; include all burst requests

**Primary metrics**: time to second replica ready, burst-window `p99` latency, burst-window `5xx` rate

**Meaningful effect threshold**:

- time-to-scale change of `>= 10s`
- `p99` latency change of `>= 25%`
- absolute `5xx` rate change of `>= 1 percentage point`

## 7. Instrumentation

Planned evidence sources:

- **External load generator**: `hey` for repeatable concurrent HTTP bursts; optional `wrk` for higher-rate bursts
- **ContainerAppSystemLogs_CL**: revision lifecycle, replica creation, scaling events, environment-level events
- **ContainerAppConsoleLogs_CL**: app log markers for request arrival, service start, and per-replica identifiers
- **Azure CLI**: environment configuration, revision inspection, replica listing
- **Azure Monitor metrics**: request count, response code breakdown, latency, replica count if exposed in the selected metric namespace

Recommended application log markers:

- `APP_START`
- `REQUEST_START`
- `REQUEST_END`
- `REPLICA_ID`
- `ARTIFICIAL_DELAY_MS`
- `INFLIGHT_COUNT`

### Test application example

```python
import os
import time
import socket
from datetime import datetime, timezone
from flask import Flask, jsonify, request

app = Flask(__name__)
HOSTNAME = socket.gethostname()
APP_START_MONO = time.monotonic()
APP_START_UTC = datetime.now(timezone.utc).isoformat()
BASE_DELAY_MS = int(os.getenv("BASE_DELAY_MS", "250"))
EXTRA_DELAY_MS = int(os.getenv("EXTRA_DELAY_MS", "0"))
INFLIGHT = 0

@app.route("/")
def index():
    global INFLIGHT
    request_start = time.monotonic()
    request_start_utc = datetime.now(timezone.utc).isoformat()
    INFLIGHT += 1
    inflight_at_start = INFLIGHT

    try:
        time.sleep((BASE_DELAY_MS + EXTRA_DELAY_MS) / 1000)
        return jsonify({
            "status": "ok",
            "hostname": HOSTNAME,
            "app_start_utc": APP_START_UTC,
            "request_start_utc": request_start_utc,
            "response_utc": datetime.now(timezone.utc).isoformat(),
            "service_time_ms": BASE_DELAY_MS + EXTRA_DELAY_MS,
            "inflight_at_start": inflight_at_start,
            "uptime_seconds": round(time.monotonic() - APP_START_MONO, 3)
        })
    finally:
        INFLIGHT -= 1
```

### Load test scripts

#### Short burst with `hey`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
TOTAL_REQUESTS="${2:-400}"
CONCURRENCY="${3:-100}"
OUTDIR="${4:-results/hey-short-burst}"

mkdir -p "$OUTDIR"

hey \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENCY" \
  -disable-keepalive \
  -o csv \
  "$URL" > "$OUTDIR/hey.csv"
```

#### Sustained burst with `wrk`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
DURATION="${2:-90s}"
CONNECTIONS="${3:-200}"
THREADS="${4:-4}"
OUTDIR="${5:-results/wrk-sustained-burst}"

mkdir -p "$OUTDIR"

wrk \
  --latency \
  -t "$THREADS" \
  -c "$CONNECTIONS" \
  -d "$DURATION" \
  "$URL" | tee "$OUTDIR/wrk.txt"
```

#### Step-burst pattern using `curl`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
OUTFILE="${2:-results/step-burst.csv}"

mkdir -p "$(dirname "$OUTFILE")"
printf 'phase,ts_utc,http_code,time_total,errormsg\n' > "$OUTFILE"

run_phase() {
  local phase="$1"
  local requests_per_phase="$2"
  local parallelism="$3"

  seq "$requests_per_phase" | xargs -I{} -P "$parallelism" bash -c '
    ts_utc="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")"
    result="$({ curl -skS "$0" -o /dev/null -w "%{http_code},%{time_total},%{errormsg}" --max-time 15; } 2>&1 || true)"
    printf "%s,%s,%s\n" "$1" "$ts_utc" "$result"
  ' "$URL" "$phase" >> "$OUTFILE"
}

run_phase warmup 20 2
sleep 10
run_phase burst_25 100 25
sleep 15
run_phase burst_100 400 100
sleep 15
run_phase burst_200 800 200
```

### Replica / metric collection helpers

```bash
#!/usr/bin/env bash
set -euo pipefail

RG="$1"
APP="$2"
OUTFILE="${3:-results/replicas.csv}"

mkdir -p "$(dirname "$OUTFILE")"
printf 'ts_utc,replica_count,replicas\n' > "$OUTFILE"

while true; do
  ts_utc="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")"
  replicas_json="$(az containerapp replica list --resource-group "$RG" --name "$APP" --output json)"
  replica_count="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' <<< "$replicas_json")"
  replicas_flat="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(";".join(sorted(x.get("name","unknown") for x in data)))' <<< "$replicas_json")"
  printf '%s,%s,%s\n' "$ts_utc" "$replica_count" "$replicas_flat" >> "$OUTFILE"
  sleep 2
done
```

### Kusto queries

```kusto
// Scaling / replica lifecycle timeline
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-burst-scaling"
| where TimeGenerated between (datetime(2026-04-12T00:00:00Z) .. datetime(2026-04-12T01:00:00Z))
| project TimeGenerated, RevisionName_s, ReplicaName_s, Reason_s, Log_s
| order by TimeGenerated asc
```

```kusto
// Application-side request markers and replica identifiers
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-burst-scaling"
| where TimeGenerated between (datetime(2026-04-12T00:00:00Z) .. datetime(2026-04-12T01:00:00Z))
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated asc
```

```kusto
// Error-focused view during the burst window
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-burst-scaling"
| where Log_s has_any ("scale", "replica", "failed", "503", "502", "timeout")
| project TimeGenerated, ReplicaName_s, Reason_s, Log_s
| order by TimeGenerated asc
```

## 8. Procedure

### 8.1 Infrastructure setup

```bash
# Resource group
az group create \
  --name rg-aca-burst-scaling-lab \
  --location koreacentral

# Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group rg-aca-burst-scaling-lab \
  --workspace-name law-aca-burst-scaling \
  --location koreacentral

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group rg-aca-burst-scaling-lab \
  --workspace-name law-aca-burst-scaling \
  --query customerId -o tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group rg-aca-burst-scaling-lab \
  --workspace-name law-aca-burst-scaling \
  --query primarySharedKey -o tsv)

# Container Apps environment
az containerapp env create \
  --name cae-burst-scaling-lab \
  --resource-group rg-aca-burst-scaling-lab \
  --location koreacentral \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY"

# ACR
az acr create \
  --name acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --sku Basic \
  --admin-enabled true \
  --location koreacentral
```

### 8.2 Build and push the test image

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
```

```bash
az acr build \
  --registry acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --image burst-scaling-app:v1 \
  --file Dockerfile .
```

### 8.3 Deploy baseline Container App

```bash
ACR_USER=$(az acr credential show \
  --name acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --query username -o tsv)

ACR_PASS=$(az acr credential show \
  --name acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --query "passwords[0].value" -o tsv)

az containerapp create \
  --name ca-burst-scaling \
  --resource-group rg-aca-burst-scaling-lab \
  --environment cae-burst-scaling-lab \
  --image acrburstscalinglab.azurecr.io/burst-scaling-app:v1 \
  --registry-server acrburstscalinglab.azurecr.io \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 10 \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars BASE_DELAY_MS=250 EXTRA_DELAY_MS=0
```

Record the public URL:

```bash
APP_URL=$(az containerapp show \
  --name ca-burst-scaling \
  --resource-group rg-aca-burst-scaling-lab \
  --query properties.configuration.ingress.fqdn -o tsv)
APP_URL="https://${APP_URL}/"
```

### 8.4 Environment-level scaler timing variants

Container Apps environment settings must be adjusted between scenario groups.

```bash
# Example: set polling interval to 10s and cooldown to 300s
az containerapp env update \
  --name cae-burst-scaling-lab \
  --resource-group rg-aca-burst-scaling-lab \
  --keda-config polling-interval=10 cooldown-period=300

# Example: revert to 30s polling interval
az containerapp env update \
  --name cae-burst-scaling-lab \
  --resource-group rg-aca-burst-scaling-lab \
  --keda-config polling-interval=30 cooldown-period=300
```

If the CLI syntax for `--keda-config` changes, capture the exact command version used in the final execution notes.

### 8.5 App-level scaling variants

For each `concurrentRequests` threshold, update the app and wait for the revision to stabilize.

```bash
az containerapp update \
  --name ca-burst-scaling \
  --resource-group rg-aca-burst-scaling-lab \
  --min-replicas 1 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 5
```

Repeat for `10`, `20`, and `50`.

### 8.6 Scenario matrix

| Scenario | Start state | `concurrentRequests` | `pollingInterval` | `cooldownPeriod` | Burst pattern | Goal |
|---|---|---:|---:|---:|---|---|
| 1 | `minReplicas=0`, verified 0 replicas | 10 | 30s | 300s | short burst | cold start + scale-out combined |
| 2 | `minReplicas=1`, warm single replica | 10 | 30s | 300s | short burst | warm burst baseline |
| 3 | `minReplicas=1`, warm single replica | 5 / 10 / 20 / 50 | 30s | 300s | short burst | concurrency threshold comparison |
| 4 | `minReplicas=1`, warm single replica | 10 | 10s / 30s / 60s | 300s | short burst | polling interval comparison |
| 5 | `minReplicas=1`, warm single replica | 10 | 30s | 60s / 300s | short burst | prove cooldown affects scale-in, not initial scale-out |
| 6 | `minReplicas=1`, warm single replica | best two thresholds | best polling interval | 300s | sustained burst | see whether short-burst gains persist |

### 8.7 Execution sequence per independent run

1. Apply the intended environment and app scaling configuration.
2. Wait until the latest revision is healthy and the previous scenario's traffic has ceased.
3. For start-from-zero scenarios, confirm zero replicas with `az containerapp replica list`.
4. For warm scenarios, send a few low-rate requests and confirm exactly one active replica if possible.
5. Start the replica polling helper at `2s` intervals.
6. Start one load script (`hey`, `wrk`, or step burst) and capture raw output.
7. Immediately after the burst, export system and console logs for the matching time window.
8. Record:
    - burst start timestamp
    - first non-200 timestamp
    - first second-replica observed timestamp
    - first second-replica ready/serving timestamp
    - last non-200 timestamp
9. Allow the app to settle, then stop polling and archive all outputs in a scenario/run-specific folder.
10. Repeat until at least `5` independent runs exist for the configuration.

## 9. Expected signal

- **Scenario 1 (0 replicas)** should show the worst user experience because cold start and queueing overlap; latency will be dominated by first replica startup plus scale-out lag.
- **Scenario 2 (1 replica)** should avoid the cold-start penalty but still show elevated `p99` latency and possible `503`/timeout responses while the first replica is saturated.
- **Lower `concurrentRequests` thresholds** should produce earlier replica growth, lower `p99`, and lower `5xx` rates.
- **Shorter `pollingInterval`** should shift the first scale event earlier by roughly one polling cycle relative to slower settings.
- **Changing `cooldownPeriod` alone** should not materially change the timestamp of the first scale-out event under the same burst profile.

## 10. Results

### 10.1 Scenario summary table

Populate after execution.

| Scenario | Runs | Median time to 2nd replica ready | Median burst `p99` | Median `5xx` rate | Notes |
|---|---:|---:|---:|---:|---|
| Cold start + scale-out | - | - | - | - | Pending |
| Warm single replica baseline | - | - | - | - | Pending |
| Threshold = 5 | - | - | - | - | Pending |
| Threshold = 10 | - | - | - | - | Pending |
| Threshold = 20 | - | - | - | - | Pending |
| Threshold = 50 | - | - | - | - | Pending |
| Polling = 10s | - | - | - | - | Pending |
| Polling = 30s | - | - | - | - | Pending |
| Polling = 60s | - | - | - | - | Pending |

### 10.2 Per-run template

| Run | Scenario | Burst start | First non-200 | First extra replica seen | First extra replica serving | Last non-200 | `p99` latency | `5xx` rate |
|---|---|---|---|---|---|---|---:|---:|
| 1 | Example | - | - | - | - | - | - | - |

### 10.3 Raw artifacts to preserve

- `hey.csv` or `wrk.txt`
- replica polling CSV
- exported Kusto query results
- revision / replica CLI snapshots
- optional charts: replica count vs time, request latency vs time, non-200 count vs time

## 11. Interpretation

To be completed only after data collection. Use explicit evidence tags.

Planned interpretation prompts:

- **Observed**: Did new replicas appear only after a measurable queueing/error window had already begun?
- **Measured**: How many seconds elapsed between burst start and scale-out / ready-to-serve timestamps?
- **Correlated**: Did lower `concurrentRequests` or shorter `pollingInterval` align with lower `p99` and lower `5xx`?
- **Inferred**: Is the dominant factor scaler detection delay, replica startup time, or both together?
- **Not Proven**: If bursts are highly variable, avoid over-claiming generality beyond the tested app profile.

## 12. What this proves

This section must stay evidence-bound after execution. The intended proof targets are:

- whether queueing/error windows are measurable before extra replicas begin serving burst traffic
- whether lowering `concurrentRequests` reduces burst-time tail latency and/or `5xx` for this workload
- whether shorter `pollingInterval` changes time-to-scale in a practically meaningful way
- whether `cooldownPeriod` affects initial burst protection or only post-burst scale-in behavior
- whether `minReplicas=1` removes cold start without fully solving burst queueing

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- behavior for non-HTTP scalers such as Service Bus, Kafka, or custom KEDA triggers
- behavior for workloads with very different startup costs, CPU profiles, or upstream dependency latency
- platform-wide guarantees for all regions, environments, or future Container Apps releases
- exact internal implementation details of the managed Envoy / KEDA integration beyond what is externally observable
- the best production setting for every customer cost/performance tradeoff

## 14. Support takeaway

Planned support guidance, pending execution:

- if the symptom is **first burst after idle**, check whether the issue is scale-from-zero rather than generic throughput
- if the symptom is **burst failures despite `minReplicas=1`**, focus on warm scale-out sensitivity (`concurrentRequests`, burst shape, app service time)
- validate whether the customer expects `cooldownPeriod` to improve scale-out; it usually should not
- if request bursts are short and steep, test lower HTTP concurrency thresholds and compare `p99`/`5xx`, not only average latency
- capture replica timeline and request timeline together; either one alone is usually insufficient

## 15. Reproduction notes

- Keep client location stable; cross-region client variance can mask burst-time effects.
- Disable keep-alive for the short-burst test if the goal is to maximize concurrency pressure at ingress.
- Use a deliberately modest app service time (for example `250 ms`) so the first replica can saturate under burst load without the app being unrealistically slow.
- For scale-from-zero scenarios, confirm zero replicas immediately before the burst; waiting too long after verification can invalidate the run.
- Preserve exact CLI versions and command syntax, especially if `az containerapp env update --keda-config` behavior changes.
- If `hey` and `wrk` disagree substantially, prefer the raw per-request artifact that best matches the customer traffic pattern under investigation.

## 16. Related guide / official docs

- [Azure Container Apps scaling](https://learn.microsoft.com/azure/container-apps/scale-app)
- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/scale-app#http)
- [Azure Container Apps environment](https://learn.microsoft.com/azure/container-apps/environment)
- [Azure Monitor for Container Apps](https://learn.microsoft.com/azure/container-apps/log-monitoring)
- [Scale-to-Zero First Request 503/Timeout](../scale-to-zero-502/overview.md)
- [Revision Update Downtime During Container Apps Deployments](../revision-update-downtime/overview.md)
