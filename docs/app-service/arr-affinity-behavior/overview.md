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

# ARR Affinity: Session Stickiness During Instance Restart and Scale Events

!!! info "Status: Planned"

## 1. Question

When ARR Affinity (session affinity) is enabled on a multi-instance App Service and the affinity-pinned instance is restarted or removed, what happens to in-flight requests and ongoing client sessions — and does disabling affinity change load distribution measurably under steady-state traffic?

## 2. Why this matters

ARR Affinity pins client sessions to a specific backend instance. When the pinned instance is restarted during a deployment or scale event, clients lose their affinity cookie binding and must reconnect. For stateless applications this may be invisible; for stateful sessions (login tokens cached in memory, WebSocket connections, SignalR) it causes visible errors. Support engineers also encounter cases where one instance consistently handles more traffic than others, which can indicate affinity imbalance under skewed initial distribution — particularly when a small number of clients arrived before others and were all pinned to one instance.

## 3. Customer symptom

"After a deployment or restart, some users get errors and have to log in again" or "One App Service instance is always overloaded while the others are nearly idle" or "Disabling ARR Affinity seemed to fix the load imbalance but I'm not sure why."

## 4. Hypothesis

- H1: With ARR Affinity enabled and a skewed initial load distribution (all clients arrive on instance A before instance B is added), instance A will continue to handle all pinned sessions even as new instances join. The per-instance request count imbalance persists for the lifetime of client sessions.
- H2: When the affinity-pinned instance is restarted, the `ARRAffinity` cookie becomes invalid; the client's next request is routed to any available instance, and a new affinity cookie is set. For stateless apps this causes no error; for session-state-dependent apps this causes a session loss.
- H3: With ARR Affinity disabled, a steady-state workload from N clients distributes across instances directionally more evenly, though exact distribution depends on the round-robin or least-connection routing algorithm in use.
- H4: SignalR and WebSocket connections require affinity at the transport layer; disabling ARR Affinity without a backplane (Azure SignalR Service or Redis) causes reconnections when the load balancer routes a WebSocket upgrade to a different backend.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P2v3 (2 instances) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance / Configuration

**Controlled:**

- Stateless HTTP echo app that returns the instance hostname (`WEBSITE_INSTANCE_ID`) in the response body
- 50 steady clients, each sending 10 req/s
- Instance count: 2 (manually scaled, no auto-scale)

**Observed:**

- Per-instance request count (derived from instance hostname in response body)
- `ARRAffinity` cookie value per client session
- Error count and session-loss events when affinity-pinned instance restarts
- Instance assignment shift after restart

**Scenarios:**

- S1: ARR Affinity enabled; all 50 clients arrive simultaneously; 5-minute load, then restart instance 1
- S2: ARR Affinity disabled; same 50-client load; 5 minutes
- S3: SignalR WebSocket connection with ARR Affinity enabled vs. disabled; restart instance mid-connection

**Independent run definition**: One 5-minute load test pass per scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- App response body: each response includes `WEBSITE_INSTANCE_ID` — parsed by load test client to attribute requests per instance
- `ARRAffinity` and `ARRAffinitySameSite` cookie values in HTTP response headers — captured per client
- Load testing tool: `locust` with session-preserving HTTP client per user
- Error count in load test output: HTTP 5xx or connection errors during instance restart
- App Service Activity Log — restart events and timing

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy stateless Flask app that returns `WEBSITE_INSTANCE_ID` and echoes `ARRAffinity` cookie.
2. S1: Enable ARR Affinity; start 50 clients simultaneously; run 5 minutes; restart instance 1 at T+3min; record per-instance counts and error spikes.
3. S2: Disable ARR Affinity (`az webapp update --client-affinity-enabled false`); repeat same load; compare per-instance distribution.
4. (Optional) S3: Establish WebSocket connection; restart backend instance; observe reconnection behavior with and without affinity.
5. For each scenario, compute per-instance request fraction from response body data.

## 9. Expected signal

- S1: Instance 1 handles proportionally more requests when initial clients land on it; restart causes brief error spike as cookies invalidate; clients re-pin to surviving instance or new instance.
- S2: Per-instance request fractions are closer across both instances; no session loss events.
- S3: WebSocket connection drops when backend restarts; without affinity, the next upgrade may hit a different instance; with affinity, reconnect targets the same instance once it recovers.

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

- Disable ARR Affinity via `az webapp update --name <app> --resource-group <rg> --client-affinity-enabled false`.
- Per-instance metrics from the platform aggregate across instances by default; use the app's response body (returning `WEBSITE_INSTANCE_ID`) for precise per-instance attribution.
- The `ARRAffinity` cookie is set by the platform, not the application; it cannot be suppressed from application code.
- SignalR without Azure SignalR Service requires ARR Affinity to maintain WebSocket connections; disabling affinity in that configuration is a known support scenario.

## 16. Related guide / official docs

- [Configure an App Service app — session affinity](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [ARR Affinity and SignalR on Azure App Service](https://learn.microsoft.com/en-us/aspnet/core/signalr/scale?view=aspnetcore-8.0#azure-app-service)
- [Robust apps for the cloud — App Service best practices](https://azure.github.io/AppService/2020/05/15/Robust-Apps-for-the-Cloud.html)
