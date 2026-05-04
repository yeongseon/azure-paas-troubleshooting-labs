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

# Replica Restart Loop Detection and Recovery

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When a Container Apps replica enters a crash loop (OOMKill, failed liveness probe, application startup failure), what signals are available to detect the loop, and what is the platform's backoff behavior? Does the backoff prevent service availability from being fully restored after the root cause is fixed?

## 2. Why this matters

Crash loops are a common operational failure mode in containerized systems. In Kubernetes, crash loops follow an exponential backoff (CrashLoopBackOff). Container Apps uses Envoy and the managed runtime, which may have different backoff semantics. Support cases arise when:

- A customer fixes the root cause (e.g., adds missing environment variable) but the app doesn't recover for several minutes
- The container crashes repeatedly with no obvious signal in Azure Monitor
- Customers confuse OOMKill restart (immediate) with liveness probe failure (delayed eviction)
- The restart count visible in logs doesn't match the customer's observation of availability impact

## 3. Customer symptom

- "Our app keeps restarting. We fixed the problem but it's still in a loop."
- "How do I stop the restart loop without deploying a new revision?"
- "The app starts, runs for 10 seconds, then crashes. This keeps repeating."
- "Container Apps doesn't show any errors but the app keeps restarting."

## 4. Hypothesis

**H1 — Exponential backoff on crash loop**: Container Apps applies an exponential backoff delay between restart attempts, similar to Kubernetes CrashLoopBackOff. The delay grows with each consecutive failure.

**H2 — OOMKill restarts are faster than probe failures**: An OOMKill restart is immediate (process killed by kernel). A liveness probe failure requires multiple failed probe cycles before the container is restarted. These two failure modes produce different restart patterns.

**H3 — Signal visibility gap**: Consecutive restarts may not appear in Log Analytics until the container has been running for a minimum time. Very fast crash loops (crash within 1–2s of start) may have reduced log visibility.

**H4 — New revision clears backoff**: Creating a new revision (even identical) starts with a fresh restart count and no backoff delay. This is why "deploying the same image" sometimes appears to fix a crash loop.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Failure Injection

**Controlled:**

- Crash type: immediate exit (code 1), OOMKill (allocate until killed), liveness probe failure
- Crash timing: crash immediately vs. crash after 10s, 30s, 60s
- Number of consecutive crashes before fix

**Observed:**

- Time between consecutive restart attempts (backoff pattern)
- Container restart count in Azure Monitor
- Time from fix application to successful restart
- Log entries per restart attempt

## 7. Instrumentation

- Application: startup time parameter via env var `CRASH_AFTER_S` (0 = immediate crash)
- `/health` endpoint: returns PID, uptime, restart count from shared file
- Container Apps system metrics: replica restart count
- Log Analytics: `ContainerAppConsoleLogs` per restart attempt

**Restart count query:**

```kusto
ContainerAppConsoleLogs
| where ContainerAppName == "app-restart-loop"
| summarize restarts=count() by bin(TimeGenerated, 1m)
| order by TimeGenerated asc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az containerapp create \
  --name app-restart-loop \
  --resource-group rg-restart-loop \
  --environment env-restart-loop \
  --image <test-image> \
  --env-vars CRASH_AFTER_S=0
```

### 8.2 Scenarios

**S1 — Immediate crash loop**: Set `CRASH_AFTER_S=0`. Container exits immediately on start. Record time between restart attempts for 10 consecutive crashes.

**S2 — Delayed crash (30s)**: Set `CRASH_AFTER_S=30`. Container runs for 30s before exiting. Compare backoff pattern with S1.

**S3 — OOMKill loop**: Allocate progressively increasing memory until OOMKilled. Compare restart timing with voluntary exit.

**S4 — Liveness probe failure**: Configure liveness probe with 3 failures × 10s interval. Hang the `/health` endpoint. Measure time from probe start to container restart.

**S5 — Recovery after fix**: After 5 consecutive crashes, update env var to fix crash. Measure time from fix to successful stable start.

**S6 — New revision clears backoff**: After 5 crashes, create identical new revision. Compare recovery time with S5.

## 9. Expected signal

- **S1**: Restart interval grows from ~10s to ~60s+ over 5 crashes (exponential backoff).
- **S2**: Shorter backoff because each run lasted longer before crashing.
- **S3**: OOMKill shows immediate restart attempt (no voluntary exit, kernel kills process).
- **S4**: Liveness failure takes 30s (3 × 10s) before restart.
- **S5**: After fix, backoff delay still present — recovery takes 1–2 minutes.
- **S6**: New revision starts immediately with no backoff delay.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Backoff behavior is not publicly documented for Container Apps; observations are compared against Kubernetes CrashLoopBackOff semantics.
- Test uses a single replica; multi-replica behavior (partial availability during crash loop) is a separate scenario.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Container Apps applies restart backoff | **Inferred** (standard container platform behavior) |
| New revision clears backoff | **Inferred** |
| OOMKill restarts faster than probe failures | **Strongly Suggested** |

## 14. Related experiments

- [Liveness Probe Failures](../liveness-probe-failures/overview.md) — probe failure timing
- [OOM Visibility Gap](../oom-visibility-gap/overview.md) — OOMKill observability
- [Startup Probes](../startup-probes/overview.md) — startup probe vs. liveness probe interaction

## 15. References

- [Container Apps monitoring documentation](https://learn.microsoft.com/en-us/azure/container-apps/monitor)
- [Container restart policies](https://learn.microsoft.com/en-us/azure/container-apps/containers#restart-policy)

## 16. Support takeaway

When investigating crash loop cases:

1. Check `ContainerAppConsoleLogs` for restart events. The time between entries indicates the current backoff interval.
2. If the customer has fixed the root cause but the app isn't recovering, backoff delay is likely. Creating a new revision (even with identical image) bypasses the backoff.
3. Distinguish OOMKill (immediate restart) from liveness probe failure (delayed restart after N probe failures). The restart pattern in logs indicates which is occurring.
4. For immediate crash loops (crash within seconds of start), logs may be incomplete — the container doesn't run long enough to emit all startup logs before the next restart.
5. Recommend minimum `minReplicas=1` for critical apps — this ensures the platform always tries to maintain at least one running replica even during backoff.
