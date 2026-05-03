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

# Deployment Slots Traffic Split: Percentage Routing Behavior and Latency Impact

!!! info "Status: Planned"

## 1. Question

App Service deployment slots support percentage-based traffic routing for A/B testing. When traffic is split (e.g., 10% to staging, 90% to production), how exactly does the routing work for returning users — is the split stateless (random per request) or stateful (sticky per user session)? And what is the performance overhead of the traffic split mechanism?

## 2. Why this matters

Teams use percentage traffic routing to gradually roll out new versions. The routing mechanism affects test validity: if the split is per-request (not per-user), the same user may hit different slot versions across requests within the same session, producing inconsistent behavior rather than a true A/B test. Understanding whether the split is sticky by default and how the `x-ms-routing-name` cookie works is essential for designing valid experiments and for understanding user experience during the rollout.

## 3. Customer symptom

"Users report seeing two different versions of the app in the same session during our gradual rollout" or "Our A/B test results are skewed because users are hitting both versions" or "After adding traffic routing, some users experience slightly higher latency."

## 4. Hypothesis

- H1: App Service percentage traffic routing sets an `x-ms-routing-name` cookie after the first request to pin subsequent requests from the same browser to the same slot. The initial request is random based on the configured percentage; all subsequent requests from that browser are sticky to the assigned slot.
- H2: The `x-ms-routing-name` cookie can be set manually by the client (by adding `x-ms-routing-name=staging` to the request) to force routing to a specific slot, enabling testing without changing the percentage. This is by design and documented.
- H3: The percentage routing header check adds a small but measurable overhead to each request (approximately 1-5ms) compared to a single-slot deployment with no routing configured.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 (with staging slot) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Platform behavior / Deployment

**Controlled:**

- Production slot (version A) and staging slot (version B) with visually distinguishable responses
- Traffic routing: 10% to staging, 90% to production

**Observed:**

- `x-ms-routing-name` cookie presence and value after first request
- Slot received by subsequent requests from the same browser
- Request latency with and without traffic routing configured

**Scenarios:**

- S1: First request — observe which slot responds and cookie value set
- S2: Subsequent requests with cookie — verify sticky routing
- S3: Manually set `x-ms-routing-name=staging` — verify forced routing
- S4: Measure latency overhead of routing vs. no routing

## 7. Instrumentation

- Browser DevTools to observe `Set-Cookie: x-ms-routing-name` header
- App response body indicating which slot version is serving (`{"slot": "production"}` vs. `{"slot": "staging"}`)
- Apache Bench for latency measurement with and without routing
- App Service **Deployment slots** blade showing traffic percentage

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy version A to production, version B to staging (different response bodies).
2. Configure 10% routing to staging.
3. S1: Send 100 requests without cookies; record which slot each lands on; verify ~10% go to staging.
4. S2: Take the cookie from a request routed to staging; send 10 subsequent requests with that cookie; verify all go to staging.
5. S3: Send a request with `Cookie: x-ms-routing-name=staging`; verify forced routing to staging regardless of the 10% probability.
6. S4: Measure p50/p95 latency with routing at 10% vs. with routing disabled (0% / 100%); compare.

## 9. Expected signal

- S1: Approximately 10% of requests go to staging (with statistical variance for small N); each response includes a `Set-Cookie: x-ms-routing-name=<slot>` header.
- S2: All 10 subsequent requests with the staging cookie go to staging (sticky routing confirmed).
- S3: Request with manual cookie goes to staging (forced routing works).
- S4: Latency difference between routing-on and routing-off is less than 5ms at p50.

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

- Traffic routing percentage is configured via: **Deployment slots** → click staging slot → **Traffic %** slider, or via `az webapp traffic-routing set --distribution staging=10`.
- The `x-ms-routing-name` cookie is set by the App Service frontend and cannot be overridden by the application.
- Setting `x-ms-routing-name=self` routes to production slot (self-routing).

## 16. Related guide / official docs

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Route production traffic manually](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#route-production-traffic-automatically)
