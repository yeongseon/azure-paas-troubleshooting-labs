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

# Long-Polling Connections Dropped by Ingress Idle Timeout

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Long-polling is a pattern where the client holds an HTTP connection open, waiting for the server to push a response when new data is available. When the wait period exceeds the Container Apps ingress idle timeout, the connection is dropped. What status code or error does the client receive, and how does the application need to be designed to handle this gracefully?

## 2. Why this matters

Long-polling is used by real-time applications (notifications, dashboard updates, chat) as a fallback when WebSockets are not available. Unlike streaming responses (which send bytes periodically), a pure long-poll holds the connection silently until the server has data. The idle timeout at the ingress layer is indistinguishable from the server finally having data — both result in the connection ending. If the client doesn't implement proper reconnect logic, it silently loses the connection and stops receiving updates.

## 3. Customer symptom

"Notifications stop arriving after a few minutes" or "Our polling endpoint works locally but stops delivering updates on Azure" or "Clients need to refresh the page to see new updates — the long-poll keeps timing out."

## 4. Hypothesis

- H1: Container Apps ingress terminates long-polling connections that have been idle (no response bytes sent) for longer than the configured idle timeout (default 240 seconds). The client receives a connection close event (TCP FIN or RST).
- H2: A well-designed long-poll server sends an empty response (HTTP 204 or a "no-data" response body) before the idle timeout, allowing the client to immediately reconnect and poll again. The timeout becomes the max wait interval, not a failure condition.
- H3: Server-Sent Events (SSE) is a better pattern than long-polling for Container Apps because SSE is a persistent HTTP stream — as long as the server sends a keep-alive `:` comment periodically, the connection remains open past the idle timeout.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Ingress | External, transport: Auto |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Networking / Platform configuration

**Controlled:**

- ACA ingress configuration examined via ARM API (`api-version=2024-03-01` and `2024-10-02-preview`)
- Standard request/response timing measured via curl
- Transport: Auto (negotiates HTTP/2 or HTTP/1.1 via ALPN)

**Observed:**

- Available ingress configuration fields in ARM model
- Presence or absence of a timeout field in the ingress config
- Actual HTTP response time for fast requests

## 7. Instrumentation

- `az containerapp ingress show` — list ingress properties
- `az rest GET .../containerApps/<app> --query "properties.configuration.ingress | keys(@)"` — enumerate all ingress config fields
- `curl -s -o /dev/null -w "%{http_code} time_total=%{time_total}"` — measure request latency
- `curl -sv --http2` — verify HTTP/2 negotiation

## 8. Procedure

1. Check ARM model for ingress timeout field (GA and preview API versions).
2. Enumerate all available ingress configuration keys.
3. Measure baseline fast-request response time (helloworld app).
4. Compare available ingress settings with documented idle timeout behavior.

## 9. Expected signal

- No `timeout` field exists in the ingress ARM model — timeout is a platform default, not configurable.
- Fast requests complete in <100ms.
- The platform default idle timeout (240s) is not exposed in the ARM config model.

## 10. Results

### ARM ingress config keys — GA API (2024-03-01)

```bash
az rest --method GET \
  --uri ".../containerApps/aca-diag-batch?api-version=2024-03-01" \
  --query "properties.configuration.ingress | keys(@)"

→ [
    "fqdn", "external", "targetPort", "exposedPort", "transport",
    "traffic", "customDomains", "allowInsecure", "ipSecurityRestrictions",
    "corsPolicy", "clientCertificateMode", "stickySessions",
    "additionalPortMappings"
  ]
```

### ARM ingress config keys — Preview API (2024-10-02-preview)

```bash
az rest --method GET \
  --uri ".../containerApps/aca-diag-batch?api-version=2024-10-02-preview" \
  --query "properties.configuration.ingress | keys(@)"

→ [
    "fqdn", "external", "targetPort", "exposedPort", "transport",
    "traffic", "customDomains", "allowInsecure", "ipSecurityRestrictions",
    "corsPolicy", "clientCertificateMode", "stickySessions",
    "additionalPortMappings", "targetPortHttpScheme"
  ]
```

!!! warning "Key finding"
    Neither the GA nor the preview ARM API exposes a timeout configuration field in the ingress model. There is no `idleTimeout`, `requestTimeout`, or `timeout` property — the ingress idle timeout is a fixed platform default (240 seconds) and is not configurable via ARM.

### Fast request baseline

```
curl -s -o /dev/null -w "%{http_code} time_total=%{time_total}" \
  https://aca-diag-batch.agreeablehill-e6bfb5a7.koreacentral.azurecontainerapps.io/

→ 200 time_total=0.057207
→ 200 time_total=0.047799
→ 200 time_total=0.049562
→ 200 time_total=0.047352
→ 200 time_total=0.045034

Average: ~49ms
```

### Ingress full config

```json
{
  "external": true,
  "targetPort": 80,
  "transport": "Auto",
  "traffic": [{"revisionName": "aca-diag-batch--0000004", "weight": 100}],
  "allowInsecure": false
}
```

## 11. Interpretation

- **Measured**: No timeout field exists in the Container Apps ingress ARM model at either the GA or preview API version. H1 (240s idle timeout) is **Not Proven by direct measurement** — the timeout value cannot be directly observed because no long-polling endpoint exists in the test app (helloworld returns immediately). The 240s figure is from platform documentation.
- **Observed**: The ARM ingress model contains 13–14 fields across API versions. None of them are timeout-related. The ingress idle timeout is a platform behavior, not a customer-configurable parameter. **Observed**.
- **Measured**: Fast requests complete in ~47–57ms, confirming the ingress layer adds minimal overhead for standard request/response patterns. **Measured**.
- **Inferred**: Because the idle timeout is not configurable in the ARM model, customers cannot extend it beyond 240 seconds. Applications that need connections longer than 240 seconds (long-polling, SSE, WebSocket) must implement application-layer keepalive to prevent the ingress from closing idle connections.

## 12. What this proves

- The Container Apps ingress ARM model has no configurable timeout field — the idle timeout is a fixed platform default. **Observed**.
- Fast HTTP requests on ACA ingress complete in ~47–57ms. **Measured**.

## 13. What this does NOT prove

- The 240-second idle timeout value was not directly measured — no long-polling test application was available in this environment. The 240s value is from platform documentation.
- Whether HTTP/2 connections are treated differently from HTTP/1.1 for idle timeout calculation.
- Whether the idle timeout applies differently to WebSocket connections vs. HTTP/2 streaming vs. HTTP/1.1 long-polling.

## 14. Support takeaway

When a customer reports that long-polling connections drop after a few minutes on Container Apps:

1. The ingress idle timeout is **not configurable** — there is no ARM property to extend it. The platform default is 240 seconds.
2. A connection with no bytes sent in either direction for 240 seconds will be closed by the ingress. The client receives a connection close event (TCP FIN).
3. To keep long-polling connections alive beyond 240 seconds, the server must send data before the timeout. Options:
   - **Server-Sent Events (SSE)**: send a `: keep-alive\n\n` comment line every 30–60 seconds
   - **Long-poll graceful design**: server returns a `204 No Content` response before the timeout; client immediately re-establishes the connection
   - **WebSocket**: send a ping frame every 30–60 seconds
4. The idle timeout affects idle connections — a connection actively sending/receiving data will not be terminated.

## 15. Reproduction notes

```bash
ACA_URL="https://<app>.<env-domain>.<region>.azurecontainerapps.io"

# Check ingress ARM model for timeout fields
az rest --method GET \
  --uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/containerApps/<app>?api-version=2024-03-01" \
  --query "properties.configuration.ingress | keys(@)"
# Expected: no timeout/idleTimeout field

# Test fast request timing
for i in $(seq 1 5); do
  curl -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" "$ACA_URL/"
done

# For long-polling test (requires custom app with slow endpoint):
# curl --max-time 300 "$ACA_URL/long-poll?wait=300"
# Expected: connection dropped at ~240s with empty reply or connection reset

# SSE keepalive pattern (Flask):
# @app.route('/sse')
# def sse_stream():
#     def generate():
#         while True:
#             yield ": keep-alive\n\n"  # SSE comment line
#             time.sleep(30)
#     return Response(generate(), mimetype='text/event-stream')
```

## 16. Related guide / official docs

- [Container Apps ingress overview](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [WebSocket support in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/websockets)
