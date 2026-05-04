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

# Log Stream Reliability and Buffering

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

How reliable is the App Service Log Stream (Kudu log streaming) under load, and what are the conditions under which log messages are dropped, delayed, or buffered beyond the live stream? How does Log Stream differ from Application Insights in terms of latency and completeness?

## 2. Why this matters

Log Stream is the first tool support engineers reach for during live incidents — it provides real-time visibility into application behavior without requiring Log Analytics workspace access or waiting for ingestion delays. However, customers frequently report that Log Stream appears to drop messages, stops updating, or shows messages out of order. Understanding the buffering model and failure conditions prevents misdiagnosis during active incidents.

## 3. Customer symptom

- "The log stream stopped updating in the middle of the incident."
- "I can see the errors in Application Insights but not in Log Stream."
- "Log Stream shows messages from 5 minutes ago, not current."
- "Log Stream works fine in staging but drops messages in production under load."

## 4. Hypothesis

**H1 — High-volume log loss**: When application log output exceeds the Log Stream buffer capacity, messages are dropped rather than buffered indefinitely. There is a maximum throughput threshold above which the stream is unreliable.

**H2 — Log Stream vs. App Insights latency**: Log Stream shows messages with lower latency than Application Insights (which has 2–5 minute ingestion delay), but Log Stream is less reliable at high volume.

**H3 — Connection drop under instance recycling**: Log Stream disconnects when the instance it is connected to is recycled (restart, swap, scale-in). The stream does not reconnect automatically and must be re-established.

**H4 — stdio vs. file logging**: Log Stream for Linux containers captures stdout/stderr of the container process. Logs written to a file inside the container (not `/home/LogFiles`) are not visible in Log Stream regardless of file logging settings.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Linux |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Observability

**Controlled:**

- Log output rate (1 msg/s, 100 msg/s, 1000 msg/s)
- Log destination (stdout vs. file)
- Application Insights instrumentation key present vs. absent
- Instance restart timing

**Observed:**

- Number of messages received in Log Stream vs. emitted by app
- Latency from app log emission to Log Stream appearance
- Log Stream behavior during instance restart
- App Insights ingestion latency

## 7. Instrumentation

- Application: sequence-numbered log messages with timestamps (`LOG #1234 at 10:00:00.123`)
- Log Stream: capture output to local file, count and sequence-check messages
- App Insights: same sequence numbers via `logging.info()` → AI handler
- Python `logging` module with UTC timestamps

**Verification query:**

```kusto
traces
| where message startswith "LOG #"
| extend seq = toint(extract("LOG #(\\d+)", 1, message))
| summarize min_seq=min(seq), max_seq=max(seq), count()
| extend expected = max_seq - min_seq + 1
| extend lost = expected - count_
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az group create --name rg-logstream --location koreacentral
az appservice plan create --name plan-logstream --resource-group rg-logstream --sku B1 --is-linux
az webapp create --name app-logstream --resource-group rg-logstream --plan plan-logstream --runtime "PYTHON:3.11"

# Enable App Service Logs
az webapp log config --name app-logstream --resource-group rg-logstream \
  --application-logging filesystem --level information
```

### 8.2 Scenarios

**S1 — Low volume (1 msg/s for 60s)**: Emit 60 sequence-numbered messages. Count received in Log Stream and App Insights.

**S2 — Medium volume (100 msg/s for 30s)**: Emit 3,000 sequence-numbered messages. Count and check for gaps.

**S3 — High volume (1000 msg/s for 10s)**: Emit 10,000 messages. Measure drop rate and Log Stream lag.

**S4 — Instance restart mid-stream**: Emit messages, then trigger a restart via `az webapp restart`. Document Log Stream disconnect behavior.

**S5 — File log vs. stdout**: Write same messages to stdout AND a local file (`/tmp/app.log`). Verify which appears in Log Stream.

## 9. Expected signal

- **S1**: All 60 messages appear in both Log Stream and App Insights (with ~2–5 min delay for AI).
- **S2**: Log Stream shows most messages with possible gaps; App Insights shows all (more reliable, slower).
- **S3**: Log Stream drops significant percentage; App Insights drops at high volume too (SDK batching limit).
- **S4**: Log Stream disconnects on restart; messages during restart window are lost from Log Stream.
- **S5**: File log NOT visible in Log Stream. Only stdout/stderr is captured.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Log Stream behavior may differ between Windows and Linux App Service.
- The test uses a single instance — multi-instance log stream may multiplex or only show one instance.
- App Insights sampling rate affects reliability comparison if sampling is enabled.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Log Stream drops messages at high volume | **Inferred** |
| App Insights has higher latency than Log Stream | **Strongly Suggested** |
| File logs are invisible to Log Stream | **Strongly Suggested** (well-documented behavior) |
| Log Stream disconnects on instance restart | **Inferred** |

## 14. Related experiments

- [App Insights vs OpenTelemetry Gap](../zip-vs-container/overview.md) — observability signal gaps
- [App Insights Connection String Injection](../zip-vs-container/overview.md) — AI configuration

## 15. References

- [Enable diagnostics logging in App Service](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs)
- [Log Stream documentation](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs#stream-logs)

## 16. Support takeaway

During live incidents, guide customers to use Log Stream as the lowest-latency signal, but set expectations:

1. Log Stream is best-effort — at high log volume, messages will be dropped. Critical events should also go to Application Insights.
2. Log Stream only captures stdout/stderr. If the app writes logs to a local file, they are not visible in Log Stream.
3. After an instance restart (swap, restart, or scale event), the Log Stream session must be reconnected manually.
4. For post-incident analysis, App Insights traces are more complete despite the ingestion delay.
5. With multiple instances, Log Stream may only show one instance — check Kudu to identify which instance is connected.
