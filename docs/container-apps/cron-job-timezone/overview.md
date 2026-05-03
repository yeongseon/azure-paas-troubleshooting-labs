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

# Cron Job Timezone Drift in Container Apps Jobs

!!! info "Status: Planned"

## 1. Question

Container Apps Jobs with cron-based schedules use UTC by default for the cron expression. When a job is configured with a cron expression intended for a local timezone (e.g., `0 9 * * *` intended as "9 AM KST = 0 AM UTC"), but the cron engine evaluates in UTC, the job fires at the wrong local time. What is the observable drift, and is there a way to configure timezone-aware cron schedules?

## 2. Why this matters

Business-critical scheduled jobs (daily reports, data exports, maintenance windows) are often defined with local business hours in mind. When the cron expression is written for local time but executed in UTC, the job fires 9 hours earlier or later than intended. This is a silent misconfiguration: the job runs successfully at the wrong time, and the error may only be noticed when stakeholders report missing or late outputs. The issue is amplified by daylight saving time transitions for regions that observe DST.

## 3. Customer symptom

"The daily report job runs at 9 AM UTC instead of 9 AM KST" or "The scheduled job fires at the wrong time but the cron expression looks correct" or "After daylight saving time started, the job started running 1 hour off."

## 4. Hypothesis

- H1: Container Apps Jobs cron schedules are evaluated in UTC. A cron expression `0 9 * * *` (9:00 AM) fires at 9:00 AM UTC = 6:00 PM KST, not 9:00 AM KST.
- H2: There is no built-in timezone configuration for Container Apps Jobs cron schedules (as of 2026). The correct workaround is to convert local time to UTC in the cron expression.
- H3: When DST transitions occur, a UTC-converted cron expression for a DST-observing timezone (e.g., `America/New_York`) is off by 1 hour for 6 months of the year if the UTC offset is not manually updated.
- H4: Non-DST-observing timezones (e.g., `Asia/Seoul`, UTC+9 always) are unaffected by DST but still require UTC conversion in the cron expression.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps Jobs |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Platform behavior

**Controlled:**

- Container Apps Job with cron schedule `*/2 * * * *` (every 2 minutes for testing)
- Job container that logs execution timestamp with both UTC and KST times

**Observed:**

- Actual execution time vs. cron schedule expectation
- UTC offset of execution time

**Scenarios:**

- S1: Cron `0 0 * * *` (intended: midnight UTC = 9 AM KST) → fires at midnight UTC
- S2: Cron `0 0 * * *` with job logging local time → confirm UTC evaluation
- S3: Convert to correct UTC equivalent for "9 AM KST" → cron `0 0 * * *` → correct (KST = UTC+9, so 9 AM KST = 0 AM UTC, which happens to work)

## 7. Instrumentation

- Container Apps Job execution history (`az containerapp job execution list`)
- Job container log output: `print(f"UTC: {datetime.utcnow()}, Local: {datetime.now()}")`
- Azure Monitor Job execution timestamps

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy a Container Apps Job with cron `*/5 * * * *` (every 5 minutes); job logs UTC and `TZ=Asia/Seoul` local time.
2. Observe execution times; confirm the 5-minute interval fires at expected UTC minutes.
3. Set cron to `0 9 * * *` (intended as 9 AM KST = 0 AM UTC); let it run overnight; verify it fires at 9:00 AM UTC (= 6:00 PM KST the previous day in Korea).
4. Document the correct UTC conversion for common business-hour schedules.

## 9. Expected signal

- Job executions occur at the cron-specified UTC times, not at the intended local time.
- The `TZ` environment variable in the job container does not affect the cron evaluation schedule (which is platform-side).
- Execution timestamps in the job history show UTC times.

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

- Container Apps Jobs cron format: `<minute> <hour> <day-of-month> <month> <day-of-week>` — standard cron, UTC timezone.
- Conversion: for KST (UTC+9), subtract 9 hours from local time to get UTC. "9 AM KST" = "0 AM UTC" = cron `0 0 * * *`.
- There is no official timezone parameter for Container Apps Jobs cron as of the time of this experiment. Check release notes for updates.

## 16. Related guide / official docs

- [Container Apps Jobs: scheduling](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Cron expression format](https://en.wikipedia.org/wiki/Cron#Overview)
