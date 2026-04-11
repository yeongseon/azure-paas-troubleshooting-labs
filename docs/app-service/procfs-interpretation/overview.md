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

# procfs Interpretation on App Service Linux

!!! info "Status: Planned"

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
| SKU / Plan | B1, P1v3, P1mv3 |
| Region | Korea Central |
| Runtime | Python 3.11, Node.js 20 |
| OS | Linux |
| Date tested | — |

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

_To be defined during execution._

## 9. Expected signal

- `/proc/meminfo` `MemTotal` may reflect host-visible memory and not strict plan memory quota
- Cgroup memory limit files are expected to map to SKU constraints more directly than procfs totals
- CPU quota behavior is expected to be clearer in cgroup controls than in aggregate `/proc/stat` values
- Azure Monitor trends should correlate better with quota-scoped metrics than with host-scoped procfs fields

## 10. Results

_Awaiting execution._

## 11. Interpretation

_Awaiting execution._

## 12. What this proves

_Awaiting execution._

## 13. What this does NOT prove

_Awaiting execution._

## 14. Support takeaway

_Awaiting execution._

## 15. Reproduction notes

- Capture procfs and cgroup snapshots at fixed intervals so timestamps align with Azure Monitor granularity.
- Validate container instance restarts before each run to avoid mixing old and new process contexts.
- Record the exact SKU and runtime because procfs presentation can vary by worker image generation.
- Keep load profile stable during collection to isolate interpretation differences from workload effects.

## 16. Related guide / official docs

- [Microsoft Learn: App Service Linux containers](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
- [cgroup v1 memory documentation](https://www.kernel.org/doc/Documentation/cgroup-v1/memory.txt)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
