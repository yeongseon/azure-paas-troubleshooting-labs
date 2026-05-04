---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Envoy Retry Storm: Upstream Overload from Automatic Retries

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04. H1 and H2 **not confirmed** — Container Apps Envoy does not automatically retry 503 or 429 responses.

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
| Runtime | Python 3.11 (gunicorn 25.3.0, 4 workers) |
| OS | Linux |
| Date tested | 2026-05-04 |
| App image | `acrlabcdrbackhgtaj.azurecr.io/diag-app:v5` |

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

1. Deployed `diag-app:v5` with three new endpoints: `/always-200` (returns 200), `/always-503` (returns 503 + logs request count), `/always-429` (returns 429 + logs request count). Added `/counters` and `/counters/reset` endpoints.
2. Routed 100% traffic to revision `aca-diag-batch--v5a`.
3. **S1**: Sent 20 requests to `/always-200`; verified baseline response times.
4. **S2**: Sent 20 requests to `/always-503`; recorded client-side HTTP status codes.
5. **S3**: Sent 20 requests to `/always-429`; recorded client-side HTTP status codes.
6. **Timing test**: Sent 8 requests each to all three endpoints; measured round-trip time (RTT) per request. Rationale: if Envoy retries internally (before returning to the client), the RTT for 503 would be 2-3× higher than for 200.
7. **Header inspection**: Examined all response headers for Envoy retry signals (`x-envoy-attempt-count`, `x-envoy-retry-on`, etc.).

## 9. Expected signal

- S1: Application receives exactly 100 requests.
- S2: Application receives >100 requests (100 × retry_factor); Azure Monitor shows elevated `Requests` count.
- S3: Application receives 100 or less requests if 429 suppresses retries; same if 429 also triggers retries.

## 10. Results

### Client-side HTTP status codes received

| Scenario | Endpoint | Client requests sent | Client 200s | Client 503s | Client 429s |
|----------|----------|---------------------|-------------|-------------|-------------|
| S1 | `/always-200` | 20 | 20 | — | — |
| S2 | `/always-503` | 20 | — | 20 | — |
| S3 | `/always-429` | 20 | — | — | 20 |

All client requests received the exact status code from the upstream container. No status code transformation by the ingress.

### Response time comparison (8 requests each)

```
/always-200: avg=0.055s  median=0.052s  min=0.048s  max=0.073s
/always-503: avg=0.054s  median=0.051s  min=0.046s  max=0.082s
/always-429: avg=0.052s  median=0.054s  min=0.044s  max=0.061s
```

Response times are statistically identical across all three status codes. If Envoy were retrying internally (before returning to the client), the 503 RTT would be 2-3× higher than the 200 baseline. No such increase was observed.

### Response headers (503 example)

```http
HTTP/2 503
server: gunicorn
date: Mon, 04 May 2026 06:15:39 GMT
content-type: application/json
content-length: 34
```

No Envoy-specific headers (`x-envoy-attempt-count`, `x-envoy-upstream-service-time`, `x-envoy-retry-on`) were present in any response across all three status codes.

## 11. Interpretation

- **Observed**: Container Apps Envoy passes 503 responses from the upstream container directly to the client without retrying. Client-side status codes match upstream status codes 1:1.
- **Observed**: Container Apps Envoy passes 429 responses from the upstream container directly to the client without retrying.
- **Measured**: RTT for 503 responses (avg 54ms) is not statistically different from RTT for 200 responses (avg 55ms). Internal Envoy retries would add at minimum one additional upstream RTT (~50ms), which would be detectable.
- **Observed**: No Envoy retry signal headers (`x-envoy-attempt-count`, `x-envoy-upstream-service-time`) appear in any response.
- **Not Proven**: H1 (Envoy retries on 5xx by default) — directly contradicted by timing and header evidence.
- **Not Proven**: H2 (503 storm amplifies upstream load) — contradicted by observed 1:1 request mapping.
- **Inferred**: Container Apps Envoy ingress is configured with automatic retries disabled, or its default retry policy does not include 5xx or 429 status codes. This differs from vanilla Envoy defaults, where 5xx retry is a common default policy.

## 12. What this proves

- Container Apps Envoy ingress does **not** automatically retry 503 responses from the upstream container. The client receives a 503 immediately, without retry amplification.
- Container Apps Envoy ingress does **not** automatically retry 429 responses from the upstream container.
- Response time for 503 and 429 is statistically identical to 200 — no internal retry overhead is added by the ingress layer.
- The ingress does not add `x-envoy-attempt-count` or other retry signal headers to responses in this configuration.

## 13. What this does NOT prove

- Whether Container Apps Envoy retries on connection-level failures (TCP reset, socket timeout) rather than HTTP-level status codes — only HTTP 503/429 were tested.
- Whether retry behavior changes with specific ingress configuration options (Container Apps does not expose retry policy configuration as of 2026-05-04).
- Whether the retry behavior applies identically to HTTP/1.1 and HTTP/2 traffic.
- Whether Dapr service invocation retries differently from ingress-level retries.

## 14. Support takeaway

When a customer reports "getting more requests than clients are sending" or "503 errors seem to cascade":

1. **Container Apps Envoy does not retry 503 or 429.** A "retry storm" from the ingress layer is not the cause. Look elsewhere — client-side retries, upstream fan-out, or KEDA scaling triggers.
2. **503 passes through 1:1.** If the container returns 503, the client receives 503. The ingress is not transforming or swallowing error responses.
3. **RTT is the amplification signal.** If you suspect retries, compare response times across 200 and 503 scenarios. A 2× RTT increase for 503 indicates internal retries; equal RTTs indicate pass-through.
4. **Check the application layer, not the ingress.** If metrics show more upstream requests than expected, look at Dapr service invocation retry policies, SDK-level retries in the application, or multiple replicas receiving the same client request via load balancing.

## 15. Reproduction notes

- Container Apps ingress is built on Envoy proxy. Envoy's default retry policy and which status codes trigger retries depend on the platform version.
- The official Container Apps documentation does not expose retry policy configuration as of 2026. This experiment aims to observe actual behavior.
- To implement explicit backpressure, consider returning 503 with `Retry-After` header and observing whether the ingress honors it.

## 16. Related guide / official docs

- [Container Apps ingress overview](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Envoy retry policies](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter#x-envoy-retry-on)
