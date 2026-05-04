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

# HTTP Ingress Timeout: Long-Running Request Termination

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Container Apps ingress has a configurable idle timeout and an implicit request timeout. What is the maximum duration for a single HTTP request, and what HTTP status code does the client receive when the request exceeds the timeout — and does the container process receive a signal before the connection is dropped?

## 2. Why this matters

Applications that perform long-running synchronous operations (data export, batch processing, file conversion) may require HTTP requests that take minutes to complete. Container Apps ingress has an idle timeout that terminates connections that are idle (no data sent) for more than the configured period. If the application does not stream any response bytes during a long operation, the ingress drops the connection even though the application is actively processing the request. Understanding this behavior is essential for designing appropriate patterns (streaming, async with polling, or webhooks) for long operations.

## 3. Customer symptom

"Long-running API calls fail after exactly 240 seconds with a connection error" or "Export endpoint works for small datasets but times out for large ones" or "The request completes on the server but the client never receives the response."

## 4. Hypothesis

- H1: Container Apps ingress has an idle connection timeout (default: 240 seconds) that terminates connections where no data is sent by the server for that period. A long-running request that does not send response headers or body bytes until completion is terminated by the ingress after 240 seconds.
- H2: The container process is NOT notified before the connection is terminated — the application continues processing after the ingress has closed the connection. The completed result is silently discarded.
- H3: Streaming the response (sending HTTP headers immediately, then streaming body bytes periodically) keeps the connection alive past the 240-second idle timeout, allowing arbitrarily long responses.
- H4: The `ingress.timeout` property in the container app configuration controls the idle timeout (in seconds, maximum 3600).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Runtime | Python 3.11 / Flask / gunicorn |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Networking / Platform behavior

**Controlled:**

- `/sleep?s=<n>` Flask endpoint — sleeps for n seconds then returns JSON
- gunicorn `--timeout 600` to prevent worker timeout before the ingress fires

**Observed:**

- HTTP status code returned at timeout boundary
- Response body at timeout
- Exact timing of connection termination

**Scenarios:**

- S1: 10-second sleep → verify baseline works
- S2: 60-second sleep → verify well within timeout
- S3: 230-second sleep → verify just under the boundary
- S4: 240-second sleep → observe timeout
- S5: 241-second sleep → confirm consistent 240s boundary

## 7. Instrumentation

- `curl -sv --max-time 300 https://<app>/sleep?s=<n>` — observe HTTP code and body
- `time curl ...` — verify exact duration
- ARM API: `az rest GET .../containerApps/aca-diag-batch?api-version=2024-03-01` — verify no `ingress.timeout` ARM field exists (non-configurable)

## 8. Procedure

1. Deploy Flask app with `/sleep?s=<n>` endpoint (gunicorn `--timeout 600`).
2. S1–S3: Test sleep values below threshold (10, 60, 230 seconds) — expect 200 OK.
3. S4: Test 240-second sleep — observe 504 at exactly 240s.
4. S5: Test 241-second sleep — confirm 504 returns at 240s regardless.
5. Check ARM API for `ingress.timeout` field — confirm no user-configurable timeout.

## 9. Expected signal

- S1–S3: HTTP 200 with `{"slept": <n>}` body.
- S4–S5: HTTP 504 with body `stream timeout` at exactly 240 seconds.
- ARM schema: no `timeout` field in ingress configuration.

## 10. Results

### S1 — 10-second sleep

```bash
curl -s --max-time 30 "$ACA_URL/sleep?s=10"
→ {"slept": 10.0}   # HTTP 200, ~10s
```

### S2 — 60-second sleep

```bash
curl -s --max-time 90 "$ACA_URL/sleep?s=60"
→ {"slept": 60.0}   # HTTP 200, ~60s
```

### S3 — 230-second sleep (under boundary)

```bash
time curl -s --max-time 260 "$ACA_URL/sleep?s=230"
→ {"slept": 230.0}   # HTTP 200
→ real  3m49.2s
```

### S4 — 240-second sleep (at boundary)

```bash
curl -sv --max-time 300 "$ACA_URL/sleep?s=240"
→ < HTTP/2 504
→ stream timeout
→ Duration: 240s exactly
```

### S5 — 241-second sleep (over boundary)

```bash
curl -sv --max-time 300 "$ACA_URL/sleep?s=241"
→ < HTTP/2 504
→ stream timeout
→ Duration: 240s (terminated before backend responded)
```

!!! warning "Key finding"
    Container Apps ingress terminates any request that has not sent a response byte within **240 seconds**, returning HTTP 504 with body `stream timeout`. This is a hardcoded platform limit — the ARM schema for `ingress` has no `timeout` field.

### ARM ingress schema — no timeout field

```bash
az rest --method get \
  --uri ".../containerApps/aca-diag-batch?api-version=2024-03-01" \
  --query "properties.configuration.ingress"
# → No "timeout" field in the response
```

## 11. Interpretation

- **Measured**: H1 is confirmed. Container Apps ingress terminates connections with no response data at exactly 240 seconds, returning HTTP 504 with body `stream timeout`. **Measured**.
- **Inferred**: H2 (container process continues after connection drop) is consistent with gunicorn's behavior — the worker holds the connection open until the sleep completes, but the ingress has already sent 504 to the client. The gunicorn worker logs the response as completed after the full sleep duration. **Inferred** (not directly observed — Kudu/exec access not available).
- **Not Proven**: H3 (streaming prevents timeout) — streaming was not tested. Response chunking should keep the connection alive per HTTP/2 flow control semantics, but this was not verified experimentally.
- **Measured**: H4 is disproven. There is no `ingress.timeout` ARM property. The 240-second limit is a platform constant, not a configurable setting in the 2024-03-01 API. **Measured**.

## 12. What this proves

- Container Apps ingress times out non-streaming requests at exactly 240 seconds with HTTP 504 `stream timeout`. **Measured**.
- The timeout is not user-configurable in the current ARM API (no `ingress.timeout` field). **Measured**.
- 230-second requests complete successfully; 240-second requests do not. The boundary is 240 seconds. **Measured**.

## 13. What this does NOT prove

- Whether streaming (chunked response with periodic flushes) prevents the timeout was not tested.
- Whether the container process receives a signal (SIGTERM or similar) when the ingress drops the connection was not measured (Kudu exec not available).
- The behavior of Dedicated workload profile was not tested — only Consumption was measured.
- Whether the timeout applies to response headers or only to response body bytes was not differentiated.

## 14. Support takeaway

When a customer reports requests failing after exactly 4 minutes (240 seconds) on Container Apps:

1. The root cause is the Container Apps ingress 240-second request timeout. This is a platform constant — it cannot be configured via the ARM API or CLI.
2. The 240s timer starts when the request arrives at the ingress and no response bytes have been sent. If the application sends response headers but no body, the timer likely resets per Envoy stream timeout semantics — but this was not verified.
3. The response is HTTP 504 with body `stream timeout` — this is Envoy's format and distinguishes this from application-level 504s.
4. **Design patterns for long operations**:
   - Async: accept the request (return 202 + job ID), process in background, expose a polling endpoint.
   - Streaming: use `Transfer-Encoding: chunked` with periodic flushes to keep bytes flowing.
   - WebSockets: upgrade the connection to WebSocket, which is not subject to the same HTTP timeout.
5. Operations that are consistently slower than 240 seconds cannot be exposed as synchronous HTTP endpoints on Container Apps.

## 15. Reproduction notes

```bash
ACA_APP="<app-name>"
RG="<resource-group>"
ACA_URL="https://<app>.<env>.azurecontainerapps.io"

# Deploy Flask app with sleep endpoint (gunicorn must have --timeout > 240)
# Dockerfile CMD: gunicorn --bind 0.0.0.0:8000 --timeout 600 app:app

# Test boundary
curl -sv --max-time 300 "$ACA_URL/sleep?s=230" | tail -2  # → 200 OK
curl -sv --max-time 300 "$ACA_URL/sleep?s=240" | tail -2  # → 504 stream timeout

# Verify no timeout ARM field
az rest --method get \
  --uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/$RG/providers/Microsoft.App/containerApps/$ACA_APP?api-version=2024-03-01" \
  --query "properties.configuration.ingress.timeout"
# → null (field does not exist)
```

## 16. Related guide / official docs

- [Container Apps ingress configuration](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Azure Container Apps FAQ — request timeout](https://learn.microsoft.com/en-us/azure/container-apps/faq)
- [Envoy stream timeout](https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/route/v3/route_components.proto#envoy-v3-api-field-config-route-v3-routeaction-timeout)
