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

# Isolated Worker Process Startup and Communication Failures

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

In the Azure Functions isolated worker model (Python, .NET 8+), what is the startup handshake between the Functions host and the worker process? What failure modes prevent the worker from registering with the host, and how do these failures manifest in logs vs. a traditional in-process failure?

## 2. Why this matters

The isolated worker model decouples the Functions host runtime from the customer's worker process using a gRPC channel. This architectural change introduces a new class of startup failures that did not exist in the in-process model:

- The worker process starts but fails to connect to the host's gRPC server
- The worker connects but the function registration fails (missing bindings, wrong trigger types)
- The worker crashes after registration but before serving requests
- The gRPC channel between host and worker becomes unhealthy mid-operation

Support cases are more difficult to diagnose because the failure point is not the host (which remains running) but the worker process, and the error messages are often gRPC-level rather than application-level.

## 3. Customer symptom

- "The Function App shows as running but HTTP triggers return 503."
- "I can see the function in the portal but calling it returns 'Worker failed to load function'."
- "The function worked locally but fails in Azure with a startup error."
- "My Python function used to work, now after upgrading to isolated model it's broken."

## 4. Hypothesis

**H1 — Worker registration timeout causes 503**: If the worker process takes longer than the host's registration timeout to complete startup (import modules, initialize SDK clients), the host marks the worker as failed and rejects incoming requests.

**H2 — gRPC port conflict causes silent failure**: If the worker process cannot bind to the gRPC port (default: randomly assigned by host), it exits immediately. The host retries but the retry pattern is not immediately visible in standard logs.

**H3 — Missing package causes late failure**: If a required package is not installed, the import error occurs when the worker tries to load function definitions, not at process start. The host receives a partial registration or a registration error.

**H4 — Environment variable access timing**: In the isolated model, environment variables are available to the worker process from startup. Key Vault references (resolved by the host) are NOT available in the worker process's `os.environ` — only plain app settings are.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (isolated worker) |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Startup + Failure Mode

**Controlled:**

- Worker startup delay (0s, 5s, 15s, 30s via sleep in `__init__.py`)
- Missing package presence (ImportError during function load)
- Key Vault reference in app setting
- gRPC channel health under load

**Observed:**

- Time from host start to first successful function invocation
- Host log entries for worker registration events
- Worker process log entries (captured via Application Insights)
- Error response codes for requests during worker startup

## 7. Instrumentation

- Application Insights: traces from both host (`azure-functions-host`) and worker (`azure-functions-python-worker`)
- Custom log at worker startup: `logging.info("Worker started, registering functions")`
- HTTP probe: send requests every 5s from the moment the app starts, record when first 200 is received

**Startup timeline query:**

```kusto
traces
| where cloud_RoleName == "func-isolated-startup"
| where message contains "worker" or message contains "register" or message contains "start"
| project timestamp, message, severityLevel
| order by timestamp asc
| take 50
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az functionapp create \
  --name func-isolated-startup \
  --resource-group rg-isolated-startup \
  --consumption-plan-location koreacentral \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --storage-account saisolatedstartup
```

### 8.2 Scenarios

**S1 — Normal startup**: Baseline isolated worker startup. Measure time from host start to first successful HTTP trigger response.

**S2 — Slow worker startup (15s delay)**: Add `time.sleep(15)` in `__init__.py` (worker initialization). Measure whether host timeouts or waits.

**S3 — ImportError on function load**: Import a non-existent module in a trigger function file. Observe whether the host starts, other functions work, and what error the broken function returns.

**S4 — Key Vault reference access**: Set an app setting to a KV reference. In the worker, read `os.environ.get("MY_SECRET")`. Verify whether the worker sees the resolved value or the reference string.

**S5 — gRPC channel unhealthy**: After successful startup, use a CPU-intensive operation to block the worker event loop. Send concurrent HTTP requests. Observe host behavior when worker becomes unresponsive.

## 9. Expected signal

- **S1**: Worker registers within 5s of host start. HTTP triggers respond within 10s of cold start.
- **S2**: Host waits up to configured timeout; if delay exceeds timeout, requests return 503.
- **S3**: Host starts successfully. Functions without the import error work. Broken function returns 500 with import error detail.
- **S4**: Worker reads the resolved KV value — host resolves KV references before passing settings to the worker process.
- **S5**: Worker unresponsive → host detects via gRPC health check → requests return 503 → host restarts worker.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Python isolated worker uses asyncio event loop — blocking the event loop with sync code is more impactful than in .NET isolated worker.
- Key Vault reference behavior in isolated vs. in-process model may differ across host versions.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Slow worker startup causes host timeout | **Inferred** |
| ImportError in one function doesn't block other functions | **Inferred** |
| KV references resolved before worker startup | **Unknown** |

## 14. Related experiments

- [Cold Start (Functions)](../cold-start/overview.md) — overall cold start timing
- [Telemetry Auth Blackhole](../telemetry-auth-blackhole/overview.md) — host startup failure modes

## 15. References

- [Python isolated worker model](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python?tabs=isolated-process)
- [Azure Functions host and worker communication](https://learn.microsoft.com/en-us/azure/azure-functions/dotnet-isolated-process-guide)

## 16. Support takeaway

For isolated worker startup failures:

1. Check BOTH the host logs AND the worker logs in Application Insights — they are separate traces. Filter by `cloud_RoleName` to separate them.
2. A function returning 503 while the Function App appears running often indicates the worker process failed to register. Check for worker crash logs.
3. `ImportError` in a single function file prevents that function from loading but does not affect other functions in the app. Customers may not realize only one of their functions is broken.
4. In the isolated model, Key Vault references in app settings are resolved by the host before the worker starts. The worker sees resolved values in its environment — this is different from how raw KV SDK calls work.
5. For .NET 8 isolated apps, add health check middleware that returns 200 quickly — the host uses this to confirm the worker is alive. Slow health check responses can cause false-positive worker restarts.
