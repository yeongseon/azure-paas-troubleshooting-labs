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

# Auto Heal Misconfiguration: Spurious Worker Recycling

!!! info "Status: Planned"

## 1. Question

When App Service Auto Heal rules are configured with thresholds that overlap with normal application traffic patterns (e.g., request count or slow request threshold set too low), does the platform recycle workers during peak traffic, and how does this manifest in availability metrics?

## 2. Why this matters

Auto Heal is a self-healing mechanism designed to restart workers when they exhibit unhealthy behavior (slow responses, excessive memory, too many requests). When misconfigured, it triggers under normal load and creates artificial outages — workers are recycled mid-request, causing in-flight requests to fail and creating a pattern of intermittent 502/503 errors that correlates with traffic spikes rather than actual health issues. This is particularly difficult to diagnose because the recycling is intentional from the platform's perspective but appears as a platform bug from the customer's perspective.

## 3. Customer symptom

"We see 502/503 errors every time traffic increases above a certain threshold" or "Workers restart randomly throughout the day with no apparent cause" or "Response times spike briefly and then return to normal — it happens like clockwork."

## 4. Hypothesis

- H1: When an Auto Heal rule triggers on request count (e.g., `requestCount >= 100 in 60 seconds`), and the app regularly receives 100+ requests per minute under normal load, the rule fires continuously, recycling the worker every 60 seconds. This creates periodic 30-60 second outage windows.
- H2: When a slow request rule triggers on `slowRequestCount >= 5 where duration >= 5s in 2 minutes`, and the app has a dependency that occasionally takes 5+ seconds (acceptable P99 latency), the rule fires under normal operation, causing spurious recycles.
- H3: Auto Heal recycle events are recorded in the Activity Log and in `AppServicePlatformLogs`. The recycle reason is visible in the event data, allowing correlation with the misconfigured rule.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Reliability

**Controlled:**

- Auto Heal rule set to trigger on request count ≥ 50 in 60 seconds (intentionally low)
- Load generator sending 60 requests per minute (just above threshold)
- Auto Heal action: Recycle Process

**Observed:**

- Worker recycle frequency
- Request failure rate during recycle
- Auto Heal trigger events in logs

**Scenarios:**

- S1: Baseline — Auto Heal disabled, load at 60 req/min → confirm no recycling
- S2: Auto Heal enabled with threshold at 50 req/min → observe recycling pattern
- S3: Raise threshold to 1000 req/min → confirm recycling stops

## 7. Instrumentation

- `AppServicePlatformLogs` in Log Analytics — filter for `AutoHeal` events
- App Service **Diagnose and Solve Problems** → Auto Heal
- Load generator (Apache Bench or locust) tracking request success rates
- Azure Monitor metrics: `Http5xx`, `Requests` with 1-minute granularity

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy a simple app with a `/slow` endpoint (sleeps 5 seconds) and a `/fast` endpoint.
2. S1: Disable Auto Heal; run load generator at 60 req/min; confirm stable operation.
3. S2: Enable Auto Heal with `requestCount >= 50 in 60s → Recycle`; run same load; observe recycling cycle and 503s during recycle.
4. Query `AppServicePlatformLogs` to confirm recycle events with `AutoHeal` as the trigger.
5. S3: Update Auto Heal threshold to 1000 req/min; run load; confirm no recycling.

## 9. Expected signal

- S1: No recycle events; steady request success rate.
- S2: Recycle event approximately every 60 seconds; brief 503 spike during each recycle (5-15 seconds); `AppServicePlatformLogs` shows `AutoHealTriggered` event correlated with recycle.
- S3: No recycle events at same load level after threshold adjustment.

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

- Auto Heal is configured under **Diagnose and Solve Problems** → Auto-Heal, or via ARM: `properties.siteConfig.autoHealEnabled` and `properties.siteConfig.autoHealRules`.
- Available triggers: request count, slow requests, memory limit, status codes.
- Available actions: Recycle Process, Log Event, Custom Action (run executable).
- Auto Heal only recycles the worker process — it does not affect the platform layer. A new process starts immediately and takes traffic, but the cold start may cause the initial requests to that instance to be slow.

## 16. Related guide / official docs

- [Auto Heal for Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/overview-diagnostics#auto-heal)
- [Configure auto healing](https://learn.microsoft.com/en-us/azure/app-service/configure-automatic-healing)
