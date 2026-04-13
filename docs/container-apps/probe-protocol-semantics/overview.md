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

# Probe Protocol Semantics (HTTP vs TCP)

!!! info "Status: Published (2026-04-14)"

## 1. Question

How do HTTP and TCP probe protocols differ in their ability to detect application-level failures in Azure Container Apps? Specifically, when an application's health endpoint returns HTTP 503, does the probe protocol choice (HTTP vs TCP) affect whether the platform detects the failure?

## 2. Why this matters

Probe configuration issues commonly appear in support cases as contradictory signals: the platform reports `Healthy`, but the application's own health endpoint returns errors. The protocol choice determines what the platform can actually observe.

- **HTTP probes** evaluate the HTTP transaction, including the returned status code.
- **TCP probes** only verify that the target port accepts a socket connection.
- A workload can therefore be application-unhealthy while still platform-healthy if the selected probe type cannot see the failure mode.

This distinction matters when customers ask why a revision is not restarting even though `/live` returns 503, or why one revision enters a restart loop while an otherwise identical revision remains healthy.

## 3. Customer symptom

Typical ticket phrasing:

- "Our health endpoint returns 503, but Container Apps still shows Healthy."
- "Two identical apps behave differently: one restarts, the other stays up."
- "The app is serving traffic, but `/live` says the dependency is down. Why is there no restart?"
- "We switched the probe type and the platform stopped detecting the failure."

## 4. Hypothesis

1. HTTP probes will detect HTTP 503 responses from health endpoints and trigger container restarts via liveness probe failure.
2. TCP probes will only verify TCP port connectivity (socket open) and will **not** detect HTTP 503 responses, leaving the container in a `Healthy` state even when the application reports itself as unhealthy.
3. Both probe types will correctly detect a completely stopped process (port not listening).

## 5. Environment

| Parameter | Value |
|---|---|
| Service | Azure Container Apps |
| Hosting model | Managed environment (Consumption) |
| Region | `koreacentral` |
| Runtime | Python 3.11, Flask + Gunicorn |
| Container image | `acrhealthprobelabb7db7c.azurecr.io/health-probe-lab:v1` |
| Ingress | External, target port 8080 |
| Revision mode | Single |
| Date tested | 2026-04-13 |

## 6. Variables

**Controlled**

- Probe protocol: HTTP vs TCP
- Probe target: `/startup`, `/live`, `/ready` vs TCP socket on port 8080
- Probe timings:
    - Startup: `periodSeconds=5`, `failureThreshold=6`, `timeoutSeconds=2`
    - Liveness: `periodSeconds=10`, `failureThreshold=3`, `timeoutSeconds=3`
    - Readiness: `periodSeconds=5`, `failureThreshold=3`, `timeoutSeconds=3`
- Container image, ingress, revision mode, and runtime
- Failure trigger: `LIVENESS_CHECK_DEPENDENCY=true`, `DEPENDENCY_URL=http://10.0.99.99:8080/health`, `DEPENDENCY_TIMEOUT_MS=1000`

**Observed**

- Revision health state after the failure trigger
- Probe failure events and `ContainerTerminated` events in system logs
- Restart counts from Log Analytics
- Direct HTTP responses from `/live` and `/`
- Whether traffic continued to be served during the probe failure condition

## 7. Instrumentation

- **ContainerAppSystemLogs_CL** for probe failures, container lifecycle events, and restart evidence
- **Direct endpoint tests** using HTTP requests to `/live` and `/`
- **Revision health state** from Azure Container Apps control plane
- **Log Analytics restart counts** for per-revision restart totals

## 8. Procedure

### Deployment design

Two apps were deployed from the same container image with the same environment variables and ingress settings. The only intentional difference was the probe protocol.

### App definitions

**ca-probe-http** — HTTP probes

- Startup: HTTP GET `/startup`, `period=5s`, `failureThreshold=6`, `timeout=2s`
- Liveness: HTTP GET `/live`, `period=10s`, `failureThreshold=3`, `timeout=3s`
- Readiness: HTTP GET `/ready`, `period=5s`, `failureThreshold=3`, `timeout=3s`

**ca-probe-tcp** — TCP probes

- Startup: TCP socket port `8080`, `period=5s`, `failureThreshold=6`, `timeout=2s`
- Liveness: TCP socket port `8080`, `period=10s`, `failureThreshold=3`, `timeout=3s`
- Readiness: TCP socket port `8080`, `period=5s`, `failureThreshold=3`, `timeout=3s`

### Test sequence

1. Deploy both apps and confirm baseline health.
2. Verify baseline behavior: both apps should be `Healthy`, `RunningAtMaxScale`, and return HTTP 200.
3. Enable dependency checking by setting:

```text
LIVENESS_CHECK_DEPENDENCY=true
DEPENDENCY_URL=http://10.0.99.99:8080/health
DEPENDENCY_TIMEOUT_MS=1000
```

4. This causes the `/live` endpoint to return HTTP 503 because the dependency target is unreachable.
5. Observe each revision's health state and system logs.
6. Test `/live` and `/` directly after the failure trigger.
7. Compare restart counts between the HTTP-probed and TCP-probed revisions.

## 9. Expected signal

- The HTTP-probed app should log repeated liveness failures with HTTP 503 and restart after the failure threshold is reached.
- The TCP-probed app should remain healthy as long as port 8080 continues accepting TCP connections, even if `/live` returns HTTP 503.
- Both probe types should still detect a fully stopped process because the port would no longer accept connections.

## 10. Results

**Execution date**: 2026-04-13  
**Failure trigger**: unreachable dependency behind `/live`

### Baseline (before enabling dependency check)

Both apps were `Healthy`, `RunningAtMaxScale`, and served **10/10 HTTP 200** responses. Response times were approximately **50ms**.

### After enabling dependency check

#### ca-probe-http (HTTP probes) — revision `0000003`

- Health state: **Activating**
- Behavior: revision stuck in a restart loop and never became healthy
- System logs showed **5 `ContainerTerminated` events** in approximately **6 minutes**

```text
15:34:02 — Container created, started
15:34:08 — Probe of Liveness failed with status code: 503
15:34:18 — Probe of Liveness failed with status code: 503
15:34:28 — Liveness threshold reached → ContainerTerminated (ProbeFailure)
15:34:28 — Container restarted
... cycle repeats ...
15:35:48 — Container created (another restart)
15:35:55 — Liveness failed 503
15:36:05 — Liveness failed 503
15:36:15 — ContainerTerminated (ProbeFailure)
```

- Old revision `0000002` (without dependency check) continued serving traffic successfully with HTTP 200
- Total restarts recorded: **5**

#### ca-probe-tcp (TCP probes) — revision `0000003`

- Health state: **Healthy**
- Running state: **RunningAtMaxScale**
- `ContainerTerminated` events: **0**
- Liveness or readiness `ProbeFailed` events: **0**
- System logs showed only normal deployment events
- Revision remained stable for the entire observation window

### Direct endpoint tests after the failure trigger

#### TCP-probed app

- `/live`: **HTTP 503**
- Response body showed:
    - `"status": "dependency-failed"`
    - `"status_code": 503`
- `/`: **HTTP 200** in **0.062s**

The application process was fully functional and continued serving normal traffic even while `/live` consistently returned 503.

#### HTTP-probed app

- `/`: **HTTP 200** in **0.069s** from the old revision that was still active

### Restart counts (Log Analytics)

| Revision | Restarts |
|---|---:|
| `ca-probe-http--0000003` | 5 |
| `ca-probe-tcp--0000003` | 0 |

### Summary comparison

| App | Probe protocol | `/live` result after trigger | Platform health | Restarts | Observed outcome |
|---|---|---|---|---:|---|
| `ca-probe-http` | HTTP | 503 | Activating / never healthy | 5 | Restart loop |
| `ca-probe-tcp` | TCP | 503 | Healthy / RunningAtMaxScale | 0 | No restart |

## 11. Interpretation

### Evidence summary

| Evidence type | Finding |
|---|---|
| `[Observed]` | The HTTP-probed revision logged repeated liveness failures with status code 503 and entered a restart loop |
| `[Observed]` | The TCP-probed revision remained `Healthy` with zero liveness/readiness failures even though `/live` returned 503 |
| `[Measured]` | Restart counts diverged completely: HTTP revision = 5 restarts, TCP revision = 0 restarts |
| `[Measured]` | Direct endpoint tests confirmed `/live` returned 503 while `/` still returned 200 in 62ms on the TCP-probed app |
| `[Correlated]` | Revision health state matched probe visibility: HTTP probe saw the 503 and the revision destabilized; TCP probe could not see the 503 and the revision stayed healthy |
| `[Inferred]` | TCP probes in Container Apps validate socket acceptability rather than application-layer success semantics |

### Key findings

1. **HTTP probes evaluate HTTP response semantics** `[Observed]`

    In the HTTP-probed revision, the liveness endpoint's HTTP 503 responses were treated as probe failures. After three consecutive failures, the platform terminated and restarted the container.

2. **TCP probes only test transport-level reachability** `[Observed]`

    In the TCP-probed revision, port 8080 remained open and accepted connections, so the platform considered the revision healthy. The HTTP 503 returned by `/live` had no effect on probe outcome because the probe never evaluated the HTTP response code.

3. **Application-unhealthy and platform-healthy can coexist** `[Observed]`

    The TCP-probed app remained healthy at the platform level while its own health endpoint continuously reported dependency failure. This creates a split-brain view of health: the app says unhealthy; the platform says healthy.

4. **Protocol choice determines failure visibility** `[Correlated]`

    The two deployments were intentionally identical except for probe protocol. The divergent behavior therefore aligns directly with what each probe type can observe: HTTP sees status codes; TCP sees only socket connectivity.

5. **TCP probes are suitable for crash detection, not application-level degradation** `[Inferred]`

    This experiment showed that TCP probes can miss failures expressed as HTTP error codes. They remain useful for detecting complete process failure, because a stopped process would close the port, but they do not validate whether the app considers itself healthy.

### Hypothesis validation

| Hypothesis | Result | Evidence |
|---|---|---|
| HTTP probes will detect HTTP 503 and trigger liveness-based restarts | **Confirmed** | HTTP revision logged repeated 503 liveness failures and restarted 5 times |
| TCP probes will ignore HTTP 503 and keep the container healthy while the port remains open | **Confirmed** | TCP revision stayed healthy with 0 restarts while `/live` returned 503 |
| Both probe types will detect a completely stopped process | **Not directly tested in this run** | Expected from probe mechanics, but no explicit port-closed scenario was executed in the provided data |

## 12. What this proves

Within this test setup, the experiment proved the following:

- HTTP liveness probes in Azure Container Apps treat HTTP 503 from the target endpoint as probe failure and can drive container restart loops `[Observed]`
- TCP probes do not interpret HTTP response codes and therefore cannot detect application-level health failures that manifest only as HTTP 503 while the port remains open `[Observed]`
- A Container Apps revision can remain platform-healthy for the entire observation period while its `/live` endpoint consistently returns HTTP 503 `[Measured]`
- Probe protocol selection materially changes whether the platform detects or ignores the same underlying failure condition `[Correlated]`

## 13. What this does NOT prove

- That TCP probes never generate false positives or false negatives under other transport-layer failure modes
- That every HTTP non-200 status is handled identically across all probe types, regions, and platform versions beyond this test
- That restart timing and health-state wording are identical in all Azure Container Apps environments
- That the untested port-closed scenario behaved identically for both apps in this specific run, even though that behavior is mechanically expected
- That readiness probes or startup probes would show identical protocol semantics in every adjacent scenario beyond the liveness-centered evidence collected here

## 14. Support takeaway

When a customer says "the app returns 503 but Container Apps shows Healthy," check the probe protocol first.

1. If the probe is **TCP**, the platform is only checking whether the port accepts a connection. HTTP 503 from `/live` will be invisible to the platform.
2. If the customer needs the platform to react to application-level health semantics, recommend an **HTTP** probe against a lightweight endpoint.
3. If the goal is only to detect process crash or listener death, **TCP** probes are sufficient.
4. When comparing revisions with different restart behavior, verify whether the only difference is probe protocol before escalating as a platform inconsistency.

| Use case | Better probe choice | Reason |
|---|---|---|
| Detect app returns 503 / dependency-failed state | HTTP | Evaluates HTTP status code |
| Detect process stopped / port closed | TCP or HTTP | Either probe fails when the port is unavailable |
| Detect degraded business logic behind a responsive listener | HTTP | TCP cannot see application-layer failure |

## 15. Reproduction notes

- Keep the two deployments identical except for probe protocol; otherwise the comparison loses diagnostic value.
- Single revision mode simplifies interpretation because the old healthy HTTP revision can continue serving traffic while the new failing revision loops.
- Use an unreachable private IP such as `10.0.99.99` to force deterministic dependency failure without relying on DNS behavior.
- Query Log Analytics with a sufficiently wide time window because probe and restart events may ingest with delay.
- Direct endpoint checks are necessary to prove the key contradiction in the TCP case: platform healthy, `/live` unhealthy.

## 16. Related guide / official docs

- [Microsoft Learn: Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Microsoft Learn: Troubleshoot health probe failures in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-health-probe-failures)
- [Microsoft Learn: Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Liveness Probe Failure Patterns](../liveness-probe-failures/overview.md) — related experiment on liveness-triggered restarts and failure modes
- [Startup Probes](../startup-probes/overview.md) — related experiment on probe behavior during container initialization
