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

# Liveness Probe Failure Patterns

!!! info "Status: Published (2026-04-13)"

## 1. Question

What failure patterns emerge from liveness probe design choices in Azure Container Apps — specifically dependency-checking probes, blocking-I/O probes, missing probes, and how do liveness-triggered restarts affect in-flight requests?

## 2. Why this matters

Liveness probe design is a common source of support escalations that appear as platform instability but are rooted in application or configuration choices. Typical anti-patterns include:

- **Dependency-checking liveness** — probe checks external dependencies (databases, caches), causing cascading restarts when a dependency fails even though the app process itself is healthy
- **Blocking I/O in probe handlers** — synchronous file, network, or lock operations inside the liveness endpoint exceed the probe timeout, triggering unnecessary restarts
- **Missing liveness probes** — zombie or deadlocked processes remain running indefinitely because the platform has no mechanism to detect unresponsiveness
- **In-flight request disruption** — liveness-triggered container termination kills active requests mid-execution, producing 503 errors for clients

These patterns are distinct from startup probe misconfiguration (covered in the [Startup Probes](../startup-probes/overview.md) experiment), which addresses initialization-phase failures. This experiment focuses on runtime liveness failures that occur after a container has successfully started.

## 3. Customer symptom

Typical ticket phrasing:

- "My container keeps restarting every few minutes even though the app works fine."
- "We added a health check that verifies our Redis connection, and now the app restarts whenever Redis is slow."
- "The app stops responding to requests but the container shows as Running. No restarts happen."
- "We see 503 errors from our API, and the logs show ProbeFailure, but the endpoint works when I test it manually."
- "In-flight requests are getting dropped and clients receive 503 during what looks like a restart."

## 4. Hypothesis

1. A liveness probe that checks an external dependency will cause cascading container restarts when the dependency becomes unreachable, even when the application process itself is healthy and capable of serving non-dependent requests.
2. A liveness probe handler that performs blocking I/O exceeding the probe timeout will trigger probe failure and container restart, even if the blocking operation is transient.
3. Without a liveness probe, a container that enters a zombie state (process alive but all handlers unresponsive) will remain in the `Running`/`Healthy` state indefinitely with no platform-initiated recovery.
4. When a liveness probe failure triggers container termination, in-flight HTTP requests will be terminated with 503 errors before their normal completion.

## 5. Environment

| Parameter | Value |
|---|---|
| Service | Azure Container Apps |
| Hosting model | Managed environment (Consumption) |
| Region | `koreacentral` |
| Runtime | Python 3.11, Flask + Gunicorn (1 worker, 8 threads) |
| Container image | Custom image with `/livez`, `/healthz`, `/readyz`, `/slow`, `/simulate/*` endpoints |
| Ingress | External, target port 8080 |
| Revision mode | Single revision per scenario |
| Logging | Log Analytics workspace |
| Date tested | 2026-04-13 |

## 6. Variables

**Controlled**

- Liveness probe presence (enabled vs omitted)
- Liveness probe endpoint behavior (healthy, dependency-check, blocking I/O, zombie hang)
- Liveness probe configuration: `periodSeconds=10`, `timeoutSeconds=5`, `failureThreshold=3`
- External dependency reachability (`DEPENDENCY_HOST` env var)
- Liveness I/O delay (`LIVENESS_IO_DELAY` env var)
- Application zombie state (triggered via `/simulate/zombie`)
- In-flight request duration (`/slow?seconds=N`)

**Observed**

- Container restart count and restart timing
- Revision health state (`Healthy` / `Unhealthy` / `Failed`)
- System log messages (`ProbeFailed`, `ContainerTerminated`, `ProbeFailure`)
- HTTP response codes from client requests during each scenario
- Time from probe failure to container termination
- In-flight request outcome (completed vs dropped)
- Exit code on container termination

## 7. Instrumentation

- **ContainerAppSystemLogs_CL** for probe failure events, container termination, and restart lifecycle
- **Synthetic HTTP requests** via `curl` with timing (`--max-time`, `-w "%{http_code} %{time_total}"`)
- **Application status endpoint** (`/status`) reporting `zombie`, `deadlocked`, `inflight` counters
- **ARM REST API** for container app deployment (required due to ACR secret naming constraints)

## 8. Procedure

### Test application

A custom Flask application was deployed with the following endpoints:

| Endpoint | Behavior |
|---|---|
| `/` | Returns JSON with hostname, uptime, in-flight count. Hangs in zombie mode. |
| `/livez` | Liveness probe endpoint. Checks dependency if `DEPENDENCY_HOST` is set. Sleeps `LIVENESS_IO_DELAY` seconds if configured. Hangs in zombie/deadlock mode. |
| `/healthz` | Startup/health check. Hangs in zombie mode. |
| `/readyz` | Readiness check. Always returns 200. |
| `/slow?seconds=N` | Sleeps N seconds before responding. Hangs in zombie mode. |
| `/simulate/zombie` | POST — sets zombie flag; all handlers begin sleeping 300s. |
| `/simulate/reset` | POST — clears all failure simulations. |
| `/status` | Returns current state (zombie, deadlocked, inflight count). |

### Scenario matrix

| Scenario | Liveness probe | App behavior | Expected outcome |
|---|---|---|---|
| **S5** (Baseline) | Enabled: `/livez`, period=10s, timeout=5s, fail=3 | Healthy, no delays | No restarts, all requests succeed |
| **S1** (Dependency) | Enabled: `/livez` checks `DEPENDENCY_HOST=10.0.99.99` | Dependency unreachable → 503 | Cascading restart loop |
| **S2** (Blocking I/O) | Enabled: `/livez` sleeps 8s (`LIVENESS_IO_DELAY=8`) | Probe exceeds 5s timeout | Timeout-based restart loop |
| **S3** (No liveness) | **Omitted** (startup + readiness only) | Zombie triggered via `/simulate/zombie` | Platform reports Healthy; app unresponsive indefinitely |
| **S4** (In-flight drop) | Enabled: `/livez`, healthy initially | Zombie triggered after in-flight requests start | In-flight requests receive 503 |

### Execution steps

1. Deploy infrastructure: Resource Group, Log Analytics Workspace, Container Apps Environment, Azure Container Registry.
2. Build and push test container image to ACR.
3. Deploy each scenario sequentially using ARM REST API (`az rest --method PUT`).
4. For each scenario:
    - Verify baseline health via `/status`
    - Execute scenario-specific trigger (env var config or `/simulate/*` POST)
    - Send synthetic HTTP requests and record response codes/timing
    - Wait for probe failure cycle (or confirm no restart occurs)
    - Query `ContainerAppSystemLogs_CL` for probe events
5. Record all results.

### ARM deployment pattern

```bash
SUB_ID="<subscription-id>"
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/<rg>/providers/Microsoft.App/containerApps/<app>?api-version=2024-03-01" \
  --headers "Content-Type=application/json" \
  --body @scenario.json
```

ARM REST API was required because the auto-generated ACR secret name ended with `-`, causing `ContainerAppInvalidSecretName` errors with `az containerapp create --registry-*` flags. Manual secret naming (`acr-pass`) in the ARM template resolved this.

## 9. Expected signal

- **S5**: No `ProbeFailed` or `ContainerTerminated` events. All HTTP requests return 200.
- **S1**: Repeated `Probe of Liveness failed with status code: 503` → `ContainerTerminated (ProbeFailure)` → restart loop. Revision becomes `Unhealthy/Failed`.
- **S2**: Repeated `Probe of Liveness failed with timeout in 5 seconds` → `ContainerTerminated (ProbeFailure)` → restart loop. Revision becomes `Unhealthy/Failed`.
- **S3**: No probe failure events. Revision stays `Healthy/Running`. App completely unresponsive after zombie trigger.
- **S4**: In-flight `/slow` requests receive HTTP 503 before their expected completion time. `ContainerTerminated` with exit code 137 (SIGKILL).

## 10. Results

**Execution Date**: 2026-04-13 14:20–15:00 UTC
**Resource Group**: `rg-aca-liveness-probe-lab`
**Container Apps Environment**: `cae-liveness-probe-lab` (koreacentral)
**Test Image**: `acrlivenessprobe.azurecr.io/liveness-probe-lab:v2`

### S5: Healthy Baseline

**Configuration**: Liveness probe on `/livez`, period=10s, timeout=5s, failureThreshold=3. No dependency, no I/O delay.

**Result**: 50/50 requests succeeded with HTTP 200, average response time 13ms. After 60 seconds of observation, zero restarts occurred. Revision remained `Healthy`/`Running` with 1 replica.

### S1: Dependency-Checking Liveness (Cascading Restart)

**Configuration**: Same liveness probe, but `DEPENDENCY_HOST=10.0.99.99` (unreachable IP). The `/livez` handler attempts a TCP connection to this host and returns 503 on failure.

**Result**: 20/20 requests returned HTTP 000 (connection refused — app was in restart loop). The revision entered `Unhealthy`/`Failed` state.

**System log timeline**:

```text
14:33:05 — Probe of Liveness failed with status code: 503
14:33:15 — Probe of Liveness failed with status code: 503
14:33:25 — Container 'liveness-lab' was terminated with reason 'ProbeFailure'
14:33:25 — Container liveness-lab failed liveness probe, will be restarted
14:33:37 — Created container 'liveness-lab'
14:33:54 — Probe of Liveness failed with status code: 503
14:34:14 — Container terminated again (2nd restart)
14:34:35 — Container recreated (3rd restart)
14:35:13 — Container terminated again (4th restart)
```

The restart cycle repeated indefinitely. Each cycle took approximately 40–50 seconds: container start (5s startup delay) → liveness begins checking → 3 consecutive 503 responses (30s) → termination → recreation.

### S2: Blocking I/O Liveness (Timeout Restart)

**Configuration**: `LIVENESS_IO_DELAY=8` — the `/livez` handler sleeps 8 seconds before responding. Probe timeout is 5 seconds.

**Result**: 10/10 requests returned HTTP 000 (connection refused — restart loop). The revision entered `Unhealthy`/`Failed` state.

**System log timeline**:

```text
14:37:53 — Probe of Liveness failed with timeout in 5 seconds.
14:38:03 — Probe of Liveness failed with timeout in 5 seconds.
14:38:13 — Container terminated with reason 'ProbeFailure'
14:38:13 — Container liveness-lab failed liveness probe, will be restarted
14:38:26 — Container recreated
```

The restart pattern was identical to S1 but the failure reason was timeout instead of HTTP status code.

### S3: No Liveness Probe (Zombie Undetected)

**Configuration**: Liveness probe **omitted**. Only startup and readiness probes configured. App deployed normally, then zombie mode triggered via `POST /simulate/zombie`.

**Zombie trigger time**: 14:49:17 UTC

**Immediate test** (10s timeout):

```text
HTTP 000 in 10.000609s
```

**Test after 90 seconds** (10s timeout):

```text
HTTP 000 in 10.006061s
```

**Platform state after 90+ seconds of zombie**:

```json
{
  "healthState": "Healthy",
  "replicas": 1,
  "runningState": "Running"
}
```

**10 parallel requests** (5s timeout each):

| Request | HTTP Code | Duration |
|---|---|---|
| req1–req10 | 000 | 5.0s (all timed out) |

**System logs**: No `ProbeFailed`, `ContainerTerminated`, or restart events appeared after the zombie was triggered. The only log entries were the initial deployment events (container creation, startup probe).

### S4: In-Flight Request Drop During Liveness Restart

**Configuration**: Liveness probe enabled (period=10s, timeout=5s, fail=3). App starts healthy; zombie mode triggered after in-flight requests are established.

**Execution**:

1. Deployed healthy app with liveness probe
2. Launched 5 concurrent `/slow?seconds=120` requests (expected to complete at T+120s)
3. Confirmed 5 in-flight requests via `/status`
4. Triggered zombie at T+5s → liveness probe starts failing
5. Waited for in-flight request outcomes

**Result**:

| Request | HTTP Code | Actual Duration | Expected Duration |
|---|---|---|---|
| SLOW_REQ_1 | **503** | 69,155ms | 120,000ms |
| SLOW_REQ_2 | **503** | 69,318ms | 120,000ms |
| SLOW_REQ_3 | **503** | 69,126ms | 120,000ms |
| SLOW_REQ_4 | **503** | 69,105ms | 120,000ms |
| SLOW_REQ_5 | **503** | 69,080ms | 120,000ms |

All 5 in-flight requests were terminated ~51 seconds early with HTTP 503.

**System log timeline**:

```text
14:56:32 — Probe of Liveness failed with timeout in 5 seconds.
14:56:42 — Probe of Liveness failed with timeout in 5 seconds.
14:56:49 — Probe of Readiness failed with timeout in 2 seconds.
14:56:52 — Probe of Liveness failed with timeout in 5 seconds.
14:56:52 — Container liveness-lab failed liveness probe, will be restarted
14:56:52 — Container 'liveness-lab' was terminated with reason 'ProbeFailure'
14:57:26 — Container 'liveness-lab' was terminated with exit code '137'
```

**Timeline analysis**:

- **T+0** (14:56:15): Slow requests launched
- **T+5** (14:56:20): Zombie triggered
- **T+17** (14:56:32): First liveness failure detected
- **T+37** (14:56:52): Third liveness failure → container termination initiated (ProbeFailure)
- **T+71** (14:57:26): Container killed with **exit code 137** (SIGKILL) after ~34s graceful shutdown period
- **T+69** (14:57:24): In-flight requests received HTTP 503

The 34-second gap between `ProbeFailure` termination (14:56:52) and `SIGKILL` (14:57:26) represents the platform's graceful shutdown window. During this window, the container remained running but zombie (all handlers hanging), so the in-flight requests could not complete gracefully. The ingress layer returned 503 when the container was finally killed.

### Scenario Comparison Summary

| Scenario | Liveness | Trigger | Restart? | Health State | HTTP Result | Failure Mode |
|---|---|---|---|---|---|---|
| S5 (Baseline) | ✅ Enabled | None | No | Healthy | 200 (50/50) | None |
| S1 (Dependency) | ✅ Enabled | Unreachable dep | Yes (loop) | Unhealthy/Failed | 000 (20/20) | 503 status probe failure |
| S2 (Blocking I/O) | ✅ Enabled | 8s sleep in handler | Yes (loop) | Unhealthy/Failed | 000 (10/10) | Timeout probe failure |
| S3 (No liveness) | ❌ Omitted | Zombie triggered | **No** | **Healthy/Running** | 000 (10/10) | **Undetected zombie** |
| S4 (In-flight) | ✅ Enabled | Zombie after requests | Yes (once) | N/A | **503** (5/5) | In-flight request drop |

## 11. Interpretation

### Evidence Summary

| Evidence Type | Finding |
|---|---|
| `[Observed]` | Dependency-checking liveness probe (S1) caused indefinite restart loop when external host was unreachable |
| `[Observed]` | Blocking I/O exceeding timeout (S2) triggered identical restart loop pattern |
| `[Observed]` | Without liveness probe (S3), zombie container remained `Healthy`/`Running` for 90+ seconds with zero platform intervention |
| `[Observed]` | In-flight requests (S4) received HTTP 503, terminated ~51 seconds before expected completion |
| `[Measured]` | S1 restart cycle: ~40–50 seconds (5s startup + 30s probe failures + termination overhead) |
| `[Measured]` | S4 graceful shutdown window: ~34 seconds (ProbeFailure at 14:56:52 → SIGKILL at 14:57:26) |
| `[Measured]` | S4 exit code: 137 (SIGKILL — forced termination after graceful period expired) |
| `[Correlated]` | Readiness probe also failed during zombie mode (14:56:49), which would have removed the replica from the load balancer pool |
| `[Inferred]` | The 503 returned to in-flight requests was generated by the Envoy ingress layer when the backend container was terminated, not by the application itself |
| `[Inferred]` | The ~34s graceful shutdown period is a platform-configured termination grace period during which the container receives SIGTERM followed by SIGKILL |

### Key Findings

1. **Dependency-checking liveness is a cascading failure anti-pattern** `[Observed]`

    The S1 scenario demonstrated that when `/livez` checks an external dependency, a dependency outage causes the application container to restart indefinitely — even though the application process itself is healthy. This converts a partial outage (one dependency down) into a total outage (entire application restarting). The liveness probe amplifies the blast radius of the original failure.

2. **Blocking I/O in liveness handlers is indistinguishable from a crash** `[Observed]`

    The S2 scenario showed that a probe handler sleeping 8 seconds with a 5-second timeout produces the same outcome as a genuinely crashed process: `ProbeFailure` → `ContainerTerminated` → restart loop. The platform cannot differentiate between "handler is slow" and "process is dead" — it only sees the timeout.

3. **Missing liveness probe creates an unrecoverable zombie state** `[Observed]`

    The S3 scenario confirmed that without a liveness probe, the platform has zero visibility into application responsiveness. The container remained `Healthy`/`Running` while serving zero requests. No timeout, no threshold, no heuristic exists at the platform level to detect this condition. Manual intervention is the only recovery path.

4. **Liveness restart terminates in-flight requests with 503** `[Measured]`

    The S4 scenario demonstrated that liveness-triggered container termination kills all in-flight requests. Clients received HTTP 503 — not a connection reset or timeout — indicating the Envoy ingress layer actively returned an error response when the backend became unavailable. The requests were cut short by ~51 seconds.

5. **Graceful shutdown period exists but may not help** `[Measured]`

    The ~34-second gap between `ProbeFailure` termination and exit code 137 (SIGKILL) indicates the platform sends SIGTERM and waits before sending SIGKILL. However, in the zombie scenario, the application could not process the SIGTERM because all threads were blocked. Applications that handle SIGTERM (drain connections, finish in-flight work) can mitigate in-flight request loss during this window.

### Hypothesis Validation

| Hypothesis | Result | Evidence |
|---|---|---|
| Dependency-checking liveness causes cascading restarts | **Confirmed** | S1: indefinite restart loop with unreachable dependency |
| Blocking I/O exceeding timeout triggers restarts | **Confirmed** | S2: 8s sleep with 5s timeout → restart loop |
| Missing liveness probe leaves zombie undetected | **Confirmed** | S3: 90+ seconds zombie, platform reports Healthy |
| Liveness restart drops in-flight requests as 503 | **Confirmed** | S4: 5/5 requests got 503, terminated 51s early |

## 12. What this proves

Within this test setup, the experiment proved the following:

- A liveness probe that checks external dependency health converts a dependency outage into a cascading application outage through continuous container restarts `[Observed]`
- Synchronous blocking operations in a liveness probe handler that exceed the probe timeout produce an identical failure pattern to a genuinely crashed container `[Observed]`
- Without a liveness probe, Azure Container Apps has no mechanism to detect or recover from a zombie container — the process remains running and the platform reports healthy status indefinitely `[Observed]`
- Liveness-triggered container termination drops all in-flight HTTP requests, which receive HTTP 503 from the Envoy ingress layer `[Measured]`
- The platform provides a graceful shutdown period (~34 seconds observed) between SIGTERM and SIGKILL, but applications must actively handle SIGTERM to benefit from it `[Measured]`

## 13. What this does NOT prove

- Whether the graceful shutdown period is configurable or fixed at the platform level (the `terminationGracePeriodSeconds` equivalent was not varied)
- Whether multiple replicas would mitigate in-flight request loss (all scenarios used single-replica deployments)
- Whether readiness probe failure alone (without liveness failure) would prevent new requests from reaching a zombie container
- That these exact timing patterns reproduce identically across all Azure regions and Container Apps infrastructure versions
- Whether Dapr-enabled or sidecar-enabled containers exhibit different probe interaction behavior
- The behavior of TCP or gRPC probe types (only HTTP probes were tested)

## 14. Support takeaway

When a customer reports container restarts or unresponsive containers in Azure Container Apps, check the liveness probe design:

**Restart loop cases** (customer sees "container keeps restarting"):

1. Query `ContainerAppSystemLogs_CL` for `ProbeFailed` and `ContainerTerminated` reasons
2. Check the liveness probe endpoint: does it call external dependencies? If yes, a dependency outage is the likely root cause
3. Check whether the liveness handler performs blocking I/O: compare the operation time against `timeoutSeconds`
4. Verify the probe is checking **process liveness**, not **dependency availability** or **business logic health**

**Zombie / unresponsive cases** (customer sees "app stopped responding but container is Running"):

1. Check whether a liveness probe is configured at all
2. If no liveness probe exists, the platform cannot detect application-level hangs
3. Recommend adding a liveness probe that checks application thread responsiveness (lightweight endpoint, no external calls)

**In-flight request drop cases** (customer sees "503 errors during restart"):

1. This is expected behavior: liveness restart terminates the container, and Envoy returns 503 for in-flight requests
2. Recommend implementing SIGTERM handling in the application to drain connections gracefully
3. For critical workloads, recommend multiple replicas so traffic can shift to healthy instances during restart

**Liveness probe design guidance**:

| Do | Don't |
|---|---|
| Check process liveness only (e.g., "can I respond to HTTP?") | Check database connectivity |
| Return quickly (< 1s) | Perform blocking I/O or locks |
| Always configure a liveness probe | Omit it and rely on platform detection |
| Handle SIGTERM for graceful shutdown | Ignore SIGTERM and let SIGKILL drop connections |
| Use multiple replicas for availability | Run single replica for critical workloads |

## 15. Reproduction notes

- **ACR secret naming**: If the auto-generated ACR secret name ends with `-` (e.g., from ACR name `acrlivenessprobe`), use ARM REST API deployment with a manually named secret instead of `az containerapp create --registry-*`.
- **Log Analytics whitespace**: LAW workspace ID and key from `az monitor log-analytics workspace show` may contain trailing `\r`. Pipe through `tr -d '[:space:]'`.
- **ACR build encoding**: Use `--no-logs` flag with `az acr build` to avoid terminal encoding errors.
- **Zombie simulation**: The application must check the zombie flag in ALL handlers (including `/`), not just the liveness endpoint. An initial implementation that only blocked `/livez` left the main endpoint responsive, invalidating the S3 scenario.
- **Gunicorn threading**: The test app uses 1 worker with 8 threads. A deadlock that blocks a single handler does not prevent other handlers from responding on different threads. Zombie mode (which blocks all handlers) is necessary to simulate a truly unresponsive application.
- **Log ingestion delay**: `ContainerAppSystemLogs_CL` may take 1–3 minutes to appear after the event. Query with `ago(10m)` and wait if recent events are missing.
- **Graceful shutdown timing**: The observed ~34-second graceful shutdown period may vary. Run the S4 scenario with sufficiently long in-flight requests (120s+) to ensure the restart clearly interrupts them.

## 16. Related guide / official docs

- [Microsoft Learn: Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Microsoft Learn: Troubleshoot health probe failures in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-health-probe-failures)
- [Microsoft Learn: Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Startup Probes experiment](../startup-probes/overview.md) — covers probe interaction during initialization phase (complementary to this experiment)
- [Container Apps Labs Overview](../index.md)
