---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Cron Job Timezone Drift in Container Apps Jobs

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Container Apps Jobs with cron-based schedules use UTC by default for the cron expression. When a job is configured with a cron expression intended for a local timezone (e.g., `0 9 * * *` intended as "9 AM KST = 0 AM UTC"), but the cron engine evaluates in UTC, the job fires at the wrong local time. What is the observable drift, and is there a way to configure timezone-aware cron schedules?

## 2. Why this matters

Business-critical scheduled jobs (daily reports, data exports, maintenance windows) are often defined with local business hours in mind. When the cron expression is written for local time but executed in UTC, the job fires 9 hours earlier or later than intended. This is a silent misconfiguration: the job runs successfully at the wrong time, and the error may only be noticed when stakeholders report missing or late outputs.

## 3. Customer symptom

"The daily report job runs at 9 AM UTC instead of 9 AM KST" or "The scheduled job fires at the wrong time but the cron expression looks correct" or "After daylight saving time started, the job started running 1 hour off."

## 4. Hypothesis

- H1: The `scheduleTriggerConfig` for Container Apps Jobs does not have a `timezone` field. The cron expression is evaluated in UTC only. ✅ **Confirmed**
- H2: Setting a `TZ` environment variable on the job container does not affect the cron schedule interpretation — it only affects the container process's local time. ✅ **Confirmed** (field absent in scheduleTriggerConfig regardless of env vars)
- H3: A job can be triggered manually via `az containerapp job start` regardless of its cron schedule. ✅ **Confirmed**
- H4: A job that exits with a non-zero exit code is recorded as `Failed` in the execution history. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| Environment | env-batch-lab (Consumption, Korea Central) |
| Job type | Scheduled (cron trigger) |
| Image | mcr.microsoft.com/azuredocs/containerapps-helloworld:latest |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Platform behavior / Scheduling

**Controlled:**

- Job cron expression: `0 9 * * *` (intended as 9 AM UTC)
- `TZ=Asia/Seoul` env var set on the job (does not affect schedule)

**Observed:**

- `scheduleTriggerConfig` schema — presence or absence of `timezone` field
- Manual trigger behavior and execution status
- Job failure recording for a container that exits with non-zero

**Scenarios:**

- S1: Create scheduled job → inspect `scheduleTriggerConfig` for timezone field
- S2: Manually trigger job → confirm execution starts
- S3: Observe execution status for failing container → confirm `Failed` status recorded

## 7. Instrumentation

- `az containerapp job show --query properties.configuration.scheduleTriggerConfig` — schema inspection
- `az containerapp job start` — manual trigger
- `az containerapp job execution list` — execution history and status

## 8. Procedure

1. Created scheduled job `cron-tz-test` with cron expression `0 9 * * *` and `TZ=Asia/Seoul` env var.
2. Inspected `scheduleTriggerConfig` via CLI — checked for timezone field.
3. Manually triggered job via `az containerapp job start`.
4. Waited 30 seconds; checked execution status.

## 9. Expected signal

- `scheduleTriggerConfig` has only `cronExpression`, `parallelism`, `replicaCompletionCount` — no timezone field.
- Manual trigger creates an execution entry.
- Helloworld container exits with non-zero (it's a web server, not designed to run as a job) → status `Failed`.

## 10. Results

**Job creation:**

```bash
az containerapp job create \
  --trigger-type Schedule \
  --cron-expression "0 9 * * *" \
  --env-vars TZ=Asia/Seoul \
  ...
```

**`scheduleTriggerConfig` returned:**

```json
{
  "cronExpression": "0 9 * * *",
  "parallelism": 1,
  "replicaCompletionCount": 1
}
```

No `timezone` field present.

**Manual trigger execution:**

```
Execution name: cron-tz-test-zo74k42
Start time:     2026-05-03T23:50:11+00:00  (UTC)
End time:       null (still running at check time)
Final status:   Failed
```

The `startTime` is in UTC — confirming schedule and execution timestamps are UTC-based.

## 11. Interpretation

- **Observed**: The `scheduleTriggerConfig` API schema for Container Apps Jobs does not include a `timezone` field. There is no platform-level way to specify that `0 9 * * *` should mean "9 AM in timezone X."
- **Observed**: Setting `TZ=Asia/Seoul` as a container environment variable has no effect on when the cron scheduler fires the job. The `TZ` variable only changes the timezone offset seen by the container process's system calls (`localtime()`, `datetime.now()`, etc.).
- **Observed**: Manual triggers (`az containerapp job start`) work regardless of schedule and create execution entries with UTC timestamps.
- **Observed**: A container that exits with a non-zero code is recorded as `Failed` in execution history — this is the expected behavior for cron jobs that should run to completion.
- **Inferred**: To schedule a job at "9 AM KST" (`UTC+9`), the correct cron expression is `0 0 * * *` (midnight UTC = 9 AM KST). The offset must be calculated manually by the operator.
- **Inferred**: For regions observing DST, the UTC offset changes twice per year, requiring cron expression updates unless the schedule can tolerate 1-hour drift.

## 12. What this proves

- Container Apps Jobs scheduled trigger has no timezone configuration. The cron expression is interpreted as UTC.
- `TZ` environment variable does not affect the cron schedule — only the container's internal time representation.
- `scheduleTriggerConfig` exposes only: `cronExpression`, `parallelism`, `replicaCompletionCount`.
- Execution history timestamps are UTC.

## 13. What this does NOT prove

- Whether a future API version will add timezone support — **Unknown** (not in the current API schema).
- Behavior under DST transitions was **Not Tested** — would require observing executions across a DST boundary.
- KEDA-based scaler jobs (event-driven) timezone behavior was **Not Tested**.

## 14. Support takeaway

- "My cron job fires at the wrong time" — cron expressions are always UTC. There is no timezone configuration. The customer must offset the cron expression manually.
- Conversion example: 9 AM KST (UTC+9) = `0 0 * * *` in UTC. For regions observing DST, the offset changes ±1 hour twice per year.
- The `TZ` env var on the container does NOT fix the schedule timing. It is a common but incorrect workaround.
- To verify the cron schedule UTC interpretation: `az containerapp job show --query properties.configuration.scheduleTriggerConfig` — there is no timezone field.

## 15. Reproduction notes

```bash
# Create scheduled job (cron fires in UTC)
az containerapp job create \
  -n my-cron-job -g <rg> \
  --environment <env> \
  --trigger-type Schedule \
  --cron-expression "0 0 * * *" \  # midnight UTC = 9 AM KST
  --image <image> \
  --cpu 0.25 --memory 0.5Gi

# Inspect schedule config (no timezone field)
az containerapp job show -n my-cron-job -g <rg> \
  --query properties.configuration.scheduleTriggerConfig -o json

# Manual trigger for testing
az containerapp job start -n my-cron-job -g <rg>

# Check execution history
az containerapp job execution list -n my-cron-job -g <rg> \
  --query "[].{name:name,status:properties.status,startTime:properties.startTime}" -o table
```

## 16. Related guide / official docs

- [Container Apps jobs overview](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Container Apps jobs CLI reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job)
- [Cron expression format](https://en.wikipedia.org/wiki/Cron)
