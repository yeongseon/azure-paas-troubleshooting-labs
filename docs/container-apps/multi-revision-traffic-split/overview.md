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

# Multi-Revision Traffic Split to Unhealthy Revision

!!! info "Status: Published (2026-04-14)"

## 1. Question

When an unhealthy revision receives traffic through percentage-based traffic splitting in Azure Container Apps multi-revision mode, what failure patterns do end-users experience, and does rolling back traffic to 100% healthy revision immediately resolve the issue?

## 2. Why this matters

Multi-revision mode is often used for gradual rollout, canary validation, and low-risk deployment testing. In support cases, customers may assume that an unhealthy or failed revision is automatically excluded from the traffic pool. If that assumption is wrong, a small traffic weight on a bad revision can create intermittent customer-visible failures that look random from the client side.

This matters for cases such as:

- partial outage after a canary rollout
- intermittent timeout reports with no obvious platform-wide failure
- confusion about whether a `Failed` revision can still receive live traffic
- rollback decisions during incident mitigation

## 3. Customer symptom

Typical ticket phrasing:

- "We shifted 10% traffic to a new revision and now a small percentage of requests time out."
- "One revision is unhealthy, but users are still seeing intermittent failures."
- "The app mostly works, but some requests hang during the rollout."
- "Does Container Apps automatically stop sending traffic to a failed revision, or do we need to remove it ourselves?"
- "After we rolled traffic back, errors stopped immediately. Was the bad revision still in rotation?"

## 4. Hypothesis

1. In multi-revision mode with traffic split (for example, 90% v1 healthy and 10% v2 unhealthy), requests routed to the unhealthy revision will fail while requests routed to the healthy revision succeed normally.
2. The client-visible failure rate will approximately match the traffic weight assigned to the unhealthy revision.
3. Rolling back traffic to 100% healthy revision will immediately stop the errors.

## 5. Environment

| Parameter | Value |
|---|---|
| Service | Azure Container Apps |
| Hosting model | Managed environment (Consumption) |
| Region | `koreacentral` |
| Runtime | Python 3.11, Flask + Gunicorn |
| Container image | `acrhealthprobelabb7db7c.azurecr.io/health-probe-lab:v1` |
| Ingress | External, target port 8080 |
| Revision mode | Multiple |
| App name | `ca-multi-rev` |
| Date tested | 2026-04-13 |

## 6. Variables

**Controlled**

- Revision mode: multiple
- Traffic split: v1=`90%`, v2=`10%`
- v1 startup delay: `0` seconds
- v2 startup delay: `120` seconds
- Startup probe budget: `failureThreshold=12`, `periodSeconds=5`, `timeoutSeconds=2`
- Liveness probe: HTTP GET `/live`, `periodSeconds=10`, `timeoutSeconds=3`, `failureThreshold=3`
- Readiness probe: HTTP GET `/ready`, `periodSeconds=5`, `timeoutSeconds=3`, `failureThreshold=3`
- Startup probe: HTTP GET `/startup`, `periodSeconds=5`, `timeoutSeconds=2`, `failureThreshold=12`
- Request sample size during split test: 20 requests
- Request sample size after rollback: 20 requests

**Observed**

- Revision `healthState`
- Revision `runningState`
- Configured `trafficWeight`
- System log restart pattern for v2
- HTTP response codes seen by end-users during split test
- HTTP response codes seen through direct revision URLs
- HTTP response codes after rollback to 100% healthy revision

## 7. Instrumentation

- **Azure Container Apps revision state** to verify `healthState`, `runningState`, and traffic weight per revision
- **Container App system logs** to capture startup probe failures, container termination, recreation, and restart-loop timing
- **Synthetic HTTP requests** to the application endpoint to measure client-visible success/failure under a 90/10 split
- **Direct revision URL requests** to isolate healthy-revision behavior from failed-revision behavior
- **Traffic reconfiguration via Azure CLI** to test rollback behavior immediately after the split scenario

## 8. Procedure

### Revision setup

- **v1**: `APP_NAME=ca-multi-rev-v1`, `STARTUP_DELAY_SECONDS=0` → starts immediately and passes probes
- **v2**: `APP_NAME=ca-multi-rev-v2`, `STARTUP_DELAY_SECONDS=120` → startup delayed by 120 seconds

### Probe setup

Both revisions used the same probes:

- Startup: HTTP GET `/startup`, `period=5s`, `timeout=2s`, `failureThreshold=12`
- Liveness: HTTP GET `/live`, `period=10s`, `timeout=3s`, `failureThreshold=3`
- Readiness: HTTP GET `/ready`, `period=5s`, `timeout=3s`, `failureThreshold=3`

The startup probe budget for each revision was 60 seconds (`12 × 5s`). Because v2 required 120 seconds before startup completion, it never passed the startup probe and entered a repeated failure cycle.

### Execution steps

1. Deploy `ca-multi-rev` in **multiple revision** mode.
2. Create revision v1 with immediate startup and verify it becomes healthy.
3. Create revision v2 with `STARTUP_DELAY_SECONDS=120` and observe whether it can pass the startup probe.
4. Configure traffic weights to `ca-multi-rev--v1=90` and `ca-multi-rev--v2=10`.
5. Record revision states and system log events for both revisions.
6. Send 20 requests to the application endpoint and record HTTP outcomes.
7. Send requests directly to the v1 and v2 revision URLs to isolate each revision's behavior.
8. Roll traffic back with:

```bash
az containerapp ingress traffic set --revision-weight ca-multi-rev--v1=100 ca-multi-rev--v2=0
```

9. Send another 20 requests after rollback and record whether failures stop immediately.

## 9. Expected signal

- v1 should remain `Healthy` and serve requests normally.
- v2 should fail startup probe validation, enter `Unhealthy` / `Failed`, and restart repeatedly.
- During the 90/10 traffic split, a minority of client requests should fail when routed to v2, while most requests should succeed through v1.
- The observed client failure rate should be roughly aligned with the 10% weight assigned to v2, allowing for small-sample variance.
- After traffic is rolled back to 100% v1, client-visible failures should stop immediately.

## 10. Results

**Execution Date**: 2026-04-13  
**App**: `ca-multi-rev`  
**Revision mode**: Multiple

### Revision states

| Revision | healthState | runningState | trafficWeight |
|---|---|---|---|
| v1 | Healthy | RunningAtMaxScale | 90 |
| v2 | Unhealthy | Failed | 10 |

### v2 system logs

v2 entered a restart loop. Four restart cycles were observed over approximately four minutes:

```text
15:20:06 — Container terminated (ProbeFailure) — restart #1
15:20:16 — Container recreated
15:20:21–15:21:16 — Startup probe failed repeatedly (503)
15:21:16 — Container terminated (ProbeFailure) — restart #2
15:21:36 — Container recreated
15:21:41–15:22:36 — Startup probe failed repeatedly (503)
15:22:36 — Container terminated (ProbeFailure) — restart #3
15:23:16 — Container recreated
15:23:21–15:23:51 — Startup probe failed repeatedly (503)
...continues
```

### v1 system logs

v1 remained clean. Only normal deployment events were present: `RevisionCreation`, `ContainerCreated`, `ContainerStarted`, and `RevisionReady`.

### Traffic test with 90/10 split

20 requests were sent through the application endpoint.

| Outcome | Count |
|---|---|
| HTTP 200 (v1) | 19 |
| HTTP 000 (timeout — routed to failed v2) | 1 |

- Observed failure rate: `5%` (`1/20`)
- Expected failure rate from configured traffic weight: `~10%`
- Deviation is consistent with the small sample size

### Direct revision URL tests

| Target | Result |
|---|---|
| v1 direct (`ca-multi-rev--v1.victoriouswater-301ca985...`) | HTTP 200 consistently; response showed `revision=ca-multi-rev--v1`, `request_count=177` |
| v2 direct | HTTP 000 (timeout) |

v2 never completed startup and remained in a failed state.

### Rollback test

Traffic was changed to 100% v1 and 0% v2 using:

```bash
az containerapp ingress traffic set --revision-weight ca-multi-rev--v1=100 ca-multi-rev--v2=0
```

20 requests were sent immediately after rollback.

| Outcome | Count |
|---|---|
| HTTP 200 | 20 |
| HTTP 000 / other failures | 0 |

The client-visible error rate dropped from approximately `5%` during the split test to `0%` immediately after rollback.

## 11. Interpretation

### Evidence summary

| Evidence Type | Finding |
|---|---|
| `[Observed]` | v1 stayed `Healthy` / `RunningAtMaxScale` while v2 was `Unhealthy` / `Failed` with a 10% traffic weight |
| `[Observed]` | v2 entered a perpetual restart loop because startup never completed before the startup probe budget was exhausted |
| `[Observed]` | During the traffic split, end-users experienced mixed outcomes: successful requests through v1 and timeouts through v2 |
| `[Observed]` | Direct requests to v2 timed out, while direct requests to v1 consistently returned HTTP 200 |
| `[Measured]` | Split test result was 19/20 successful and 1/20 timed out, for a 5% observed failure rate |
| `[Measured]` | Rollback test result was 20/20 successful immediately after traffic moved to 100% v1 |
| `[Correlated]` | The only failed client request in the split test aligns with the presence of a 10% traffic weight on the failed revision |
| `[Inferred]` | Azure Container Apps did not automatically exclude the failed revision from percentage-based traffic routing in this scenario |

### Key findings

1. **Traffic was still routed to the failed revision** `[Observed]`

    v2 remained configured with `trafficWeight=10` even though its state was `Unhealthy` / `Failed`. The split test produced a timeout outcome consistent with some requests continuing to reach that revision.

2. **Client-visible failure mode was timeout, not an application-generated HTTP error** `[Observed]`

    Requests routed to v2 returned HTTP 000 rather than an HTTP 5xx response body. In this test, the failed revision behaved as an unreachable backend from the client's perspective.

3. **Blast radius matched the traffic share, not the entire app** `[Correlated]`

    The healthy revision continued serving requests normally. Only the portion of traffic exposed to v2 was at risk, which is why the outage appeared intermittent rather than total.

4. **Observed failure rate was directionally consistent with traffic weight** `[Measured]`

    The measured failure rate was 5% versus an expected ~10%. With only 20 requests, this is consistent with sampling variance and does not contradict the weighted-routing expectation.

5. **Rollback removed the issue immediately** `[Measured]`

    After moving traffic to `ca-multi-rev--v1=100` and `ca-multi-rev--v2=0`, the next 20 requests all succeeded. No delay was observed between rollback and recovery from the client perspective.

### Hypothesis validation

| Hypothesis | Result | Evidence |
|---|---|---|
| Requests routed to unhealthy v2 fail while requests routed to healthy v1 succeed | **Confirmed** | Split test + direct revision URL tests |
| Failure rate approximately matches unhealthy revision traffic weight | **Confirmed with small-sample variance** | 5% observed vs ~10% expected from 20 requests |
| Rolling back traffic to 100% healthy revision immediately stops errors | **Confirmed** | 20/20 HTTP 200 immediately after rollback |

## 12. What this proves

Within this test setup, the experiment proved the following:

- A revision in `Unhealthy` / `Failed` state can still receive live traffic if it retains a non-zero configured traffic weight in multi-revision mode `[Observed]`
- Requests routed to that failed revision can surface as client timeouts (`HTTP 000`) rather than an application-generated HTTP error response `[Observed]`
- The healthy revision can continue serving its portion of requests normally while the unhealthy revision produces intermittent failures `[Observed]`
- The customer-visible failure rate tracks the unhealthy revision's assigned traffic percentage directionally, though small request samples can deviate from the configured weight `[Measured]`
- Setting the unhealthy revision's traffic weight to 0% immediately eliminated the observed failures in this scenario `[Measured]`

## 13. What this does NOT prove

- That every failed revision in Azure Container Apps will always produce `HTTP 000`; other failure modes may return different client behaviors
- That the weighted failure rate will exactly equal the configured percentage in small samples
- That Container Apps never skips failed revisions under any other routing mode, health state transition, or future platform version
- That rollback timing is identical under higher load, multiple replicas, or different regions
- That readiness or liveness probe failures would produce the same client pattern as this startup-probe-driven failure case

## 14. Support takeaway

When a customer reports intermittent failures during a multi-revision rollout, do not assume Azure Container Apps automatically removes a failed revision from traffic rotation.

Recommended support workflow:

1. Check revision traffic weights first, not just revision health state.
2. If a revision is `Unhealthy` or `Failed` and still has non-zero traffic, treat it as an active contributor to client errors.
3. Compare the customer's observed error rate with the configured traffic split. A small but non-zero error rate can map directly to canary weight.
4. Test the app endpoint and the direct revision URLs separately to isolate which revision is failing.
5. For mitigation, set the unhealthy revision's weight to `0%` or shift traffic to the known healthy revision.

For this scenario, the practical incident rule is simple: **traffic weight is authoritative for exposure**. If a failed revision still has traffic assigned, customers can still hit it.

## 15. Reproduction notes

- The critical trigger in this experiment was the mismatch between v2 startup delay (`120s`) and startup probe budget (`60s`). Without that mismatch, the failed-revision behavior would not reproduce.
- Small request samples can understate or overstate the configured weight. The 20-request split test produced 5% observed failure even though v2 held 10% traffic.
- Direct revision URL testing is useful for separating routing behavior from application health. In this experiment it clearly distinguished v1 success from v2 timeout behavior.
- The restart-loop evidence came from system logs, while the customer-visible symptom came from endpoint testing. Both views were necessary to connect platform state to user impact.

## 16. Related guide / official docs

- [Microsoft Learn: Traffic splitting in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting)
- [Microsoft Learn: Revisions in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Microsoft Learn: Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Startup Probes experiment](../startup-probes/overview.md)
- [Container Apps Labs Overview](../index.md)
