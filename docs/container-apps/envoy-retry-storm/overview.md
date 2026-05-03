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

# Envoy Retry Storm: Upstream Overload from Automatic Retries

!!! info "Status: Planned"

## 1. Question

Container Apps ingress uses Envoy proxy, which may perform automatic HTTP retries for certain response codes (5xx). When the upstream container is returning 503 due to overload, does Envoy's retry behavior amplify the load (retry storm), and what observable pattern does this create in metrics?

## 2. Why this matters

Envoy-level automatic retries are designed to improve reliability, but when the upstream service is genuinely overloaded (returning 503 due to resource exhaustion), automatic retries multiply the load. A service receiving 100 requests per second and returning 503s may receive 200-300 requests per second from Envoy retries, making the overload worse and preventing recovery. Understanding whether Container Apps Envoy performs automatic retries, under what conditions, and whether they can be disabled is critical for services that use 503 as a legitimate backpressure signal.

## 3. Customer symptom

"The app gets worse when it starts returning 503 errors — the load seems to increase when we're already overloaded" or "503 errors cascade — a small overload becomes a total outage quickly" or "Metrics show 3× more requests than our clients are sending during an incident."

## 4. Hypothesis

- H1: Container Apps Envoy proxy retries requests that receive a 5xx response from the upstream container, with a configurable number of retry attempts. The default retry policy is 2 retries on 5xx, meaning each failing request from the client becomes up to 3 requests to the upstream.
- H2: During an upstream overload scenario (upstream returns 503), Envoy retries amplify the inbound request rate to the upstream, potentially by a factor of 2-3×, accelerating the overload rather than allowing recovery.
- H3: The retry behavior is visible in Container Apps metrics: `Requests` count at the ingress layer is higher than the actual client request rate during a 503 storm. The delta between ingress requests and upstream requests is the retry amplification factor.
- H4: Returning HTTP 429 (Too Many Requests) instead of 503 may not trigger Envoy retries (depends on Envoy's default retry policy for 429), providing better backpressure signaling.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Reliability

**Controlled:**

- Container app that returns 503 for all requests above a configurable threshold
- Load generator at a known request rate
- Measurement of actual requests reaching the container vs. requests sent by the client

**Observed:**

- Request amplification factor (client requests vs. upstream requests)
- Behavior with 503 vs. 429 response codes
- Recovery time after overload resolves

**Scenarios:**

- S1: Upstream returns 200 → 1:1 ratio (no retries)
- S2: Upstream returns 503 → observe amplification
- S3: Upstream returns 429 → observe if retries occur

## 7. Instrumentation

- Container application log counting inbound requests (application-side counter)
- Client-side request counter (Apache Bench)
- Azure Monitor `Requests` metric for the container app
- Ratio: (application-side count) / (client-side count) = amplification factor

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy app with `/always-200`, `/always-503`, and `/always-429` endpoints. Log each request to application log with timestamp.
2. S1: Send 100 requests to `/always-200`; verify application log shows 100 requests (1:1).
3. S2: Send 100 requests to `/always-503`; count application log entries; compare to 100 (expect >100 due to retries).
4. S3: Send 100 requests to `/always-429`; count application log entries; compare.

## 9. Expected signal

- S1: Application receives exactly 100 requests.
- S2: Application receives >100 requests (100 × retry_factor); Azure Monitor shows elevated `Requests` count.
- S3: Application receives 100 or less requests if 429 suppresses retries; same if 429 also triggers retries.

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

- Container Apps ingress is built on Envoy proxy. Envoy's default retry policy and which status codes trigger retries depend on the platform version.
- The official Container Apps documentation does not expose retry policy configuration as of 2026. This experiment aims to observe actual behavior.
- To implement explicit backpressure, consider returning 503 with `Retry-After` header and observing whether the ingress honors it.

## 16. Related guide / official docs

- [Container Apps ingress overview](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Envoy retry policies](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter#x-envoy-retry-on)
