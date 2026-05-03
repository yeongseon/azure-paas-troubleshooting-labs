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

# CPU Throttling: Baseline vs. Burstable Behavior Across SKUs

!!! info "Status: Planned"

## 1. Question

App Service SKUs have defined CPU limits. When an application exceeds the CPU allocation for its SKU, does App Service hard-throttle (kill/restart) the process, soft-throttle (rate-limit CPU cycles), or allow burst above the nominal limit? How does this differ between B-series (burstable) and P-series (premium) SKUs?

## 2. Why this matters

CPU throttling behavior is poorly understood by customers who observe slow response times without corresponding CPU metric alerts. On burstable SKUs (B1, B2, B3), the nominal CPU allocation can be temporarily exceeded (CPU credits model), but once credits are exhausted, the vCPU is throttled to the baseline — causing sudden performance degradation without any obvious signal. On premium SKUs, the CPU allocation is more consistent but still subject to noisy-neighbor effects at the physical host level. Understanding this behavior is critical for capacity planning and for explaining performance degradation patterns.

## 3. Customer symptom

"The app performs fine most of the time but slows dramatically during peak hours" or "CPU usage shows 50% but response times are 10× worse than expected" or "Performance degrades exactly when CPU credits run out on the B1 plan."

## 4. Hypothesis

- H1: On B1 SKU, the vCPU has a nominal baseline (e.g., 10% of a physical core) and can burst up to 1 vCPU using accrued credits. Once credits are exhausted, performance drops to the baseline rate. This is visible as a sudden increase in response time without a corresponding `CpuPercentage` spike.
- H2: On P1v3 SKU, the vCPU allocation is fixed and does not use a credit model. CPU-intensive work causes `CpuPercentage` to reach 100%, but throttling behavior is soft (CFS scheduler) rather than hard kill.
- H3: App Service `CpuPercentage` metric measures the app's CPU usage as a percentage of its allocated vCPU, not the physical host CPU. At 100% `CpuPercentage`, the process is using its full vCPU allocation; actual performance may still be degraded if the host is overcommitted.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 and P1v3 (compared) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance / Platform behavior

**Controlled:**

- CPU burn endpoint that runs a tight loop for a configurable duration
- Load generator sustaining 100% CPU for 10+ minutes
- Azure Monitor `CpuPercentage` metric at 1-minute granularity

**Observed:**

- Response time under sustained CPU load on B1 vs P1v3
- CPU credit consumption rate (B1 only)
- Relationship between `CpuPercentage` metric and actual request latency

**Scenarios:**

- S1: P1v3 at 100% CPU — measure response time degradation
- S2: B1 at 100% CPU for 15 minutes — observe credit exhaustion and performance cliff
- S3: B1 with idle periods between bursts — observe credit recovery

## 7. Instrumentation

- Azure Monitor `CpuPercentage` metric
- Application response time measurement (Apache Bench p95 latency)
- `cat /proc/sched_debug` or `top` via Kudu SSH to observe scheduler behavior
- App Service Diagnose and Solve: CPU Analysis

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy CPU burn endpoint on both B1 and P1v3 apps.
2. S1 (P1v3): Run `ab -n 10000 -c 4 /cpu-burn?seconds=1`; measure p95 latency; check if it remains consistent.
3. S2 (B1): Sustain 100% CPU for 15 minutes; measure latency every minute; plot latency vs. time to identify performance cliff.
4. S3 (B1): Allow 10 minutes idle (credit recovery); repeat S2; confirm initial burst performance.

## 9. Expected signal

- S1: P1v3 maintains consistent latency at 100% CPU (no credit model); `CpuPercentage` at 100% but response times remain stable.
- S2: B1 initially responds quickly (credits available); after credit exhaustion, response times increase 5-10× while `CpuPercentage` remains at 100%.
- S3: After credit recovery, B1 returns to initial burst performance.

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

- B-series SKU CPU credit behavior follows Azure VM Bsv2 series documentation (App Service B-series maps to these VM types).
- `CpuPercentage` in Azure Monitor is the platform metric. Process-level CPU can be checked via `/proc/<pid>/stat` via Kudu SSH.
- CPU throttling in Linux cgroups uses CFS bandwidth control (cpu.cfs_quota_us / cpu.cfs_period_us). Check `/sys/fs/cgroup/cpu/` for the configured quota.

## 16. Related guide / official docs

- [App Service pricing and SKU comparison](https://azure.microsoft.com/pricing/details/app-service/linux/)
- [Monitor your app in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/web-sites-monitor)
- [B-series burstable virtual machines](https://learn.microsoft.com/en-us/azure/virtual-machines/bsv2-series)
