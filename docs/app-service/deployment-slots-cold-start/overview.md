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

# Deployment Slot Cold Start After Swap

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution on a P1v3 plan with deployment slots enabled.

## 1. Question

After a slot swap completes, does the production slot serve cold-start latency to the first request, and does the swap warming mechanism prevent this? Under what conditions does cold-start re-occur on the production slot immediately after swap?

## 2. Why this matters

Slot swap is the primary zero-downtime deployment mechanism for App Service. However, customers frequently report that after a swap, the first handful of requests to production are slow — sometimes 5–30 seconds — despite the swap warming phase theoretically pre-initializing the new code. Understanding when warming works and when it fails to prevent cold-start is essential for support cases involving post-swap latency spikes.

## 3. Customer symptom

- "We swapped to production and the first few requests were extremely slow."
- "Our slot swap takes 5 minutes of warming, but production still has slow requests after the swap."
- "The staging slot responds fast before the swap, but production is slow right after it lands."
- "We have Always On enabled but still see a spike after slot swap."

## 4. Hypothesis

**H1 — Warming prevents cold-start**: If warmup requests (via the swap warming phase and `applicationInitialization` configured with routes) successfully pre-initialize the new production slot, the first external client request will not experience cold-start latency.

**H2 — ARR affinity breaks warming**: If ARR affinity is enabled, the warming requests during swap may be routed to specific instances (those that handled the warming HTTP probe), leaving other instances cold. External clients routed to non-warmed instances will see cold-start latency.

**H3 — Always On does not prevent post-swap cold-start**: Always On pings the root path continuously, but the interval (every 5 minutes) means newly-swapped instances may be cold for up to 5 minutes after the swap if warming did not complete successfully.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | P1v3 (deployment slots require Standard or higher) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config + Latency

**Controlled:**

- Slot swap timing and warming phase duration
- Application initialization routes configured vs. not configured
- Always On: enabled vs. disabled
- ARR affinity: enabled vs. disabled
- Number of instances (1 vs. 2)

**Observed:**

- First-request latency to production immediately after swap (p50, p95)
- App Insights dependency traces showing cold-start initialization time
- Worker process PID before and after swap (to confirm process replacement)
- Warm-up probe log entries in Kudu

## 7. Instrumentation

- App Insights: request duration, first vs. subsequent requests by instance
- Kudu console: `/proc/<pid>/cmdline` and start time to detect process replacement
- Custom endpoint: `/health` returning startup time + PID
- External HTTP probe with millisecond timestamps: 20 consecutive requests immediately post-swap
- Application logs: module import timing, first request marker

**Key KQL query:**

```kusto
requests
| where timestamp > ago(30m)
| where name == "GET /health"
| summarize p50=percentile(duration, 50), p95=percentile(duration, 95), count() by bin(timestamp, 1m)
| order by timestamp asc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az group create --name rg-slot-coldstart --location koreacentral

az appservice plan create \
  --name plan-slot-coldstart \
  --resource-group rg-slot-coldstart \
  --sku P1v3 --is-linux

az webapp create \
  --name app-slot-coldstart \
  --resource-group rg-slot-coldstart \
  --plan plan-slot-coldstart \
  --runtime "PYTHON:3.11"

az webapp deployment slot create \
  --name app-slot-coldstart \
  --resource-group rg-slot-coldstart \
  --slot staging
```

### 8.2 Application

Flask app with:
- Deliberate 3-second startup delay (simulating module imports or DB connection pool init)
- `/health` endpoint returning `{"pid": os.getpid(), "started_at": startup_time, "uptime_s": elapsed}`
- Startup timestamp recorded at module import time

### 8.3 Scenarios

**S1 — Swap without warming**: Deploy to staging, immediately swap without `applicationInitialization`. Measure first-request latency to production.

**S2 — Swap with warming routes**: Configure `applicationInitialization` with `<add initializationPage="/health"/>`. Perform swap. Measure first-request latency.

**S3 — Multi-instance + ARR affinity**: Scale to 2 instances, enable ARR affinity, perform swap, send 20 requests and check which instances are warm vs. cold.

**S4 — Always On interaction**: Enable Always On. Swap. Verify whether Always On pings arrived before first external request.

## 9. Expected signal

- **S1**: First request shows 3–4s latency spike (cold-start). Subsequent requests return to baseline (<100ms).
- **S2**: Warming prevents cold-start; first request latency matches warmed baseline.
- **S3**: With 2 instances and ARR affinity, ~50% of clients hit the non-warmed instance and see cold-start.
- **S4**: If Always On fires within seconds of swap, production should be warm. If swap completes and Always On interval has not elapsed, cold-start is possible.

## 10. Results

!!! info "Results pending execution"
    No data collected yet. Results will be added after experiment execution.

### S1 — Swap without warming
*Awaiting data.*

### S2 — Swap with warming routes
*Awaiting data.*

### S3 — Multi-instance + ARR affinity
*Awaiting data.*

### S4 — Always On interaction
*Awaiting data.*

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Single-region test; global Traffic Manager routing may add additional cold-start sources.
- Python startup time (3s simulated) may not match real application startup profiles; .NET or Java apps have different cold-start characteristics.
- ARR affinity behavior may differ between B-series and P-series plans.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Slot swap without warming causes cold-start | **Inferred** (well-documented behavior) |
| Warming prevents cold-start in single-instance | **Unknown** (not yet measured) |
| ARR affinity causes uneven warming across instances | **Unknown** (not yet measured) |

## 14. Related experiments

- [Slot Swap Warmup](../slot-swap-warmup/overview.md) — in-flight request handling during swap warmup phase
- [Always On Ping Interplay](../slot-swap-warmup/overview.md) — Always On behavior and interval
- [Zip Deploy SCM Restart](../zip-vs-container/overview.md) — cold-start triggered by SCM deployment

## 15. References

- [Azure App Service deployment slots documentation](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [applicationInitialization warmup configuration](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#specify-custom-warm-up)

## 16. Support takeaway

When customers report post-swap latency spikes:

1. Check whether `applicationInitialization` is configured with representative routes (not just `/`).
2. Verify instance count — with multiple instances and ARR affinity, uneven warming is expected.
3. Check Always On interval — a recently-swapped app may be cold for up to 5 minutes before the next Always On ping.
4. Review Kudu event log for swap start/end times and warmup probe results.

Slot swap warming only guarantees that the platform sent warmup requests — not that the application was fully initialized. If initialization is slow (DB connection pool, cache warm), the warmup routes must exercise those code paths.
