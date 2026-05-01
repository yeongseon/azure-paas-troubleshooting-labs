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

# App Service Plan Scale-Out Timing: Instance Warmup, In-Flight Request Handling, and State Retention

!!! info "Status: Planned"

## 1. Question

When an App Service plan scales out from N to N+1 instances, what is the time between the scale decision and the new instance serving traffic — and during the scale-out window, are in-flight requests affected, does traffic distribution shift immediately, and is any per-instance state (e.g., local disk writes, in-memory cache) visible to the new instance?

## 2. Why this matters

App Service plan auto-scale events are often invisible to operators until they cause problems. A scale-out adds a new instance but that instance must start the application runtime before it can serve traffic. During this warmup period, the load balancer may or may not route requests to the new instance. Per-instance state (files written to the writable layer, in-memory caches) is not shared across instances. Customers who assume shared state across instances encounter data consistency issues after scale-out that only appear under load.

## 3. Customer symptom

"After auto-scale triggered, some users started getting errors even though the app was healthy" or "My app writes to a local file and the data disappears after a scale event" or "The new instance takes a long time to become available — why?"

## 4. Hypothesis

- H1: There is a measurable warmup delay between a scale-out decision and the new instance serving its first request. During this window, all traffic is served by the existing instance(s). The warmup time includes OS provisioning, application runtime startup, and application initialization.
- H2: The App Service load balancer begins routing requests to the new instance as soon as the instance's HTTP listener is ready — before any application-level warmup logic completes. If the application has a slow initialization path (e.g., loading a large model, establishing a connection pool), early requests to the new instance may experience high latency or errors.
- H3: Per-instance writable storage (the container's writable layer, `/tmp`) is not shared across instances. Data written by instance A is not visible to instance B. The `/home` path (shared persistent storage, if enabled) is shared and visible to all instances.
- H4: ARR Affinity, when enabled, pins a session to a specific instance via a cookie. When that instance is removed during scale-in, the session cookie becomes invalid and the client's next request is routed to a different instance without any error indication to the application.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P2v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Platform behavior / Scalability

**Controlled:**

- App Service on P2v3, manual scale-out from 1 to 2 instances
- Application: FastAPI with a `/instance` endpoint returning `WEBSITE_INSTANCE_ID`, a `/write` endpoint writing to `/tmp/test.txt`, and a `/read` endpoint reading from `/tmp/test.txt`
- ARR Affinity: tested both enabled and disabled

**Observed:**

- Time from scale-out trigger to first request served by new instance (`WEBSITE_INSTANCE_ID` change)
- Request error rate during scale-out window
- Latency distribution before, during, and after scale-out
- `/tmp/test.txt` visibility across instances (H3)
- ARR cookie behavior after scale-in removes the pinned instance (H4)

**Scenarios:**

- S1: Manual scale-out 1→2 — measure warmup time and first-request latency on new instance
- S2: Slow-init application (5-second delay in startup) — measure error rate during scale-out
- S3: Write to `/tmp` on instance A — attempt read from instance B — confirm isolation
- S4: ARR Affinity enabled — scale-in removes pinned instance — observe client behavior

**Independent run definition**: One scale event per scenario; continuous load during scale event.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Application log: `WEBSITE_INSTANCE_ID` per request — detect when new instance starts serving
- Load generator: `hey -n 1000 -c 10 https://<app>.azurewebsites.net/instance` — continuous requests during scale
- Error rate: count of non-2xx responses during scale window
- Response time: p50/p95/p99 before and after scale-out
- `/tmp` isolation test: `POST /write` → `GET /read` from a different instance (identified by `WEBSITE_INSTANCE_ID` in response)
- ARR cookie inspection: `curl -c cookies.txt -b cookies.txt https://<app>.azurewebsites.net/instance` — confirm cookie persistence and instance binding

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy app to 1-instance P2v3; warm up with 100 requests; start continuous load generator.
2. S1: Manually scale to 2 instances via `az appservice plan update --number-of-workers 2`; record timestamp; monitor responses for new `WEBSITE_INSTANCE_ID` to appear; measure time delta.
3. S2: Deploy slow-init variant (5-second sleep in startup); repeat scale-out; count error responses during warmup window.
4. S3: Use load balancer round-robin (ARR Affinity disabled) to send `/write` to one instance and `/read` to another; confirm `/tmp` is not shared.
5. S4: Enable ARR Affinity; pin session to instance A via cookie; scale in to remove instance A; observe next request — is session lost gracefully or with an error?

## 9. Expected signal

- S1: New instance appears in response pool within 2–5 minutes of scale trigger; no errors during warmup if initialization is fast.
- S2: During the warmup window for the slow-init instance, requests routed to it return 5xx or time out; errors clear once initialization completes.
- S3: `/read` on a different instance returns 404 (file not found); `/tmp` is instance-local; `/home` (if enabled) would be shared.
- S4: After scale-in removes the pinned instance, the ARR cookie becomes stale; next request is routed to a remaining instance; no HTTP error is returned to the client, but server-side session state (if any) is lost.

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

- `WEBSITE_INSTANCE_ID` is an environment variable available in each App Service instance; logging it per request is the most reliable way to identify which instance served a request.
- Manual scale-out via `az appservice plan update` is synchronous from the API perspective but asynchronous from the instance provisioning perspective; the API returns before the new instance is ready.
- `/home` persistent storage must be explicitly enabled (`WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`) and is mounted via Azure Files; latency characteristics differ from `/tmp`.
- ARR Affinity cookie is named `ARRAffinity` and `ARRAffinitySameSite`; it is set by the platform, not the application.

## 16. Related guide / official docs

- [Scale up an app in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/manage-scale-up)
- [Auto-scale in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/manage-automatic-scaling)
- [App Service plan — multi-instance behavior](https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans)
- [ARR Affinity in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
