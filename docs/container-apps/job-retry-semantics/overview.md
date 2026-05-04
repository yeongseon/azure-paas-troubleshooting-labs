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

# Container Apps Job Retry Semantics

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When a Container Apps Job fails (non-zero exit code, OOMKill, or timeout), what retry behavior does the platform apply? How does retry count interact with job concurrency limits, and what distinguishes a job "failure" from a job "timeout" in the logs and events?

## 2. Why this matters

Container Apps Jobs are increasingly used for batch processing, data pipelines, and scheduled tasks. The retry semantics are not always intuitive:
- A job that exits with code 0 on a partial result may appear "succeeded" even though it processed no data
- A job that is OOMKilled produces a different exit code than one that reaches its timeout
- Retry logic can cause jobs to re-process already-committed data if not handled carefully
- Event-triggered jobs (queue-based) have different retry semantics than scheduled (cron) jobs

## 3. Customer symptom

- "Our job ran 3 times and we ended up with duplicate records in the database."
- "The job says it succeeded but looking at the output it clearly didn't process all the records."
- "We set retryLimit=3 but the job only retried once."
- "How do I tell if a job was killed by OOM vs. exceeded the timeout?"

## 4. Hypothesis

**H1 — Exit code determines retry trigger**: A job retries only on non-zero exit code. Exit code 0 is always treated as success regardless of output or partial processing. Exit code 143 (SIGTERM, timeout) triggers a retry.

**H2 — OOMKill exit code is 137**: A container killed by the Linux OOM killer exits with code 137 (SIGKILL). This is distinguishable from timeout (143) or application error (1, 2, etc.) in job execution logs.

**H3 — Retry count is per execution, not per trigger**: For event-triggered jobs, each event trigger creates an independent execution. `retryLimit` applies to that single execution, not to the total number of times a message is processed.

**H4 — Concurrency limit blocks retry**: If `parallelism=1` and `retryLimit=3`, a failing job will retry but the retries run sequentially. The total execution time is `retryLimit × executionTimeout`.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| Job type | Manual, Scheduled, Event-triggered |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Job Behavior

**Controlled:**

- Exit code: 0, 1, 137 (OOMKill simulation), 143 (timeout simulation)
- `retryLimit`: 0, 1, 3
- Job type: manual, scheduled (cron), event-triggered (Storage Queue)
- `executionTimeout`: 30s, 60s

**Observed:**

- Number of execution attempts per trigger
- Exit code recorded in job execution history
- Time between retry attempts (backoff?)
- Event source re-processing behavior on event-triggered jobs

## 7. Instrumentation

- Job container: reads `EXIT_CODE` env var, exits with that code after logging
- For OOMKill simulation: allocate memory until killed
- For timeout: sleep for longer than `executionTimeout`
- Job execution history: `az containerapp job execution list`

**Execution history query:**

```bash
az containerapp job execution list \
  --name job-retry-test \
  --resource-group rg-job-retry \
  --query "[].{name:name, status:properties.status, startTime:properties.startTime, endTime:properties.endTime}"
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az containerapp job create \
  --name job-retry-test \
  --resource-group rg-job-retry \
  --environment env-job-retry \
  --image <job-image> \
  --replica-retry-limit 3 \
  --trigger-type Manual \
  --replica-timeout 60
```

### 8.2 Scenarios

**S1 — Exit 1, retryLimit 3**: Job exits with code 1 on every attempt. Verify exactly 3 retries (4 total executions). Record time between retries.

**S2 — Exit 0 after partial work**: Job logs "processed 0 records" but exits with code 0. Verify no retry. Documents the "false success" problem.

**S3 — OOMKill simulation**: Job allocates 2GB (exceeds container memory limit). Record exit code in execution history. Verify retries occur.

**S4 — Timeout**: Job sleeps for 90s with `executionTimeout=60s`. Record what exit code appears in execution history after timeout.

**S5 — Event-triggered retry**: Storage Queue message triggers job. Job fails. Verify whether the queue message becomes visible again (for reprocessing) or is dead-lettered.

## 9. Expected signal

- **S1**: 4 total executions (1 initial + 3 retries). Retry delay is near-immediate (no long backoff).
- **S2**: 1 execution, status Succeeded. No retry.
- **S3**: Exit code 137 in execution history. Retries occur.
- **S4**: Exit code 143 (SIGTERM on timeout) in history. Retries occur.
- **S5**: Queue message visibility timeout determines reprocessing; Container Apps does not dead-letter by default.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Job retry semantics may differ between scheduled, manual, and event-triggered job types.
- OOMKill simulation may be unreliable in test environments with large available memory headroom.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Exit 0 never retries | **Strongly Suggested** (standard container job semantics) |
| OOMKill exit code is 137 | **Strongly Suggested** (Linux SIGKILL standard) |
| Timeout exit code is 143 | **Inferred** (SIGTERM on timeout) |

## 14. Related experiments

- [Job Execution Failures](../liveness-probe-failures/overview.md) — job failure modes and observability
- [OOM Visibility Gap](../oom-visibility-gap/overview.md) — OOMKill observability in Container Apps

## 15. References

- [Container Apps Jobs documentation](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Job retry configuration](https://learn.microsoft.com/en-us/azure/container-apps/jobs?tabs=azure-cli#job-configuration)

## 16. Support takeaway

For Container Apps Job retry and failure issues:

1. The exit code is the single most important diagnostic signal. Exit 0 = success (no retry), exit 137 = OOMKill (will retry), exit 143 = timeout (will retry), exit 1+ = application error (will retry up to retryLimit).
2. A job that returns exit 0 is always treated as succeeded — there is no "succeeded but with errors" state. Applications must use non-zero exit codes to signal failure.
3. For event-triggered jobs, retry behavior interacts with the event source (Queue) — the message visibility timeout determines when it becomes re-processable. Container Apps does not control this.
4. OOMKill jobs don't receive SIGTERM — the process is killed immediately with SIGKILL. Graceful shutdown handlers don't run. Ensure jobs are idempotent.
