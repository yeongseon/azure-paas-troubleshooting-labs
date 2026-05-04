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

# Container Memory OOM Kill: Process SIGKILL Without Application Exception

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04. Adapted from JVM-specific design to runtime-agnostic container memory limit test using Python/gunicorn.

## 1. Question

When a Container Apps container allocates memory that exceeds the cgroup memory limit, how does the failure manifest — as an application-level exception or as an external SIGKILL from the OOM killer? Is the event visible in Container Apps logs, and does the container restart automatically?

## 2. Why this matters

Container memory limits are enforced by Linux cgroups. When a process inside the container exceeds the limit, the kernel OOM killer sends SIGKILL to a process in the cgroup — the application never gets to throw an exception or log an error before it is terminated. This confuses developers who expect to catch or log out-of-memory conditions: for Java apps, `OutOfMemoryError` never appears; for Python apps, there is no `MemoryError`; for Node.js, no `heap out of memory` — the process is simply killed. The only evidence is in the container runtime logs or gunicorn/supervisor supervisor output.

## 3. Customer symptom

"The container crashes with no error message" or "No exception in logs but the container restarts randomly" or "Workers keep dying and respawning — gunicorn says 'Perhaps out of memory?'" or "The app is running but requests return connection reset errors."

## 4. Hypothesis

- H1: When a container allocates memory exceeding the cgroup limit (container memory limit), the process is terminated with SIGKILL by the OOM killer — no application-level exception is raised or logged.
- H2: The OOM kill is visible in `ContainerAppConsoleLogs` as a gunicorn error: `Worker (pid:N) was sent SIGKILL! Perhaps out of memory?` — the worker restarts automatically, and the gunicorn master process survives.
- H3: For a request that triggers the OOM kill, the HTTP client receives `upstream connect error or disconnect/reset before headers` — the connection is terminated mid-request with no HTTP response code.
- H4: The container itself does not restart (only the gunicorn worker process dies and respawns); the replica remains `Running` throughout.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| App name | aca-diag-batch |
| Revision | aca-diag-batch--v3c |
| Runtime | Python 3.11 / gunicorn (4 workers) |
| Container memory limit | 0.5Gi (512 MB) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Runtime / Resource limits

**Controlled:**

- Container memory limit: 0.5Gi (512 MB)
- Container CPU limit: 0.25 vCPU
- `/allocate?mb=N` endpoint allocates N MB as `bytearray` and holds it in process memory
- `/allocate/reset` endpoint releases all held memory

**Observed:**

- HTTP response from `/allocate?mb=450` (exceeds per-worker memory headroom)
- `ContainerAppConsoleLogs` for gunicorn worker kill messages
- Replica `runningState` (container-level vs process-level failure)

## 7. Instrumentation

- `curl /allocate?mb=450` — trigger per-worker memory overflow
- `az containerapp logs show --type console` — observe gunicorn SIGKILL messages
- `az containerapp replica list` — confirm container stays Running

## 8. Procedure

1. Deploy Python/gunicorn app with `/allocate?mb=N` endpoint; container limit 0.5Gi.
2. Send `GET /allocate?mb=450` — allocates 450 MB in one gunicorn worker (exceeds cgroup per-worker headroom).
3. Observe HTTP client error and gunicorn console logs.
4. Confirm container replica stays Running (only worker process is killed and restarted).

## 9. Expected signal

- HTTP client: connection termination / reset (no HTTP status code).
- `ContainerAppConsoleLogs`: `Worker (pid:N) was sent SIGKILL! Perhaps out of memory?`
- Container replica: stays `Running` (gunicorn master respawns killed workers).
- No `MemoryError` Python exception in logs.

## 10. Results

### Memory allocation triggering OOM kill

```bash
curl -s "https://aca-diag-batch.../allocate?mb=450" --max-time 30

→ upstream connect error or disconnect/reset before headers.
  retried and the latest reset reason: connection termination
```

The HTTP client received a connection reset with no HTTP status code. The process was killed before it could write a response.

### ContainerAppConsoleLogs — gunicorn worker kill events

```json
{"TimeStamp": "2026-05-04T05:42:09.0536422+00:00",
 "Log": "[ERROR] Worker (pid:20) was sent SIGKILL! Perhaps out of memory?"}

{"TimeStamp": "2026-05-04T05:42:09.0584578+00:00",
 "Log": "[INFO] Booting worker with pid: 26"}

{"TimeStamp": "2026-05-04T05:42:10.8872476+00:00",
 "Log": "[ERROR] Worker (pid:16) was sent SIGKILL! Perhaps out of memory?"}

{"TimeStamp": "2026-05-04T05:42:12.4144501+00:00",
 "Log": "[ERROR] Worker (pid:24) was sent SIGKILL! Perhaps out of memory?"}

{"TimeStamp": "2026-05-04T05:42:13.9183418+00:00",
 "Log": "[ERROR] Worker (pid:22) was sent SIGKILL! Perhaps out of memory?"}
```

Multiple workers were killed in rapid succession. Gunicorn master (pid:1) survived and respawned each worker immediately.

### Cascade pattern

The first `/allocate?mb=450` request was routed to one worker. That worker was OOM-killed. Gunicorn respawned it. The next `/allocate?mb=450` request (retry) was routed to a different worker, which was also OOM-killed. This cascaded through all 4 workers.

### Container replica state (throughout experiment)

```bash
az containerapp replica list ... --query "[0].properties.runningState"
→ "Running"
```

The container (replica) never restarted. Only individual gunicorn worker processes were killed and respawned.

### No Python MemoryError in logs

```
# Search of ContainerAppConsoleLogs for "MemoryError", "Traceback", "Exception":
# → 0 results
```

Python never raised `MemoryError`. The process was killed externally by the OOM killer before Python's memory allocator returned control to application code.

## 11. Interpretation

- **Measured**: H1 is confirmed. Allocating 450 MB in a single worker process (within a 0.5Gi container limit shared with other processes) triggers an OOM kill — no Python `MemoryError` is raised, no HTTP response is returned. **Measured**.
- **Measured**: H2 is confirmed. `ContainerAppConsoleLogs` shows `Worker (pid:N) was sent SIGKILL! Perhaps out of memory?` for multiple worker PIDs. The gunicorn master process survives and respawns workers. **Measured**.
- **Measured**: H3 is confirmed. The HTTP client receives `upstream connect error... connection termination` — the connection is reset with no HTTP status code. **Measured**.
- **Measured**: H4 is confirmed. The replica `runningState` remains `Running` throughout. The container-level restart count does not increment — only process-level kills occur. **Measured**.

## 12. What this proves

- cgroup OOM kills terminate processes with SIGKILL without raising application-level exceptions. Python does not raise `MemoryError`, Java does not throw `OutOfMemoryError` — the process is externally killed. **Measured** (Python case).
- `ContainerAppConsoleLogs` captures `Worker (pid:N) was sent SIGKILL! Perhaps out of memory?` — this is the primary diagnostic signal for gunicorn OOM events. **Measured**.
- HTTP clients receive connection reset (no HTTP status code) when a worker is OOM-killed mid-request. **Measured**.
- Gunicorn worker process kills do not cause container-level restart — the replica stays `Running`. **Measured**.

## 13. What this does NOT prove

- Java-specific behavior (`OutOfMemoryError` vs. OOM kill threshold, off-heap memory interaction with `-Xmx`) was not tested in this experiment.
- Whether `ContainerAppSystemLogs` shows exit code 137 (SIGKILL) for this case was not confirmed — the system logs did not show a container-level OOM event (only process-level).
- Whether single-process containers (no supervisor) produce different restart behavior was not tested.
- Memory metrics (`ContainerAppSystemLogs_CL` via Log Analytics) were not checked — Log Analytics workspace was not configured on this environment.

## 14. Support takeaway

When a customer reports "container crashes with no error" or "workers keep dying and respawning":

1. **Check `ContainerAppConsoleLogs`** for `SIGKILL! Perhaps out of memory?` — this is the gunicorn OOM indicator. For other runtimes, look for similar supervisor kill messages.
2. **No application exception = OOM kill**. If there is no `MemoryError` / `OutOfMemoryError` / crash log, the process was killed externally by the cgroup OOM killer.
3. **Client sees connection reset** — requests routed to an OOM-killed worker receive `connection termination` or TCP RST. This appears as a 502 or connection error on load balancers/clients.
4. **Container memory limit**: check `az containerapp show --query "properties.template.containers[0].resources.memory"`. For Python/gunicorn with N workers, each worker needs memory headroom: `container_limit / workers` is not exact — workers share memory pages but have independent heap allocations.
5. **Fix**: increase memory limit, reduce gunicorn worker count, or limit per-request memory usage. For Java: set `-XX:MaxRAMPercentage=75.0` instead of `-Xmx` at container limit.

## 15. Reproduction notes

```bash
APP="<aca-app-name>"
RG="<resource-group>"

# Deploy with low memory limit
az containerapp update -n $APP -g $RG --cpu 0.25 --memory 0.5Gi

# Add /allocate endpoint to app (allocates bytearray in process memory)
# Trigger OOM: request > available per-worker headroom
curl "https://<fqdn>/allocate?mb=450"
# Expected: "upstream connect error... connection termination"

# Check OOM evidence in console logs
az containerapp logs show -n $APP -g $RG --type console --tail 30 | \
  grep "SIGKILL\|out of memory"
# Expected: Worker (pid:N) was sent SIGKILL! Perhaps out of memory?

# Confirm container is still running
az containerapp replica list -n $APP -g $RG \
  --revision <latest-revision> --query "[0].properties.runningState" -o tsv
# Expected: Running
```

## 16. Related guide / official docs

- [Container Apps observability](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [Container Apps resource limits](https://learn.microsoft.com/en-us/azure/container-apps/containers)
- [Linux cgroup OOM killer](https://www.kernel.org/doc/html/latest/admin-guide/mm/oom_kill.html)
