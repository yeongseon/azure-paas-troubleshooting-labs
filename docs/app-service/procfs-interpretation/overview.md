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

## Question

How reliable is `/proc` filesystem data inside an App Service Linux container, and what are the known interpretation limits when comparing procfs values with Azure Monitor metrics?

## Why this matters

Support engineers and developers frequently use procfs (`/proc/meminfo`, `/proc/stat`, `/proc/loadavg`) to diagnose issues on App Service Linux. However, the values reported by procfs inside a container may reflect the host, the cgroup, or the container depending on the kernel version, cgroup version (v1 vs. v2), and how the App Service sandbox is configured.

Misinterpreting procfs data leads to incorrect memory or CPU conclusions — for example, seeing 32GB total memory in `/proc/meminfo` on a B1 plan with 1.75GB allocated.

## Customer symptom

"The memory/CPU values I read from /proc don't match Azure Monitor" or "My app shows 32GB total memory but the plan only has 1.75GB."

## Planned approach

Deploy a diagnostic application on App Service Linux (multiple SKUs) that reads and logs key procfs files. Compare the procfs output with Azure Monitor metrics and cgroup control files (`memory.limit_in_bytes`, `memory.usage_in_bytes`, `cpu.cfs_quota_us`). Test across B1, P1v3, and P1mv3 to observe SKU-specific differences.

## Key variables

**Controlled:**

- App Service SKU/plan
- Runtime (Python, Node.js)
- Cgroup version exposure

**Observed:**

- `/proc/meminfo` values vs. cgroup memory limits
- `/proc/stat` CPU values vs. cgroup CPU quota
- `/proc/loadavg` vs. Azure Monitor CPU percentage
- Discrepancies between procfs, cgroup, and Azure Monitor

## Expected evidence tags

Observed, Measured, Correlated

## Related resources

- [Microsoft Learn: App Service Linux containers](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
- [cgroup v1 memory documentation](https://www.kernel.org/doc/Documentation/cgroup-v1/memory.txt)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
