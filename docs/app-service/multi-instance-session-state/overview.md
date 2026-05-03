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

# Multi-Instance Session State Inconsistency Without Sticky Sessions

!!! info "Status: Planned"

## 1. Question

When an App Service plan is scaled out to multiple instances and the application maintains server-side session state (in-memory, filesystem, or local cache), requests from the same client may be routed to different instances without ARR Affinity. What is the observable behavior when session state is not found on a different instance, and how does it differ from sticky session (ARR Affinity enabled) behavior?

## 2. Why this matters

Many legacy applications store session state in-process or on the local filesystem, assuming all requests from the same user go to the same server. This assumption breaks in a multi-instance App Service deployment without ARR Affinity. Users experience random session loss, unexpected logouts, or data inconsistency proportional to the number of instances and the round-robin distribution of requests. The failure is non-deterministic and difficult to reproduce in single-instance test environments.

## 3. Customer symptom

"Users get logged out randomly even though we haven't changed anything" or "Shopping cart contents disappear intermittently" or "Some users are fine but others keep losing their session — it seems to affect about half our users."

## 4. Hypothesis

- H1: Without ARR Affinity, the App Service frontend routes requests round-robin across instances. A user's first request is handled by instance A (session created), the second by instance B (session not found → session loss or re-authentication). The probability of session loss is `(N-1)/N` on the second request for N instances.
- H2: With ARR Affinity enabled, the frontend sets an `ARRAffinity` cookie that pins subsequent requests from the same client to the same instance. Session state is consistently found. The cost is reduced load balancing effectiveness (sticky sessions create hot instances).
- H3: The correct fix for stateless multi-instance deployments is to use an external session store (Redis Cache, Azure SQL) rather than ARR Affinity, which prevents stateful in-process storage from being a single point of failure.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 (scaled to 2 instances) |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask with in-memory session) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Platform behavior / State management

**Controlled:**

- Flask app with server-side session (stored in-memory on each instance)
- ARR Affinity enabled and disabled
- Scale set to 2 instances

**Observed:**

- Session persistence across requests from the same client
- Which instance handles each request (visible via `X-MS-Session-Id` or instance ID endpoint)
- Session hit vs. miss rate

**Scenarios:**

- S1: ARR Affinity ON, 2 instances → session always found
- S2: ARR Affinity OFF, 2 instances → session lost on approximately 50% of requests
- S3: ARR Affinity OFF + Redis-backed session store → session always found regardless of instance

## 7. Instrumentation

- Response header `X-Instance-Id` (custom header added by the app, reporting `os.environ['WEBSITE_INSTANCE_ID']`)
- Session endpoint that stores and retrieves a counter value per session
- Azure Monitor `Requests` metric split by instance to verify load distribution

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Flask app with `/session-set?key=counter&val=1` and `/session-get?key=counter` endpoints; each response includes the current instance ID.
2. Scale to 2 instances.
3. S1: Enable ARR Affinity; repeat `/session-set` then `/session-get` 20 times; verify counter always increments on same instance.
4. S2: Disable ARR Affinity (delete `ARRAffinity` cookie from client); repeat; observe that some `/session-get` calls return "counter not found" (different instance).
5. S3: Configure Azure Cache for Redis as session backend; repeat S2; verify counter is consistent across instances.

## 9. Expected signal

- S1: All requests hit the same instance; session counter increments correctly.
- S2: Approximately 50% of requests hit a different instance; those requests find no session and return empty or default counter value.
- S3: All requests find the session regardless of instance; counter increments correctly.

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

- ARR Affinity is controlled via **Configuration > General settings > ARR Affinity** or `az webapp update --set properties.clientAffinityEnabled=false`.
- The `ARRAffinity` and `ARRAffinitySameSite` cookies are set by the App Service frontend when affinity is enabled.
- `WEBSITE_INSTANCE_ID` environment variable contains the unique identifier of the current instance.

## 16. Related guide / official docs

- [ARR Affinity in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [Azure Cache for Redis session provider for ASP.NET](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-aspnet-session-state-provider)
