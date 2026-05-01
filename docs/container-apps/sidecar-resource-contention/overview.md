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

# Sidecar Container Resource Contention: CPU and Memory Competition with the Main Container

!!! info "Status: Planned"

## 1. Question

When a sidecar container in a Container App consumes more CPU or memory than expected — due to a log shipping agent, a metrics collector, or a proxy sidecar under load — how does the resource contention manifest in the main container's performance, and does the platform enforce per-container resource limits or only replica-level limits?

## 2. Why this matters

Container Apps supports multiple containers per replica (main + sidecars). Resource limits (`cpu` and `memory`) are specified per container, but the enforcement model — whether limits are enforced independently per container or only at the replica level — affects whether a runaway sidecar can starve the main container. A sidecar that is well-behaved under normal conditions may spike under load (e.g., a log shipper under high log volume), reducing available CPU for the main container. This contention is invisible in application-level metrics and only visible in replica-level resource metrics, making it a difficult-to-diagnose performance regression.

## 3. Customer symptom

"My app's response latency increased but CPU and memory metrics look normal" or "I added a log shipping sidecar and now the app is slow under load" or "The replica gets OOM-killed but the app itself isn't using much memory."

## 4. Hypothesis

- H1: Resource limits specified per container in a Container Apps revision are enforced by the container runtime (cgroups) independently per container. A sidecar that reaches its CPU limit is throttled without affecting the main container's CPU allocation — provided the replica's total resource request is within the replica limit.
- H2: If the total resource usage of all containers in a replica (main + sidecar) exceeds the replica-level resource limit, the platform OOM-kills the replica rather than the individual over-limit container. The OOM kill event appears in `ContainerAppSystemLogs` referencing the replica, not a specific container.
- H3: A sidecar under high load (e.g., a log shipper processing large log volumes) increases its CPU consumption, which competes with the main container for the shared CPU budget of the replica. The main container experiences increased response latency correlated with the sidecar's CPU spike, even if the main container's own CPU limit is not exceeded.
- H4: The `ContainerAppConsoleLogs` table logs stdout from both main and sidecar containers, distinguished by the `ContainerName` field. Resource contention events (OOM, CPU throttle) appear in `ContainerAppSystemLogs` at the replica level, not attributed to a specific container.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (main) + Python 3.11 (sidecar) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Resource / Performance

**Controlled:**

- Container App with one main container (FastAPI HTTP server) and one sidecar (synthetic log generator)
- Resource limits: main container `0.5 vCPU / 1 Gi`, sidecar `0.25 vCPU / 0.5 Gi`
- Replica total: `0.75 vCPU / 1.5 Gi`
- Load profile: constant HTTP traffic to main container during sidecar CPU/memory spike

**Observed:**

- Main container response latency (p50/p95/p99) during sidecar load spike
- CPU and memory usage per container (via `az containerapp revision show` metrics)
- OOM kill events in `ContainerAppSystemLogs` — which container is referenced
- `ContainerName` field in logs — confirm sidecar vs. main attribution

**Scenarios:**

- S1: Sidecar idle — baseline main container response latency
- S2: Sidecar at CPU limit (spinning loop) — observe main container latency impact
- S3: Sidecar memory leak (allocate 600 Mi — exceeds sidecar limit) — observe OOM kill target
- S4: Both containers at resource limits simultaneously — observe replica-level OOM

**Independent run definition**: One load spike event per scenario; 5-minute observation window.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Response latency: `hey -n 1000 -c 10 https://<app>.azurewebsites.net/` during sidecar load — p50/p95/p99
- `ContainerAppSystemLogs` KQL: `| where Reason == "OOMKilled" | project TimeGenerated, ContainerName, Reason` — OOM attribution
- `ContainerAppConsoleLogs` KQL: `| where ContainerName == "<sidecar-name>"` — sidecar stdout (log output rate)
- CPU throttle: `cat /sys/fs/cgroup/cpu/cpu.stat` from within the container — throttled_time counter
- Sidecar trigger: `POST /spike-cpu` or `POST /alloc-memory?mb=600` — deterministic load injection

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy app with sidecar at idle; run baseline latency test (S1); record p50/p95/p99.
2. S2: Trigger sidecar CPU spike (`POST /spike-cpu`); maintain HTTP load on main container; record latency during spike; compare to S1 baseline.
3. S3: Trigger sidecar memory allocation of 600 Mi (exceeds 0.5 Gi limit); observe OOM kill; check `ContainerAppSystemLogs` for the `ContainerName` field of the OOM event.
4. S4: Simultaneously max out both containers; observe whether replica-level OOM triggers when total usage exceeds `1.5 Gi`.
5. For each scenario, log `ContainerName` in all system log OOM events to confirm attribution granularity.

## 9. Expected signal

- S1: p50 ~50 ms, p95 ~200 ms at baseline with sidecar idle.
- S2: p95 increases during sidecar CPU spike; correlation visible between sidecar CPU usage and main container latency.
- S3: OOM kill event in `ContainerAppSystemLogs` references the sidecar container name if per-container limits are enforced; references the replica if only replica-level limits are enforced.
- S4: Replica OOM kill when combined usage exceeds replica limit; main container is terminated despite being within its own limit.

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

- Container-level resource limits in Container Apps are specified per container in the revision template; the replica total is the sum of all containers' limits. Set limits explicitly for every container, including sidecars.
- CPU throttling (not OOM) does not produce a system log event; it is only visible via cgroup statistics (`cpu.stat`) inside the container or via Azure Monitor metrics.
- When diagnosing OOM kills with multiple containers, always check the `ContainerName` field in `ContainerAppSystemLogs` to determine which container triggered the kill.
- Sidecar containers that generate high log volume can also create backpressure in the log pipeline, potentially affecting `ContainerAppConsoleLogs` ingestion latency for both containers.

## 16. Related guide / official docs

- [Containers in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers)
- [Resources and limits in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers#configuration)
- [OOM kills in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-oom-errors)
