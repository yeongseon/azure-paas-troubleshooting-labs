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

# Container Apps Jobs: Execution Failures, Timeout Behavior, and Retry Semantics

!!! info "Status: Planned"

## 1. Question

When a Container Apps Job fails mid-execution — due to a non-zero exit code, a timeout, or an OOM kill — how is the failure reflected in job execution history, what retry behavior does the platform apply, and how do event-triggered jobs differ from scheduled jobs in their failure and retry semantics?

## 2. Why this matters

Container Apps Jobs are distinct from Container Apps services: they run to completion rather than serving continuous traffic. When a job execution fails, the platform may retry automatically — but the retry count, backoff, and termination conditions are not always visible to operators. A job that appears to be "running" in the portal may actually be in a retry loop after repeated failures. Timeout-induced failures produce a different exit signal than application crashes, but both may appear identically in execution history. Support engineers investigating stuck or looping jobs need to distinguish between platform-level retries, job-level failures, and OOM kills.

## 3. Customer symptom

"My Container App Job shows as Failed but I can't find where the error is" or "The job keeps running forever and never completes" or "I see multiple executions of the same scheduled job — is it retrying or duplicating?" or "The job was OOM-killed but the exit code shows 1, not 137."

## 4. Hypothesis

- H1: A Container Apps Job execution that exits with a non-zero code is marked as `Failed` in execution history. If `replicaRetryLimit` is greater than 0, the platform retries the execution up to that limit. Each retry appears as a separate execution event in `ContainerAppSystemLogs`, not as a sub-event of the original execution.
- H2: A job execution that exceeds `replicaTimeout` is terminated by the platform. The termination appears in execution history as a `Failed` execution with a timeout-related reason. The container exit code may be 143 (SIGTERM) rather than a non-zero application exit code.
- H3: A scheduled job (cron trigger) that is still running when its next scheduled execution is due will have the new execution queued. Whether the new execution starts immediately or waits depends on the `parallelism` setting. If `parallelism=1`, the second execution waits; the job does not duplicate.
- H4: An event-triggered job (e.g., KEDA-based queue trigger) consumes one message per execution. If the execution fails and the message is not explicitly deleted from the queue, the message becomes visible again after the queue's visibility timeout, and a new job execution is triggered — creating a retry loop from the queue, not from the job's own retry mechanism.

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

**Experiment type**: Reliability / Jobs

**Controlled:**

- Container Apps Job (manual, scheduled, and event-triggered variants)
- Job image: Python script with configurable exit code, sleep duration, and memory allocation
- `replicaRetryLimit`: 0 (no retry) and 3 (retry)
- `replicaTimeout`: 30 seconds

**Observed:**

- Job execution history: status, start time, end time, exit code per execution
- `ContainerAppSystemLogs` entries per execution and per retry
- Exit code for timeout-terminated vs. OOM-killed vs. application-crash executions
- Queue message visibility after failed event-triggered execution

**Scenarios:**

- S1: Manual job exits with code 1 — no retry (`replicaRetryLimit=0`)
- S2: Manual job exits with code 1 — with retry (`replicaRetryLimit=3`)
- S3: Job exceeds `replicaTimeout` (60-second sleep, 30-second timeout)
- S4: Scheduled job (every 1 minute) with 90-second execution — observe queuing behavior
- S5: Event-triggered job (Storage Queue) — execution fails without deleting message — observe re-trigger

**Independent run definition**: One job trigger per scenario; observe for 10 minutes.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `az containerapp job execution list --name <job> --resource-group <rg>` — execution history with status and timestamps
- `ContainerAppSystemLogs` KQL: `| where ContainerAppName == "<job-name>"` — system events per execution
- Exit code: `az containerapp job execution show --execution-name <exec> --query "properties.status"` — execution result details
- Storage Queue: Azure Portal > Queue > Peek messages — message visibility state after failed execution
- Time measurement: job trigger timestamp → `Failed` status appears in execution list

## 8. Procedure

_To be defined during execution._

### Sketch

1. S1: Trigger manual job with exit code 1, `replicaRetryLimit=0`; confirm single `Failed` execution in history; no retry.
2. S2: Set `replicaRetryLimit=3`; trigger same job; observe 4 total executions (1 original + 3 retries); confirm each appears as a separate event in system log.
3. S3: Set job sleep to 60 seconds, `replicaTimeout=30`; trigger; observe execution terminated at ~30 seconds; record exit code (expect SIGTERM → 143 in container).
4. S4: Configure cron schedule `*/1 * * * *` (every minute); set job sleep to 90 seconds; observe second scheduled execution after 60 seconds — does it queue or duplicate?
5. S5: Configure Storage Queue trigger; enqueue one message; let execution fail without deleting the message; observe whether the message re-triggers a new execution after queue visibility timeout.

## 9. Expected signal

- S1: One `Failed` execution; no additional executions in history.
- S2: Four executions total (1 + 3 retries); each in system log as a separate event; final status `Failed` after all retries exhausted.
- S3: Execution terminated at timeout; exit code in container may be 143 (SIGTERM); execution history shows `Failed` with a timeout-related reason.
- S4: Second scheduled execution is queued and starts after first execution completes (if `parallelism=1`); no duplication — two separate sequential executions.
- S5: Failed execution leaves the message visible after queue's visibility timeout; new execution triggered by KEDA; creates a retry loop until the message is explicitly deleted or moves to dead-letter queue.

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

- Container Apps Jobs execution history is available via `az containerapp job execution list`; the portal shows a summarized view. Use the CLI for exit code details.
- `replicaTimeout` is in seconds; the default is no timeout (unlimited). Always set a timeout for production jobs to prevent stuck executions from consuming resources indefinitely.
- For event-triggered jobs, message deletion responsibility lies with the application, not the platform. If the application exits before deleting the message, the message will re-trigger a new execution — this is by design for at-least-once processing but can cause unintended retry loops.
- OOM-killed containers typically exit with code 137 (SIGKILL); timeout-terminated containers exit with 143 (SIGTERM) if the application handles SIGTERM, or 137 if the timeout is enforced with SIGKILL after a grace period.

## 16. Related guide / official docs

- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Create a job with Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs-get-started-cli)
- [KEDA scalers for event-driven jobs](https://keda.sh/docs/scalers/)
- [Monitor jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/monitor)
