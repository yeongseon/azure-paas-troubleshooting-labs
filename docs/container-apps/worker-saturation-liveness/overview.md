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

# Worker Saturation vs Liveness Probes

!!! info "Status: Published (2026-04-14)"

## 1. Question

When a single-worker, single-thread web application has its only worker thread blocked by a long-running request, does the HTTP liveness probe timeout trigger a container restart, and what happens to the in-flight blocking request?

## 2. Why this matters

This is a common Azure Container Apps support pattern: the customer reports intermittent 503s, timeouts, or unexpected restarts, but platform telemetry initially suggests only probe failures. The real issue may be application-level worker saturation rather than an infrastructure fault.

In single-worker or otherwise concurrency-constrained applications, one long-running request can prevent the process from servicing all other traffic, including readiness and liveness endpoints. If the platform interprets that temporary unresponsiveness as container failure, the result is a restart that kills the original request and amplifies customer-visible impact.

For support engineers, the important question is whether probe-triggered restarts are the root cause or only the final symptom of a saturated application worker.

## 3. Customer symptom

Typical ticket phrasing:

- "Our Container App becomes unhealthy and restarts during one slow request."
- "We see intermittent 503s even though CPU and memory do not look exhausted."
- "Health probes start failing only when one request runs for a long time."
- "A request that should finish in 60 seconds never completes because the container restarts first."
- "The app looks healthy most of the time, but under one blocking request the whole replica stops responding."

## 4. Hypothesis

1. A single-worker, single-thread Gunicorn app will be unable to respond to liveness probes when the worker thread is occupied by a long-running request.
2. The liveness probe will timeout (3s configured) because the HTTP GET cannot be processed while the worker is blocked.
3. After 3 consecutive liveness probe failures (`failureThreshold=3`), the container will be terminated and restarted, killing the in-flight request.
4. The readiness probe will also fail, removing the replica from the load balancer before the liveness restart occurs.

## 5. Environment

| Parameter | Value |
|---|---|
| Service | Azure Container Apps |
| Hosting model | Managed environment (Consumption) |
| Region | `koreacentral` |
| Runtime | Python 3.11, Flask + Gunicorn (1 worker, 1 thread) |
| Container image | `acrhealthprobelabb7db7c.azurecr.io/health-probe-lab:v1` |
| Gunicorn command | `gunicorn app:app -b 0.0.0.0:8080 --workers 1 --threads 1 --timeout 120 --access-logfile -` |
| Ingress | External, target port 8080 |
| Revision mode | Single |
| App name | `ca-worker-sat` |
| Date tested | 2026-04-13 |

## 6. Variables

**Controlled**

- Gunicorn concurrency fixed at `--workers 1 --threads 1`
- Blocking request duration fixed at 60 seconds (`/delay?seconds=60`)
- Startup probe: HTTP GET `/startup`, `periodSeconds=5`, `failureThreshold=6`, `timeoutSeconds=2`
- Liveness probe: HTTP GET `/live`, `periodSeconds=10`, `failureThreshold=3`, `timeoutSeconds=3`
- Readiness probe: HTTP GET `/ready`, `periodSeconds=5`, `failureThreshold=3`, `timeoutSeconds=3`
- Single revision deployment with one active replica under test

**Observed**

- Baseline response success rate and latency before saturation
- HTTP outcomes for concurrent `/` requests during worker saturation
- HTTP outcome for direct `/live` request during worker saturation
- Probe failure timestamps in `ContainerAppSystemLogs_CL`
- Time from blocking request start to readiness failure threshold
- Time from first probe failure to liveness-triggered termination
- Outcome of the original blocking request after container restart

## 7. Instrumentation

- **Synthetic HTTP requests** using `curl` with explicit client-side timeout handling
- **Container Apps system logs** for readiness/liveness probe failures, threshold transitions, container termination, and restart events
- **Revision health state** from Azure Container Apps control plane (`Healthy`, `RunningAtMaxScale`)
- **Application access behavior** observed from baseline, during saturation, and after restart

## 8. Procedure

1. Deployed the test app with `gunicorn --workers 1 --threads 1` so the application had exactly one request-processing thread.
2. Verified the baseline state: 5/5 requests returned HTTP 200 with response time around 50-60ms; revision state was healthy.
3. Sent one blocking request:

    ```bash
    curl --max-time 120 "https://FQDN/delay?seconds=60"
    ```

4. While that request occupied the only worker, tested parallel responsiveness:
    - Sent 5 concurrent requests to `/`
    - Sent 1 request to `/live`
5. Collected system logs covering readiness failures, liveness failures, termination, and restart.
6. Waited for post-restart recovery and recorded the final outcome of the original blocking request.

## 9. Expected signal

If the hypothesis is correct:

- The single blocking request will monopolize the only Gunicorn worker and prevent the app from serving `/`, `/ready`, and `/live`
- User requests to `/` during saturation will time out rather than return normal application responses
- Readiness will fail first because it probes more frequently (`periodSeconds=5`), causing the replica to be removed from load balancing before restart
- Liveness will fail later and, after 3 consecutive timeouts, will terminate the container with `ProbeFailure`
- The original blocking request will not complete normally because the container restart will kill it mid-flight
- After restart, the fresh container should return to healthy state immediately

## 10. Results

**Execution date**: 2026-04-13 15:31-15:34 UTC  
**Application**: `ca-worker-sat`  
**Revision**: `ca-worker-sat--0000002`

### Baseline (before saturation)

- 5/5 requests returned HTTP 200
- Response times were approximately 50-60ms
- Revision state: `Healthy`, `RunningAtMaxScale`

### During worker saturation

- Blocking request sent at **15:31:30 UTC**
- 5 concurrent requests to `/`: **all returned HTTP 000** after timing out at 10 seconds
- 1 request to `/live`: **HTTP 000** after timing out at 5 seconds
- The worker was fully saturated and unable to process any other request while the delay request was active

### System logs (chronological)

```text
15:32:44 — Probe of Readiness failed with timeout in 3 seconds.
15:32:49 — Probe of Readiness failed with timeout in 3 seconds.
15:32:49 — Probe of Liveness failed with timeout in 3 seconds.
15:32:54 — Probe of Readiness failed with timeout in 3 seconds.
15:32:54 — Readiness Probe reached failure threshold 3, changing status to Failure.
15:32:54 — Container ca-worker-sat failed readiness probe
15:32:59 — Probe of Readiness failed with timeout in 3 seconds.
15:32:59 — Probe of Liveness failed with timeout in 3 seconds.
15:33:04 — Probe of Readiness failed with timeout in 3 seconds.
15:33:09 — Probe of Readiness failed with timeout in 3 seconds.
15:33:10 — Probe of Liveness failed with timeout in 3 seconds.
15:33:10 — Container ca-worker-sat failed liveness probe, will be restarted
15:33:10 — Container terminated with reason 'ProbeFailure'
15:33:59 — Container recreated and started
```

### Timeline summary

- **T+0** (15:31:30): Blocking request sent
- **T+~74s** (15:32:44): First readiness probe failure observed
- **T+~84s** (15:32:54): Readiness failure threshold reached; replica marked failed for readiness
- **T+~100s** (15:33:10): Liveness failure threshold reached; container terminated with `ProbeFailure`
- **T+~149s** (15:33:59): Container recreated and started

### After restart (recovered)

- Original blocking request: **HTTP 000** after timing out at 120 seconds on the client side
- The request never completed successfully; it was interrupted by the restart
- Container returned to `Healthy`, `RunningAtMaxScale` with a fresh worker after recreation
- Two total `ContainerTerminated` events were observed; the second was likely associated with another test or probe activity during restart rather than the main blocking-request event

## 11. Interpretation

### Evidence summary

| Evidence Type | Finding |
|---|---|
| `[Observed]` | One blocking `/delay?seconds=60` request prevented the 1-worker/1-thread app from serving any other HTTP request, including `/live` |
| `[Observed]` | Readiness failures appeared before liveness-triggered restart |
| `[Observed]` | The container was terminated with reason `ProbeFailure` after repeated liveness timeouts |
| `[Observed]` | After restart, the application returned to healthy state with a fresh worker |
| `[Measured]` | Baseline latency was ~50-60ms for 5/5 successful requests |
| `[Measured]` | All 5 concurrent `/` requests timed out at 10s and `/live` timed out at 5s during saturation |
| `[Measured]` | First observed readiness failure occurred ~74s after the blocking request, readiness threshold was reached ~84s after start, and liveness termination occurred ~100s after start |
| `[Correlated]` | The sequence readiness failure → readiness threshold reached → liveness threshold reached → `ProbeFailure` termination aligned with total worker unresponsiveness |
| `[Inferred]` | The readiness probe likely removed the replica from the load balancer before liveness restart, reducing new routed traffic during the final pre-restart window |
| `[Inferred]` | The blocking request was killed by container termination rather than finishing naturally, because the client eventually timed out and the container was restarted before a normal response was emitted |

### Key findings

1. **A single blocking request can fully saturate a single-worker Gunicorn process** `[Observed]`

    With `--workers 1 --threads 1`, the application had no remaining capacity once one long-running request was active. All other requests, including probe requests, were queued behind that request and could not be served.

2. **Probe timeouts can be an application concurrency symptom, not only an app crash symptom** `[Observed]`

    The liveness endpoint itself was not logically broken. It became unavailable because the application had no free worker to execute it. From the platform point of view, that unresponsiveness was indistinguishable from a dead or hung process.

3. **Readiness failed before liveness restarted the container** `[Measured]`

    Because readiness probed every 5 seconds while liveness probed every 10 seconds, the readiness threshold was reached first. This created a short window where the replica was effectively removed from traffic distribution before the container restart occurred.

4. **The in-flight blocking request did not survive the liveness-triggered restart** `[Observed]`

    The original `/delay` call never completed and the client eventually reported HTTP 000 at its 120-second timeout. Given the logged `ProbeFailure` termination and container recreation, the most reasonable explanation is that the request was terminated with the container.

5. **Recovery after restart was immediate in this scenario** `[Observed]`

    Once the platform recreated the container, the app returned to healthy state without additional intervention. This shows the failure mode was tied to transient worker saturation, not persistent startup breakage.

### Hypothesis validation

| Hypothesis | Result | Evidence |
|---|---|---|
| Single worker cannot respond to probes while occupied by long-running request | **Confirmed** | `/live` timed out and all concurrent `/` requests timed out during the blocking request |
| Liveness probe will timeout because the GET cannot be processed while the worker is blocked | **Confirmed** | Repeated `Probe of Liveness failed with timeout in 3 seconds` events |
| After 3 consecutive liveness failures, the container will restart and kill the in-flight request | **Confirmed** | Liveness threshold reached at 15:33:10, `ProbeFailure` termination logged, blocking request never completed |
| Readiness will fail before liveness and remove the replica from LB first | **Confirmed** | Readiness threshold reached at 15:32:54, before liveness-triggered termination at 15:33:10 |

## 12. What this proves

Within this test setup, the experiment proved the following:

- A single-worker, single-thread Flask + Gunicorn application in Azure Container Apps can become completely unresponsive to both user traffic and health probes when one long-running request occupies the only worker `[Observed]`
- HTTP liveness probes that cannot be processed because of worker saturation fail the same way as probes against a hung process: by timing out until the configured failure threshold is reached `[Observed]`
- Readiness can fail earlier than liveness when it uses a shorter probe period, creating a pre-restart interval where the replica is likely out of rotation but not yet restarted `[Measured]`
- Liveness-triggered termination interrupts the original blocking request; the request does not survive container restart in this configuration `[Observed]`
- Once the container is recreated, the application can recover immediately if the underlying issue was transient worker saturation rather than persistent application startup failure `[Observed]`

## 13. What this does NOT prove

- That the exact observed timings (~74s to first readiness failure, ~100s to liveness termination, ~49s to recreation) are fixed across all Azure Container Apps regions or infrastructure revisions
- That the same behavior would occur with multiple Gunicorn workers, multiple threads, async workers, or multiple replicas
- That Envoy returned a specific downstream status code to new callers after readiness failure; that routing transition was inferred from probe behavior rather than directly packet-captured
- That the second `ContainerTerminated` event was caused by the same blocking request scenario; it may have been unrelated probe activity during restart or another test artifact
- That CPU exhaustion, memory pressure, or platform infrastructure faults contributed materially to this scenario; the experiment isolated worker-thread saturation behavior only

## 14. Support takeaway

When a customer reports intermittent 503s, probe failures, or restarts in Azure Container Apps, do not assume the platform is killing a healthy app arbitrarily. A single blocked worker can make the replica look dead to readiness and liveness probes.

Support triage pattern for this case:

1. Check whether the app uses very low concurrency settings such as Gunicorn `--workers 1 --threads 1`
2. Review whether one slow endpoint can monopolize the only worker or thread
3. Query `ContainerAppSystemLogs_CL` for readiness and liveness timeout events and compare their order
4. Determine whether readiness failed first, which would explain intermittent 503s or traffic loss before restart
5. Confirm whether the in-flight request duration overlaps the probe failure window; if so, request termination is expected rather than anomalous

Practical support conclusion:

- **If the app is single-worker and one slow request blocks probe endpoints, probe failure is a downstream symptom of worker saturation**
- **If readiness fails before liveness, customers may see traffic loss before they notice the restart**
- **If liveness restarts the container, the blocked request should be treated as lost work unless the app has external checkpointing or retry-safe semantics**

## 15. Reproduction notes

- Use a truly single-concurrency server model. This experiment depends on `--workers 1 --threads 1`; additional workers or threads would weaken or eliminate the effect.
- Keep the blocking request long enough to outlast multiple probe cycles. A short delay may finish before readiness or liveness thresholds are reached.
- Client-side timeouts matter. The blocking request used `--max-time 120` and the probe-validation requests used shorter timeouts to show user-visible failure cleanly.
- Probe timing should be recorded from system logs rather than inferred only from wall-clock expectations; actual first failure can lag the start of the blocking request depending on probe schedule phase.
- Readiness and liveness periods should differ if you want to observe the pre-restart window clearly. In this case, readiness (`5s`) failed before liveness (`10s`).
- Expect log ingestion delay when querying Log Analytics; recent `ContainerAppSystemLogs_CL` entries may appear 1-3 minutes after the event.

## 16. Related guide / official docs

- [Microsoft Learn: Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Microsoft Learn: Troubleshoot health probe failures in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-health-probe-failures)
- [Microsoft Learn: Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Liveness Probe Failure Patterns](../liveness-probe-failures/overview.md) — broader liveness failure patterns, including blocking-I/O and in-flight request effects
- [Startup Probes](../startup-probes/overview.md) — complementary probe sequencing behavior during initialization
