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

# Log Analytics Ingestion Gap: Console Logs vs System Logs vs Real-time Streaming

!!! info "Status: Planned"

## 1. Question

In Azure Container Apps, when a container emits stdout, is OOM-killed, and triggers a scaling event simultaneously, are the corresponding entries across `ContainerAppConsoleLogs`, `ContainerAppSystemLogs`, and the real-time log stream captured with consistent event ordering — and are there conditions where entries are delayed, misordered, or lost entirely?

## 2. Why this matters

Support engineers diagnosing Container App incidents rely on three log surfaces: `ContainerAppConsoleLogs` (stdout/stderr via Log Analytics), `ContainerAppSystemLogs` (platform events: OOMKill, restart, scaling), and real-time log streaming (`az containerapp logs show --follow`). These surfaces have different ingestion paths and latencies. A restart event may appear in metrics (replica count drop) before the reason appears in system logs; a console log entry may arrive after the correlated system event; and logs emitted just before an OOM kill may be lost entirely. Misordered or missing data leads to incorrect root cause analysis.

## 3. Customer symptom

"I see a restart in the metrics but the system logs show nothing at the time of the event" or "The real-time log stream shows errors but I can't find them in Log Analytics afterward" or "I can't tell when exactly the container crashed because the log timestamps don't align with the metric drop."

## 4. Hypothesis

- H1: `ContainerAppConsoleLogs` in Log Analytics has a measurable ingestion delay relative to the container event time. The delay is observable by comparing a wall-clock timestamp embedded in stdout with the `TimeGenerated` field in Log Analytics (which reflects the platform's event time, not the ingestion time). The `ingestion_time()` function in KQL returns the actual Log Analytics ingestion timestamp and may differ from `TimeGenerated`.
- H2: `ContainerAppSystemLogs` for restart events (OOMKill, probe failure) appears in Log Analytics before the corresponding console log entries for the same restart window — because system events are emitted by the platform directly, while console logs travel through a separate stdout collection pipeline.
- H3: Stdout lines emitted by a container in the seconds before an OOM kill may be lost and not appear in `ContainerAppConsoleLogs`. The OOM kill event itself is captured in `ContainerAppSystemLogs`.
- H4: Real-time log streaming (`az containerapp logs show --follow`) shows logs with lower latency than Log Analytics ingestion, but may miss entries emitted during a rapid restart (the stream reconnects and may skip the gap window).

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

**Experiment type**: Observability

**Controlled:**

- Container App that emits a wall-clock timestamp in every stdout line (format: `[UNIX_TS] message`)
- Deterministic event triggers: OOM allocation, liveness probe failure (returns 500 on demand)
- Log Analytics workspace with diagnostics settings enabled on the Container Apps environment

**Observed:**

- Embedded event timestamp (from stdout) vs. `TimeGenerated` field in Log Analytics
- `ingestion_time()` in KQL vs. `TimeGenerated` — ingestion delay
- Last stdout line before OOM kill vs. OOMKilled event time in system log
- Real-time stream entry count vs. Log Analytics entry count for the same window

**Scenarios:**

- S1: Normal operation with 1000 stdout lines over 60 seconds — baseline ingestion delay measurement
- S2: Liveness probe failure → restart — compare system log and console log timing
- S3: OOM allocation → OOM kill — check stdout completeness before kill
- S4: Scale-to-zero event — compare metric drop timestamp vs. system log event timestamp

**Independent run definition**: One event trigger per scenario; wait 15 minutes for Log Analytics ingestion before querying.

**Planned runs per configuration**: 5

## 7. Instrumentation

- Container stdout: each line includes a Unix epoch prefix (`[1746000000.123] message`) — parseable with `| extend event_ts = todouble(extract(@"\[(\d+\.\d+)\]", 1, Log))`
- Log Analytics KQL: `ContainerAppConsoleLogs | extend event_ts = todouble(extract(...)) | extend ingestion_delay_s = (ingestion_time() - todatetime(event_ts))` — ingestion delay per line
- `ContainerAppSystemLogs` KQL: `| where Reason in ("OOMKilled", "BackOff", "Killing") | project TimeGenerated, Reason, ContainerName`
- Azure Monitor metric: `ReplicaCount` — time series from Azure Portal
- `az containerapp logs show --follow` — real-time stream; capture to file with wall-clock timestamps
- Comparison: Log Analytics entry count vs. real-time stream entry count for the same 60-second window

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container App with a test harness that: (a) emits timestamped stdout continuously, (b) accepts `POST /trigger-oom` to begin memory allocation, (c) accepts `POST /fail-probe` to make liveness probe return 500.
2. S1: Emit 1000 lines over 60 seconds; wait 15 minutes; query Log Analytics with `ingestion_time()` delta to measure ingestion delay.
3. S2: Trigger liveness probe failure; record wall clock; query `ContainerAppSystemLogs` and `ContainerAppConsoleLogs` at T+5min and T+15min; compare event ordering.
4. S3: Trigger OOM allocation; after OOMKilled event appears in system log, count stdout lines before the last line timestamp vs. expected line count.
5. S4: Stop traffic; wait for scale-to-zero; compare `ReplicaCount` metric drop timestamp vs. `ContainerAppSystemLogs` scaling event timestamp.
6. For each scenario, run `az containerapp logs show --follow` in parallel; compare entry count with Log Analytics count for the same window.

## 9. Expected signal

- S1: `ingestion_time()` is later than `TimeGenerated` by a measurable delta; `TimeGenerated` reflects event time, not ingestion time; actual ingestion delay is visible via `ingestion_time() - TimeGenerated`.
- S2: `ContainerAppSystemLogs` restart event appears in Log Analytics before the corresponding `ContainerAppConsoleLogs` entry for the same restart window.
- S3: One or more stdout lines emitted immediately before the OOM kill are absent from `ContainerAppConsoleLogs`; OOMKilled reason is present in `ContainerAppSystemLogs`.
- S4: `ReplicaCount` metric drops before the corresponding scaling event appears in `ContainerAppSystemLogs`.

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

- Use `ingestion_time()` in KQL to measure actual Log Analytics ingestion latency; `TimeGenerated` reflects the platform event time, not the time the entry landed in Log Analytics.
- Real-time log streaming and Log Analytics ingestion use different pipelines; entries visible in the stream may not appear in Log Analytics for several minutes, and vice versa during rapid restarts.
- OOM tests should allocate memory at a controlled rate (e.g., 20 MB/s) to ensure the OOM event falls within a predictable time window.
- Log Analytics ingestion latency varies by region and workspace load; run tests at consistent times and note the workspace region.

## 16. Related guide / official docs

- [Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [View log streams in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-streaming)
- [Observability in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [Log Analytics ingestion time — ingestion_time() function](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-standard-columns#_ingestiontime)
