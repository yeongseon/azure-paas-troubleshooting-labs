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

# Container CPU Limit Burst: Throttling Under Sustained Load

!!! info "Status: Planned"

## 1. Question

Container Apps allows configuring CPU requests and limits per container. When a container's CPU usage exceeds its configured CPU limit, what throttling behavior occurs — is the process throttled via CFS bandwidth control, and what observable symptoms appear in application metrics vs. system-level metrics?

## 2. Why this matters

Containers deployed without explicit CPU limits run with a soft limit equal to the requested CPU (the default behavior). When load spikes, a container with 0.5 vCPU request and a 2.0 vCPU limit can burst temporarily. However, when a container hits its CPU limit under sustained load, CFS bandwidth control (Linux cgroups) throttles the process by suspending it for portions of each 100ms scheduling period. This causes erratic latency spikes that are not correlated with CPU usage percentage (which stays at 100% of the limit), making diagnosis difficult.

## 3. Customer symptom

"CPU is at 100% but response times are erratic — sometimes fast, sometimes very slow" or "p99 latency is 10× the p50 even though p50 is acceptable" or "Adding more replicas doesn't help — each replica still has high latency."

## 4. Hypothesis

- H1: When CPU usage hits the container's CPU limit, the Linux CFS scheduler throttles the container. The throttling appears as periodic pauses in execution, causing request latency to spike at unpredictable intervals. CPU usage in Azure Monitor remains near 100% (relative to the limit) but doesn't reflect the throttling directly.
- H2: The throttling rate is visible in `/sys/fs/cgroup/cpu/cpu.stat` as `throttled_time` increasing. This requires exec access to the container (via `az containerapp exec`).
- H3: Increasing the CPU limit (with corresponding cost increase) or reducing the application's CPU usage (optimization) resolves the throttling. Horizontal scaling (more replicas) distributes load but each replica still throttles if its individual share of load exceeds the limit.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance / Resource limits

**Controlled:**

- Container CPU request and limit: 0.5 vCPU (tight limit)
- CPU-intensive endpoint that uses ~0.5 vCPU per request
- Load generator sustaining 1 concurrent request (should hit the limit)

**Observed:**

- Response latency p50 and p99
- CPU usage metric in Azure Monitor (% of limit)
- `cpu.stat throttled_time` via container exec

**Scenarios:**

- S1: 0.5 vCPU limit, 1 concurrent request → throttling under sustained load
- S2: 2.0 vCPU limit, same load → no throttling; consistent latency
- S3: 0.5 vCPU limit, horizontal scale to 4 replicas, load balanced → same per-replica throttling

## 7. Instrumentation

- Client-side p50/p95/p99 latency from Apache Bench or locust
- `az containerapp exec -- cat /sys/fs/cgroup/cpu/cpu.stat` to observe throttle counters
- Azure Monitor Container Apps CPU metrics (per container)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy CPU-burn app with 0.5 vCPU limit.
2. S1: Run sustained CPU load at ~100% of limit; measure p50/p99 latency; observe throttled_time increasing.
3. S2: Increase CPU limit to 2.0; run same load; measure p50/p99; compare.
4. S3: Return to 0.5 vCPU; scale to 4 replicas; apply same total load (split across replicas); observe per-replica throttling still occurs.

## 9. Expected signal

- S1: p99 latency is 2-5× p50; `throttled_time` increases in `/sys/fs/cgroup/cpu/cpu.stat`.
- S2: p99 and p50 converge; no throttled_time increase.
- S3: Each replica experiences same throttling as S1; horizontal scale does not help if per-replica load hits the limit.

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

- Container CPU throttling is a Linux cgroups CFS behavior. The `throttled_time` counter in `/sys/fs/cgroup/cpu/cpu.stat` measures nanoseconds the container was throttled.
- In Container Apps, CPU is allocated in 0.25 vCPU increments. Minimum: 0.25 vCPU; Maximum: 4 vCPU (Consumption plan).
- CPU limit and memory limit are configured together in Container Apps; CPU and memory are provisioned in predefined pairs.

## 16. Related guide / official docs

- [Container Apps resource allocation](https://learn.microsoft.com/en-us/azure/container-apps/containers#allocations)
- [Linux cgroups CPU bandwidth control](https://www.kernel.org/doc/html/latest/scheduler/sched-bwc.html)
