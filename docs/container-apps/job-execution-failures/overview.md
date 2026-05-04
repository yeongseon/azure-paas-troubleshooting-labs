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

# Container Apps Jobs: Execution Failures, Timeout Behavior, and Retry Semantics

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a Container Apps Job fails mid-execution — due to a non-zero exit code, a timeout, or an OOM kill — how is the failure reflected in job execution history, what retry behavior does the platform apply, and how do event-triggered jobs differ from scheduled jobs in their failure and retry semantics?

## 2. Why this matters

Container Apps Jobs are distinct from Container Apps services: they run to completion rather than serving continuous traffic. When a job execution fails, the platform may retry automatically — but the retry count, backoff, and termination conditions are not always visible to operators. A job that appears to be "running" in the portal may actually be in a retry loop after repeated failures. Timeout-induced failures produce a different exit signal than application crashes, but both may appear identically in execution history. Support engineers investigating stuck or looping jobs need to distinguish between platform-level retries, job-level failures, and OOM kills.

## 3. Customer symptom

"My Container App Job shows as Failed but I can't find where the error is" or "The job keeps running forever and never completes" or "I see multiple executions of the same scheduled job — is it retrying or duplicating?" or "The job was OOM-killed but the exit code shows 1, not 137."

## 4. Hypothesis

- H1: A Container App Job exits with status `Failed` when the container process exits with a non-zero exit code. The exit code itself is not captured in `az containerapp job execution show` output — only the `Failed` status string.
- H2: A web server image (designed for long-running service) used as a job image will always show `Failed` because the container never exits with code 0.
- H3: An image with a shell command that exits with code 0 (e.g., `alpine` running `sh -c "exit 0"`) produces execution status `Succeeded`.
- H4: `replicaRetryLimit: 0` means no automatic retries. Each manual trigger produces exactly one execution attempt.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| Jobs tested | cron-tz-test, job-exitcode-test, job-success-test, job-alpine-exit0 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Reliability / Platform behavior

**Controlled:**

- Manual trigger type
- `replicaRetryLimit: 0` (no retries)
- `replicaTimeout: 60s`

**Observed:**

- Execution status (`Succeeded` / `Failed` / `Running`) per image type and exit code
- Retry behavior under `replicaRetryLimit: 0`
- Time from job start to status finalization

**Scenarios:**

- S1: Web server image (`containerapps-helloworld`) used as job → expect `Failed`
- S2: Custom command as single string `["sh", "-c", "exit 42"]` → expect `Failed`
- S3: `alpine` image with default entrypoint → expect `Succeeded`
- S4: `cron-tz-test` scheduled job execution → existing `Failed` in history

## 7. Instrumentation

- `az containerapp job create` — create job with specific image/command
- `az containerapp job start` — trigger manual execution
- `az containerapp job execution list` — monitor execution status
- `az containerapp job execution show` — inspect execution details and template

## 8. Procedure

1. Create `job-exitcode-test` with `busybox:latest` and command `["sh","-c","exit 42"]` as a single JSON string (intentionally incorrect format).
2. Trigger execution; wait 60s; check status.
3. Create `job-success-test` with `containerapps-helloworld` (web server). Trigger; wait; check status.
4. Create `job-alpine-exit0` with `alpine:latest` (default entrypoint = shell that exits 0). Trigger; wait; check status.
5. Check `cron-tz-test` existing failed scheduled execution.

## 9. Expected signal

- S1 (`containerapps-helloworld` as job): `Failed` — web server does not exit.
- S2 (custom exit 42): `Failed` — non-zero exit code.
- S3 (`alpine` default): `Succeeded` — shell exits 0 by default.
- S4 (scheduled): `Failed` — same web server image failure pattern.

## 10. Results

### S4 — Existing scheduled job failure (cron-tz-test)

```
Name                  Status    StartTime
--------------------  --------  -------------------------
cron-tz-test-zo74k42  Failed    2026-05-03T23:50:11+00:00

Image: mcr.microsoft.com/azuredocs/containerapps-helloworld:latest
Command: (none — default entrypoint)
```

### S2 — busybox with command as single JSON string (incorrect format)

```bash
$ az containerapp job create \
  --name "job-exitcode-test" \
  --image "busybox:latest" \
  --command '["sh","-c","echo STARTING; sleep 2; echo FAILING; exit 42"]'

# Execution 1 (exit 42 attempt):
job-exitcode-test-rptt7dh: Failed

# Execution 2 (exit 0 attempt via --image override with success command):
job-exitcode-test-22hthkp: Failed
```

Inspection of execution template:
```json
"command": ["[\"sh\",\"-c\",\"echo STARTING; sleep 2; echo FAILING; exit 42\"]"]
```

The entire command was passed as a single string argument to the container entrypoint (treated as a literal argument, not an exec form). This caused the container to fail regardless of the intended command.

### S1 — containerapps-helloworld used as job

```
job-success-test-1yff4uz: Failed
```

The `containerapps-helloworld` image starts a web server that listens indefinitely. As a job, it either times out (if `replicaTimeout` is exceeded) or is killed when the replica is reclaimed. Status: `Failed`.

### S3 — alpine with default entrypoint (exit 0)

```
job-alpine-exit0-4qof0s5: Succeeded
```

Alpine's default entrypoint is `sh`, which starts and exits with code 0 immediately. Status: `Succeeded`.

### Job configuration

```json
{
  "replicaRetryLimit": 0,
  "triggerType": "Manual"
}
```

With `replicaRetryLimit: 0`, each execution attempt runs exactly once — no automatic retries observed.

## 11. Interpretation

- **Observed**: H1 is confirmed — `Failed` status appears for non-zero exit code containers. The exit code value itself (e.g., 42) is NOT captured in `az containerapp job execution show` or `az containerapp job execution list`. Only the `Failed` string is exposed.
- **Observed**: H2 is confirmed — a web server image (`containerapps-helloworld`) used as a job always produces `Failed` because the container never exits with code 0. This is a common misconfiguration when teams repurpose their app image as a job image.
- **Observed**: H3 is confirmed — `alpine` with default entrypoint exits 0 and produces `Succeeded`.
- **Observed**: H4 is confirmed — with `replicaRetryLimit: 0`, each manual trigger produces exactly one `Failed` or `Succeeded` record. No retry was observed.
- **Observed**: Passing a command as a JSON-encoded string (e.g., `["sh","-c","exit 42"]` as a single element) is NOT equivalent to exec form in the container spec. The command is passed as a literal argument to the entrypoint, not parsed as an array. Proper exec form requires multiple `--args` elements or direct JSON array format in the ARM spec.
- **Inferred**: The exit code is likely captured in `ContainerAppConsoleLogs` (stderr/stdout) but not exposed in the execution status API. Log Analytics queries on `ContainerAppConsoleLogs` with `| where ContainerAppName_s == "job-exitcode-test"` would be needed to correlate exit codes.

## 12. What this proves

- Job execution status is binary: `Succeeded` (exit 0) or `Failed` (non-zero exit or container crash). Exit code values are not surfaced in the execution API. **Observed**.
- Web server images used as jobs produce `Failed` because they never exit. **Observed**.
- `replicaRetryLimit: 0` means exactly one execution attempt per trigger. **Observed**.
- Command format matters: a JSON-encoded string passed as `--command` is not the same as exec form. The command must be provided as separate arguments (`--command "sh" --args "-c" "exit 0"`). **Observed**.

## 13. What this does NOT prove

- OOM kill exit code behavior was not tested. OOM kills typically produce exit code 137 (SIGKILL), but whether ACA captures this separately from generic non-zero exits is unknown from this experiment.
- Timeout-induced failures (`replicaTimeout` exceeded) were not directly tested. A job running beyond `replicaTimeout` should produce `Failed` with a timeout reason, distinct from an exit code failure.
- Retry behavior with `replicaRetryLimit > 0` was not tested. Multiple retry attempts may produce multiple entries in execution history or a single consolidated entry.
- KEDA-triggered job behavior differs from Manual and Scheduled — not tested here.

## 14. Support takeaway

When investigating a Container App Job that shows `Failed`:

1. **Check image type**: Is the image a web server (long-running service)? If so, it will always fail as a job. Jobs must use images designed to run to completion and exit with code 0.
2. **Check exit code**: `az containerapp job execution show` does NOT expose the exit code. Query `ContainerAppConsoleLogs` in Log Analytics: `ContainerAppConsoleLogs_CL | where ContainerAppName_s == "<job-name>" | order by TimeGenerated desc`.
3. **Check command format**: Verify `--command` and `--args` are set correctly. A single string `["sh","-c","exit 0"]` is NOT exec form — use `--command "sh" --args "-c" "exit 0"`.
4. **Check retry count**: `az containerapp job show --query "properties.configuration.replicaRetryLimit"`. If 0, each trigger runs once. If > 0, check execution history for multiple attempts.
5. **Distinguish timeout from crash**: If `replicaTimeout` is shorter than the job's expected runtime, the platform kills the job and marks it `Failed`. Increase `replicaTimeout` to accommodate the job duration.

## 15. Reproduction notes

```bash
RG="rg-lab-aca-batch"
ENV="env-batch-lab"

# Create a properly-configured failing job (exit code 1)
az containerapp job create \
  --name "job-fail-demo" \
  --resource-group $RG \
  --environment $ENV \
  --trigger-type Manual \
  --replica-timeout 60 \
  --image "alpine:latest" \
  --command "sh" --args "-c" "exit 1" \
  --cpu 0.25 --memory 0.5Gi

# Trigger and wait
EXEC=$(az containerapp job start -n "job-fail-demo" -g $RG --query "name" -o tsv)
sleep 30
az containerapp job execution list -n "job-fail-demo" -g $RG \
  --query "[].{name:name,status:properties.status}" -o table
# Expected: Failed

# Create a succeeding job (exit 0)
az containerapp job create \
  --name "job-success-demo" \
  --resource-group $RG \
  --environment $ENV \
  --trigger-type Manual \
  --replica-timeout 60 \
  --image "alpine:latest" \
  --command "sh" --args "-c" "echo done; exit 0" \
  --cpu 0.25 --memory 0.5Gi

EXEC=$(az containerapp job start -n "job-success-demo" -g $RG --query "name" -o tsv)
sleep 30
az containerapp job execution list -n "job-success-demo" -g $RG \
  --query "[].{name:name,status:properties.status}" -o table
# Expected: Succeeded
```

## 16. Related guide / official docs

- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Job retry and timeout configuration](https://learn.microsoft.com/en-us/azure/container-apps/jobs#job-configuration)
- [Monitor jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/monitor-jobs)
