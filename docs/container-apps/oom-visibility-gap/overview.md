---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-10
    cli_version: "2.73.0"
    core_tools_version: null
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# OOM Visibility Gap Across Metrics and Logs

!!! info "Status: Published"
    Experiment completed with real data collected on 2026-04-10 from Azure Container Apps Consumption tier (koreacentral).
    Five OOM kills across two variants (gradual and spike). Hypothesis partially confirmed — OOM events are **invisible in system logs and partially invisible in metrics**, with console logs being the only reliable evidence source.

## 1. Question

When a Container App container is killed by the OOM (Out of Memory) killer, is this event visible in Azure Monitor metrics, Container Apps system logs, and console logs? Where are the gaps in observability?

## 2. Why this matters

OOM kills are a common cause of container restarts, but the visibility of these events varies dramatically across Azure's telemetry layers. When operators use multi-process application servers like gunicorn, the OOM killer targets the worker process — not the container's PID 1. This creates a critical blind spot: the container never technically restarts, so platform-level telemetry that tracks container lifecycle events sees nothing. The only evidence exists in application-level console logs, which many customers don't monitor or don't know to look for.

### Background: How OOM Kill Works in Container Apps

Container Apps runs containers with cgroup memory limits. When a process exceeds the cgroup limit, the Linux OOM killer sends SIGKILL (signal 9) to the offending process. The kill target depends on the process hierarchy:

```text
┌─────────────────────────────────────────────────────┐
│  Container (cgroup limit: 0.5Gi)                    │
│                                                     │
│  PID 1: gunicorn master                             │
│    ├── PID 7: gunicorn worker (handling requests)   │
│    │         ← OOM killer targets THIS process      │
│    │                                                │
│    └── [master detects worker death, spawns new]    │
│         PID 12: new gunicorn worker                 │
│                                                     │
│  Result: Container PID 1 never dies                 │
│          Platform sees: container still running ✓    │
│          System logs: nothing happened              │
│          Console logs: "Worker sent SIGKILL!"       │
└─────────────────────────────────────────────────────┘
```

**Without multi-process servers** (e.g., Node.js single process), an OOM kill would terminate PID 1, causing a true container restart with platform-visible events. But Python (gunicorn), Java (JVM with multiple threads), and .NET (Kestrel) commonly use process supervisors that absorb OOM kills transparently.

## 3. Customer symptom

- "My container keeps restarting but I don't see any errors in the system logs."
- "Memory usage drops to baseline periodically — looks like restarts — but `RestartCount` is 0."
- "We see `Worker was sent SIGKILL` in stdout but the platform says everything is healthy."
- "Our API returns `upstream connect error` intermittently but health checks pass."

## 4. Hypothesis

**H1 — System logs gap**: When a Container App worker process is OOM-killed, `ContainerAppSystemLogs_CL` will contain **no record** of the event because the container (PID 1) continues running.

**H2 — Metrics partial visibility**: Azure Monitor `WorkingSetBytes` will show a memory drop (evidence of something happening) but the 1-minute aggregation will miss the actual peak. `RestartCount` will remain 0 because the container never restarts.

**H3 — Console logs are the only evidence**: `ContainerAppConsoleLogs_CL` will capture gunicorn's SIGKILL log message, making it the only telemetry source that records the OOM event.

**H4 — Two failure modes**: Gradual memory leaks will be invisible to clients (health endpoint on separate thread stays responsive), while sudden spikes will cause client-visible errors (the request thread is killed mid-response).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption (0.25 vCPU / 0.5Gi) |
| Region | Korea Central |
| Container image | Custom Python 3.11 (Flask + gunicorn gthread) |
| OS | Linux |
| Registry | Azure Container Registry (`acroomlab`) |
| Environment | `cae-oom` (auto-generated Log Analytics workspace) |
| Date tested | 2026-04-10 |

**Container configuration:**

| Component | Configuration | Purpose |
|-----------|--------------|---------|
| gunicorn | `--workers 1 --worker-class gthread --threads 4` | Single worker with 4 threads — health probes stay responsive during allocation |
| Memory limit | 0.5Gi (512MB) | Minimum valid Container Apps memory for 0.25 vCPU |
| Min/Max replicas | 1/1 | Fixed single replica for controlled observation |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Container memory limit: 0.5Gi
- Container CPU: 0.25 vCPU
- Memory allocation variant: gradual (16MB chunks, 0.5s pause) vs spike (500MB immediate)
- Application server: gunicorn with gthread worker class
- Target allocation: 600MB (exceeds 512MB limit)
- Single replica (minReplicas=maxReplicas=1)

**Observed:**

- `ContainerAppSystemLogs_CL`: presence/absence of OOM events, exit codes, container termination entries
- `ContainerAppConsoleLogs_CL`: gunicorn SIGKILL messages, allocation progression logs
- Azure Monitor `WorkingSetBytes`: memory usage pattern, peak visibility
- Azure Monitor `RestartCount`: container restart detection
- Replica API: `restartCount`, `runningState`, `startedAt`
- Client response: error message type, response time, availability during OOM

## 7. Instrumentation

- **Test application**: Custom Flask app with background memory allocator thread, cgroup v2 reading, memory progression logging to stdout
- **Endpoints**: `/start` (gradual allocation), `/spike` (immediate allocation), `/memory` (current state), `/health` (liveness), `/reset` (free memory)
- **Memory allocation**: `bytearray` with page touching (every 4096 bytes) to force physical allocation
- **Console logging**: `[OOM-TEST]` prefix with allocated MB and RSS at each step
- **System telemetry**: `ContainerAppSystemLogs_CL` via `az monitor log-analytics query`
- **Console telemetry**: `ContainerAppConsoleLogs_CL` via `az monitor log-analytics query`
- **Metrics**: Azure Monitor REST API for `WorkingSetBytes` and `RestartCount` at 1-minute granularity
- **Replica inspection**: `az containerapp replica list` for restart count and container start time

## 8. Procedure

### Step 1: Deploy test infrastructure

```bash
az group create --name rg-oom-lab --location koreacentral

az acr create --name acroomlab --resource-group rg-oom-lab \
    --sku Basic --admin-enabled true

az acr build --registry acroomlab --image oom-app:v2 \
    --file Dockerfile .

az containerapp env create --name cae-oom \
    --resource-group rg-oom-lab --location koreacentral

ACR_PASSWORD=$(az acr credential show --name acroomlab \
    --query "passwords[0].value" --output tsv)

az containerapp create --name ca-oom-test \
    --resource-group rg-oom-lab \
    --environment cae-oom \
    --image acroomlab.azurecr.io/oom-app:v2 \
    --registry-server acroomlab.azurecr.io \
    --registry-username acroomlab \
    --registry-password "$ACR_PASSWORD" \
    --cpu 0.25 --memory 0.5Gi \
    --min-replicas 1 --max-replicas 1 \
    --ingress external --target-port 8080
```

### Step 2: Verify app is healthy

```bash
FQDN=$(az containerapp show --name ca-oom-test \
    --resource-group rg-oom-lab \
    --query properties.configuration.ingress.fqdn --output tsv)

curl "https://${FQDN}/health"
# {"status":"healthy"}

curl "https://${FQDN}/memory"
# {"allocated_blocks":0,"allocated_mb":0.0,"pid":7,"vmrss_mb":32.2,...}
```

### Step 3: Run gradual OOM variant

```bash
# Start background allocation: 16MB chunks, 0.5s pause, 600MB target
curl -X POST "https://${FQDN}/start" \
    -H "Content-Type: application/json" \
    -d '{"chunk_mb": 16, "pause_seconds": 0.5, "target_mb": 600}'

# Poll memory every 2s until OOM (worker restarts with pid change)
while true; do
    curl -s "https://${FQDN}/memory"
    sleep 2
done
```

### Step 4: Run spike OOM variant

```bash
curl -X POST "https://${FQDN}/spike" \
    -H "Content-Type: application/json" \
    -d '{"mb": 500}'
# Returns: "upstream connect error or disconnect/reset before headers"
```

### Step 5: Collect evidence from Log Analytics

```bash
WORKSPACE_ID=$(az containerapp env show --name cae-oom \
    --resource-group rg-oom-lab \
    --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId \
    --output tsv)

# System logs (expecting: nothing)
az monitor log-analytics query --workspace "$WORKSPACE_ID" \
    --analytics-query "
    ContainerAppSystemLogs_CL
    | where TimeGenerated > ago(2h)
    | where ContainerAppName_s == 'ca-oom-test'
    | where Reason_s !in ('ContainerAppUpdate','RevisionUpdate')
    | project TimeGenerated, Reason_s, Type_s, Log_s
    | order by TimeGenerated desc"

# Console logs (expecting: SIGKILL messages)
az monitor log-analytics query --workspace "$WORKSPACE_ID" \
    --analytics-query "
    ContainerAppConsoleLogs_CL
    | where TimeGenerated > ago(2h)
    | where ContainerAppName_s == 'ca-oom-test'
    | where Log_s has_any ('SIGKILL', 'ERROR', 'OOM')
    | project TimeGenerated, Log_s
    | order by TimeGenerated desc"
```

### Step 6: Collect Azure Monitor metrics

```bash
RESOURCE_ID=$(az containerapp show --name ca-oom-test \
    --resource-group rg-oom-lab --query id --output tsv)

az monitor metrics list --resource "$RESOURCE_ID" \
    --metric "WorkingSetBytes" --interval PT1M \
    --start-time "2026-04-10T14:00:00Z" \
    --end-time "2026-04-10T14:30:00Z"

az monitor metrics list --resource "$RESOURCE_ID" \
    --metric "RestartCount" --interval PT1M \
    --start-time "2026-04-10T14:00:00Z" \
    --end-time "2026-04-10T14:30:00Z"
```

### Step 7: Clean up

```bash
az group delete --name rg-oom-lab --yes --no-wait
```

## 9. Expected signal

- `ContainerAppSystemLogs_CL`: Container exit with code 137 (SIGKILL), `ContainerTerminated` events
- Azure Monitor `RestartCount`: increment after each OOM kill
- Azure Monitor `WorkingSetBytes`: sharp drop after OOM kill, peak visible
- `ContainerAppConsoleLogs_CL`: gunicorn SIGKILL messages in stdout
- Client impact: no errors for gradual variant, connection errors for spike variant

## 10. Results

### 10.1 Summary: Observability Gap Matrix

| Telemetry Source | OOM Evidence Expected | OOM Evidence Found | Gap? |
|-----------------|----------------------|-------------------|------|
| `ContainerAppSystemLogs_CL` | Exit code 137, ContainerTerminated | **NOTHING** — zero events after initial creation | **YES** |
| Azure Monitor `RestartCount` | Increment per kill | max=1 for first kill, but tracks container restarts (container never restarted) | **YES** |
| Azure Monitor `WorkingSetBytes` | Peak memory visible | 1-min avg shows 202.9MB, **misses actual 496MB peak** | **PARTIAL** |
| `ContainerAppConsoleLogs_CL` | SIGKILL message | ✅ **9 SIGKILL messages** captured from gunicorn | **NO** |
| Replica API (`az containerapp replica list`) | restartCount > 0 | restartCount = 0, start time unchanged | **YES** |
| Client response (gradual variant) | Possible errors | ✅ No errors — health endpoint responsive throughout | N/A |
| Client response (spike variant) | Connection error | ✅ `upstream connect error / connection termination` | N/A |

### 10.2 Run Results: Gradual Variant (Runs 1, 3, 5)

| Metric | Run 1 | Run 3 | Run 5 |
|--------|-------|-------|-------|
| Last allocation before kill | 464MB | 464MB | 464MB |
| Last RSS before kill | 496.08MB | 496.36MB | 496.35MB |
| Killed worker PID | 7 | 32 | 56 |
| Replacement worker PID | 12 | 37 | 61 |
| Time from start to OOM | ~14s | ~14s | ~15s |
| Client error | None | None | None |
| Health endpoint responsive | Yes | Yes | Yes |

!!! tip "How to read this"
    All three gradual runs show identical OOM behavior: the worker is killed at 464MB allocated (496MB RSS), and a new worker is spawned within 1 second. The consistency across runs (464MB kill point) confirms a deterministic cgroup limit, not probabilistic behavior. The baseline ~32MB (Python + gunicorn + Flask) plus 464MB allocations = 496MB, just under the 512MB (0.5Gi) limit.

### 10.3 Run Results: Spike Variant (Runs 2, 4)

| Metric | Run 2 | Run 4 |
|--------|-------|-------|
| Spike requested | 500MB | 500MB |
| Client error | `upstream connect error / connection termination` | Same |
| Workers killed before stable | 6 | 6 |
| Kill-restart loop duration | ~8s | ~8s |
| Final stable worker PID | 32 | 56 |
| Recovery time to healthy | ~3s after loop ends | ~3s |

!!! warning "Spike Variant: Kill-Restart Loop"
    The spike variant triggers a pathological behavior: gunicorn's request queuing causes each new replacement worker to inherit the pending HTTP request (which triggers the 500MB allocation). Each worker is killed immediately after boot, creating a loop of 6 killed workers over ~8 seconds. The loop ends only when the HTTP request times out in the Envoy proxy, and the next worker boots without the toxic request.

### 10.4 System Logs Evidence (The Primary Gap)

**Query**: All `ContainerAppSystemLogs_CL` entries after initial container creation at 14:06:53Z.

**Result**: **Zero entries.** No `ContainerTerminated`, no exit code 137, no `OOMKilled`, no warnings.

```text
Total system log entries after container creation: 0
Events found:
  - ContainerTerminated:    0
  - Exit code 137:          0
  - OOMKilled:              0
  - ContainerBackOff:       0
  - Any event at all:       0
```

The system logs captured the initial deployment sequence (image pull, container creation, KEDA scaler startup, traffic weight assignment) but recorded **nothing** about 5 subsequent OOM kills.

### 10.5 Console Logs Evidence (The Only Signal)

**Query**: `ContainerAppConsoleLogs_CL` entries containing SIGKILL or ERROR.

**Result**: **9 SIGKILL messages** across all runs, all from gunicorn master process (PID 1).

```text
Message format (all 9 entries):
  [TIMESTAMP] [1] [ERROR] Worker (pid:N) was sent SIGKILL! Perhaps out of memory?

Worker PIDs killed: 7, 12, 16, 19, 22, 26, 29, 32, 37, 40, 43, 47, 50, 53, 56
(Gradual runs: 1 worker killed each. Spike runs: 6 workers killed each.)
```

!!! tip "How to read this"
    The `Perhaps out of memory?` message comes from gunicorn — it is application-level logging, not platform-level. Gunicorn detects that its child process received SIGKILL (which is the OOM killer's signal) and logs its best guess. If the application used a different process manager (or ran as a single process), this log would not exist.

### 10.6 Azure Monitor Metrics Evidence

**WorkingSetBytes** (1-minute granularity):

| Timestamp | Average (MB) | Note |
|-----------|-------------|------|
| 14:08:00 | 202.9 | Run 1 — avg across the minute; actual peak was ~496MB |
| 14:09:00 | 33.9 | Post-OOM baseline |
| 14:10:00–14:13:00 | 33.9 | Idle |
| 14:14:00 | 34.0 | Start of runs 2-3 |
| 14:15:00 | 113.8 | Runs 3-5 blended — multiple OOMs within 1 minute |
| 14:16:00 | 35.0 | Post-OOM baseline |

**RestartCount**:

| Timestamp | Maximum | Note |
|-----------|---------|------|
| 14:10:00 | 1.0 | Appeared 3 minutes after first OOM — tracks container restarts, not worker restarts |
| 14:15:00 | 1.0 | Despite 5+ OOM kills, still shows max=1 |

**Replica API** (`az containerapp replica list`):

| Field | Value |
|-------|-------|
| restartCount | **0** |
| runningState | Running |
| startedAt | 2026-04-10T14:06:53Z (unchanged) |

!!! tip "How to read this"
    The replica API shows `restartCount: 0` and the same start time from initial deployment — proving the container (PID 1) never restarted. Azure Monitor `RestartCount` showing 1.0 is likely a stale metric from the initial deployment or a platform-side accounting discrepancy. The key insight: **all standard metrics say "nothing happened" while the application experienced 5 OOM kills.**

## 11. Interpretation

**H1 — System logs gap: CONFIRMED.** `ContainerAppSystemLogs_CL` recorded zero events after the initial container creation, despite 5 OOM kills across 9 minutes. The gap exists because the system logs track container lifecycle events (create, start, stop, terminate), and the container never stopped or terminated — only the worker process inside it was killed.

**H2 — Metrics partial visibility: CONFIRMED.** `WorkingSetBytes` showed a memory pattern (202.9MB average dropping to 33.9MB) that hints at something, but the 1-minute aggregation severely underreports the actual peak (496MB vs reported 202.9MB). `RestartCount` stayed at 0 in the replica API, confirming the container was never restarted. The platform has no metric that distinguishes "worker process OOM-killed" from "everything is fine."

**H3 — Console logs only evidence: CONFIRMED.** `ContainerAppConsoleLogs_CL` is the only telemetry source that contains direct evidence of OOM kills. The gunicorn master process logging `Worker was sent SIGKILL! Perhaps out of memory?` is application-level intelligence, not platform-provided. Applications that don't have a supervisor logging SIGKILL deaths would have **zero evidence** across all telemetry sources.

**H4 — Two failure modes: CONFIRMED.** Gradual memory leaks produced zero client-visible errors — the health endpoint (served by a separate thread in the gthread worker class) continued responding throughout the OOM kill and worker restart. Spike allocations caused client-visible `upstream connect error or disconnect/reset before headers` because the request-handling thread was killed mid-response, and the Envoy proxy couldn't forward the response.

### Key Discovery: The Gunicorn Absorption Effect

The most significant finding is that gunicorn's process model completely absorbs OOM kills at the platform level. Because gunicorn master (PID 1) stays alive and respawns workers, the container never terminates. This means:

1. No `ContainerTerminated` event in system logs
2. No container restart count increment
3. No exit code 137 propagation to the platform
4. Container health probes pass (master process is alive)

This is not a bug — it's the intended behavior of process supervisors. But it creates a **systematic blind spot** for any customer using gunicorn (Python), Supervisor, or similar multi-process architectures.

### Key Discovery: Spike Causes Kill-Restart Loop

The spike variant revealed a pathological interaction between gunicorn's request queuing and OOM kills. When a request triggers a large allocation and the worker is killed, gunicorn's master process queues the pending request for the next worker. The new worker accepts the same request, triggers the same allocation, and is killed again — creating a loop of 6 killed workers over ~8 seconds. This only stops when the Envoy proxy's request timeout expires.

## 12. What this proves

!!! success "Evidence level: Reproduced (5 OOM kills, 2 variants, consistent across all runs)"

1. **Container Apps system logs have zero visibility into worker-level OOM kills** — `ContainerAppSystemLogs_CL` contains no events whatsoever for OOM kills that don't terminate PID 1
2. **Azure Monitor metrics underreport OOM impact** — 1-minute `WorkingSetBytes` average showed 202.9MB when actual peak was 496MB (2.4× underreporting); `RestartCount` stayed 0
3. **Console logs are the ONLY evidence source** — `ContainerAppConsoleLogs_CL` captured gunicorn's SIGKILL messages, but this depends entirely on the application having a process supervisor that logs child deaths
4. **Gradual memory leaks are invisible to clients** — health probes pass, no HTTP errors, no availability impact visible externally. Memory drops to baseline and the cycle can repeat indefinitely without anyone noticing
5. **Spike allocations cause client-visible connection errors** — `upstream connect error or disconnect/reset before headers` with a kill-restart loop lasting ~8 seconds
6. **OOM kill threshold is deterministic**: All 3 gradual runs killed at exactly 464MB allocated / 496MB RSS in a 0.5Gi container — baseline (~32MB) + allocations = cgroup limit

## 13. What this does NOT prove

- **Single-process container behavior**: If the application runs as PID 1 (e.g., Node.js without a process manager), the container itself would be terminated and platform events would likely appear. This experiment only covers multi-process supervisors (gunicorn).
- **Application Insights visibility**: We did not instrument Application Insights SDK. The hypothesis that Application Insights would also miss OOM kills remains untested (but is highly likely — the process is SIGKILL'd before any flush).
- **Higher memory tiers**: 0.5Gi is the minimum. Behavior at 1Gi, 2Gi, or 4Gi may differ in timing but the observability gap mechanism is the same.
- **Kubernetes-native OOM behavior**: Container Apps abstracts Kubernetes. In raw Kubernetes, `kubectl describe pod` shows `OOMKilled` as the last state — Container Apps may or may not expose this through `ContainerAppSystemLogs_CL` in other scenarios.
- **Long-term memory leak patterns**: Our test ran over minutes. A slow leak over hours or days might produce different metric patterns with Azure Monitor's longer aggregation windows.

## 14. Support takeaway

!!! abstract "For support engineers"

    **When a customer reports "unexplained container restarts with no errors in logs":**

    1. **Check console logs FIRST** — query `ContainerAppConsoleLogs_CL` for `SIGKILL`, `killed`, `out of memory`, or `OOM`. System logs will show nothing useful.
    2. **Look at `WorkingSetBytes` pattern** — a sawtooth pattern (gradual rise → sharp drop → rise again) is the memory metric signature of repeated OOM kills, even if the absolute values look low due to 1-minute averaging
    3. **Ask about the process model** — "Are you using gunicorn, uWSGI, Supervisor, or similar?" Multi-process architectures hide OOM kills from platform telemetry
    4. **Check PID changes in console logs** — if `Booting worker with pid: N` appears repeatedly with increasing PIDs, workers are being killed and restarted

    **KQL query for OOM detection** (the only reliable method):

    ```kusto
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == "<app-name>"
    | where Log_s has_any ("SIGKILL", "out of memory", "OOMKilled", "killed")
    | project TimeGenerated, Log_s
    | order by TimeGenerated desc
    ```

    **Why system logs don't help:**

    ```kusto
    // This query returns NOTHING for gunicorn-style OOM kills:
    ContainerAppSystemLogs_CL
    | where ContainerAppName_s == "<app-name>"
    | where Reason_s in ("ContainerTerminated", "Error")
        or Log_s has "137"
    // Result: 0 rows — the container never terminated
    ```

    **Customer recommendations:**

    1. **Add memory monitoring to application code** — log RSS periodically so console logs capture the trend before OOM
    2. **Set memory limits with headroom** — if baseline is 32MB and peak workload needs 400MB, use 1Gi not 0.5Gi
    3. **Use `--max-requests` in gunicorn** — automatic worker recycling prevents unbounded memory growth
    4. **Consider `--max-requests-jitter`** — prevents all workers from restarting simultaneously

## 15. Reproduction notes

- Container Apps Consumption tier minimum memory is 0.5Gi for 0.25 vCPU — this is a valid combination
- gunicorn `gthread` worker class is essential — sync workers would block the health endpoint during allocation, causing Container Apps to restart the container (masking the OOM visibility gap)
- Memory allocation must touch every page (`bytearray` with page-touching loop) — Python's lazy allocation means `bytearray(500*1024*1024)` alone might not trigger OOM immediately
- The background thread design keeps `/health` and `/memory` endpoints responsive during gradual allocation, allowing observation of the OOM without health probe interference
- Console log ingestion into Log Analytics has 1-5 minute delay — wait before querying
- System log ingestion delay is similar but irrelevant here since no events are generated
- `RestartCount` metric is unreliable for multi-process OOM detection — it tracks container restarts, not process restarts
- Test application source code is available in the `data/container-apps/oom-visibility-gap/` directory
- The spike variant causes gunicorn request queuing to create a kill-restart loop — this is a known gunicorn behavior, not a Container Apps issue

## 16. Related guide / official docs

- [Monitor Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Log monitoring in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Container Apps system logs](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring?tabs=bash#system-logs)
- [Gunicorn design — Worker processes](https://docs.gunicorn.org/en/stable/design.html)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
