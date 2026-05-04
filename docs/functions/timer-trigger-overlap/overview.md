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

# Timer Trigger Overlap and Singleton Behavior

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

In Azure Functions, when a timer-triggered function takes longer to execute than its schedule interval, does the next invocation fire while the previous one is still running (overlap)? Is the `RunOnStartup` and `UseMonitor` behavior the same across Consumption and Flex Consumption plans?

## 2. Why this matters

Timer triggers are one of the most misunderstood Function trigger types. The singleton lease mechanism is supposed to prevent overlapping invocations, but customers frequently report:
- Two invocations of a timer function running simultaneously causing data corruption
- Timer triggers firing "double" after a scale-out event
- Functions not running at the scheduled time after a cold start
- Confusion between `RunOnStartup` (fires immediately on host start) and the normal schedule

Understanding when overlaps occur, when the singleton lease prevents them, and how cold starts interact with scheduled timers is essential for correctness guarantees in timer-driven workloads.

## 3. Customer symptom

- "Our timer function ran twice at the same time and corrupted our data."
- "The timer function skipped an execution after we deployed."
- "The function ran at startup even though we didn't schedule it then."
- "After scaling out to 2 instances, the timer fires twice every minute."

## 4. Hypothesis

**H1 — Singleton lease prevents overlap on single instance**: The distributed singleton lease (stored in Azure Storage) prevents two invocations of the same timer function from running simultaneously, even if the execution exceeds the schedule interval. The second invocation is skipped (not queued) if the first is still running.

**H2 — Scale-out causes duplicate timer fires**: On Consumption plan, if multiple instances are active, the singleton lease prevents double invocation — only one instance will acquire the lease per schedule interval. However, if the lease acquisition fails (network error, Storage latency), duplicates may occur.

**H3 — RunOnStartup causes unexpected immediate execution**: If `RunOnStartup: true`, the function fires immediately on every host startup (cold start, restart, deploy). Customers who set this expecting "run once on first deploy ever" will see it fire on every restart.

**H4 — Schedule missed during cold start**: If the function host is cold (no active instance) when a scheduled time passes, the invocation is executed immediately when the host warms up (schedule recovery), not at the next interval.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| Plan | Consumption (Python) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Trigger Behavior

**Controlled:**

- Timer schedule (every 30s for reliable testing)
- Function execution duration (5s, 60s, 120s via sleep)
- `RunOnStartup` setting: true vs. false
- Instance count: 1 vs. scaled out
- `UseMonitor` setting: true vs. false

**Observed:**

- Invocation timestamps and durations from App Insights
- Invocation count per schedule interval
- Singleton lease acquisition in Azure Storage table
- Schedule missed / recovered events in host log

## 7. Instrumentation

- App Insights: function invocations with custom property `invocation_id`
- Azure Storage: `azure-webjobs-hosts/locks/` container for singleton lease inspection
- Function host log: `azure-functions-host.log` for lease acquisition messages

**Overlap detection query:**

```kusto
traces
| where message startswith "Timer function started"
| extend invocation = tostring(customDimensions.invocation_id)
| summarize concurrent = count() by bin(timestamp, 10s)
| where concurrent > 1
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az functionapp create \
  --name func-timer-overlap \
  --resource-group rg-timer-overlap \
  --consumption-plan-location koreacentral \
  --runtime python \
  --runtime-version 3.11 \
  --storage-account satimeroverlap
```

### 8.2 Application

```python
import azure.functions as func
import logging, time, os

app = func.FunctionApp()

@app.timer_trigger(schedule="*/30 * * * * *", run_on_startup=False, use_monitor=True)
def timer_overlap_test(mytimer: func.TimerRequest) -> None:
    duration = int(os.environ.get("SLEEP_SECONDS", "5"))
    logging.info(f"Timer function started, will sleep {duration}s")
    time.sleep(duration)
    logging.info("Timer function completed")
```

### 8.3 Scenarios

**S1 — Normal (5s sleep, 30s interval)**: Function completes before next schedule. Verify exactly 1 invocation per 30s.

**S2 — Overlap condition (60s sleep, 30s interval)**: Function takes 60s, next schedule fires at 30s. Verify singleton prevents overlap — second invocation is skipped.

**S3 — RunOnStartup=true**: Restart the function app. Verify function fires immediately on startup in addition to scheduled time.

**S4 — Scale-out test**: Allow scale to 2 instances. Verify only one instance executes per schedule interval.

**S5 — Schedule recovery**: Stop all instances for 5 minutes (scale to 0 or disable). Re-enable. Observe whether missed schedules are executed immediately on recovery.

## 9. Expected signal

- **S1**: 1 invocation per 30s.
- **S2**: Singleton prevents overlap — invocation count is 1 per 60s (one execution per 2 schedule intervals). No concurrent invocations.
- **S3**: Invocation fires at t=0 (startup) and at next scheduled time.
- **S4**: Exactly 1 invocation per schedule interval across all instances.
- **S5**: On recovery, schedule monitor detects missed intervals and executes once (not per missed interval).

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Singleton lease behavior depends on Azure Storage availability. If Storage is degraded, lease acquisition may fail and duplicates can occur.
- Python is single-threaded per worker — concurrent invocations require separate worker processes.
- Flex Consumption plan timer behavior may differ from Consumption.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Singleton lease prevents overlap within single instance | **Strongly Suggested** (documented behavior) |
| Scale-out does not cause duplicate invocations | **Strongly Suggested** (distributed singleton via Storage) |
| RunOnStartup fires on every host restart | **Strongly Suggested** (well-documented) |
| Schedule recovery executes once for all missed intervals | **Unknown** |

## 14. Related experiments

- [Cold Start (Functions)](../cold-start/overview.md) — host startup timing and schedule interaction
- [Job Execution Failures (Container Apps)](../../container-apps/liveness-probe-failures/overview.md) — Container Apps cron job overlap behavior

## 15. References

- [Timer trigger in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer)
- [Singleton support in Durable Functions](https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-singletons)
- [Timer trigger schedule expressions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer?tabs=python-v2#ncrontab-expressions)

## 16. Support takeaway

For timer function overlap and scheduling issues:

1. The distributed singleton lease (in Azure Storage `azure-webjobs-hosts`) is the primary overlap prevention mechanism. If a function is running double, check whether Storage connectivity was degraded when the lease should have been acquired.
2. `RunOnStartup: true` fires on EVERY host start — cold start, restart, deployment. Remove this flag from production functions unless immediate-on-start behavior is intentional.
3. If a timer function appears to run twice after scale-out, verify the singleton is working by checking App Insights for overlapping invocation timestamps and checking the Storage table for lease entries.
4. Missed schedule recovery: the Functions host tracks the last execution time. On recovery, it checks whether the previous scheduled interval was missed and fires once to catch up.
5. For business-critical timer workloads, add idempotency to the function body — even with singleton protection, distributed system edge cases (lease expiry during network partition) can cause occasional duplicates.
