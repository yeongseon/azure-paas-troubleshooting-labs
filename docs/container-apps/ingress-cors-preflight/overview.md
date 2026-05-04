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

# Ingress CORS Preflight Handling

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

Does Azure Container Apps Envoy ingress handle CORS preflight OPTIONS requests at the ingress layer, or do they pass through to the application? If the application doesn't handle OPTIONS, do preflight requests fail with 404 or 405?

## 2. Why this matters

CORS (Cross-Origin Resource Sharing) is a common source of support cases for Container Apps. Browser-based applications making cross-origin requests require CORS headers. The confusion arises from two questions:
1. Who is responsible for CORS — the app, Envoy ingress, or both?
2. What happens to OPTIONS preflight requests if the app doesn't explicitly handle them?

Customers frequently assume Envoy handles CORS automatically, or that CORS headers on the response are sufficient without handling OPTIONS. The result is preflight requests failing with 404 or 405, which appears as a CORS error in the browser.

## 3. Customer symptom

- "CORS is configured correctly in the app but the browser still complains."
- "The API works in Postman but fails in the browser with a CORS error."
- "OPTIONS requests return 404 or 405."
- "I added `Access-Control-Allow-Origin: *` to the response but preflight still fails."

## 4. Hypothesis

**H1 — Envoy does not handle CORS**: Container Apps Envoy ingress does not add CORS headers or handle OPTIONS preflight requests automatically. CORS is entirely the application's responsibility.

**H2 — OPTIONS returns 404 if not handled by app**: If the application does not implement an OPTIONS handler, an OPTIONS preflight request will return 404 or 405 from the application, causing the browser to block the actual request.

**H3 — `Access-Control-Allow-Origin` header alone is insufficient**: A response with `Access-Control-Allow-Origin: *` on the actual request (GET/POST) does not help if the OPTIONS preflight fails first. Both the preflight and the actual request need CORS headers.

**H4 — Envoy CORS config is not surfaced**: Unlike Azure API Management, Container Apps does not expose Envoy CORS configuration through the Container Apps API. There is no built-in CORS toggle.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask) |
| Ingress | External |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Network + CORS

**Controlled:**

- Application CORS handling: none, OPTIONS only, full CORS headers
- Request type: simple GET, cross-origin GET, cross-origin POST with custom header
- Browser vs. curl vs. Python requests client

**Observed:**

- HTTP status code for OPTIONS requests
- CORS headers present on response
- Browser console error messages
- Envoy access log for OPTIONS requests

## 7. Instrumentation

- Flask app with three configurations: (a) no CORS, (b) OPTIONS handler only, (c) full CORS via `flask-cors`
- Browser test page (HTML file) making cross-origin fetch requests
- curl for preflight: `curl -X OPTIONS -H "Origin: http://evil.com" -H "Access-Control-Request-Method: POST" https://<app>/api`

**CORS test request:**

```bash
# Preflight test
curl -sv -X OPTIONS \
  -H "Origin: https://test.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" \
  https://<containerapp>/api/data
```

## 8. Procedure

### 8.1 Scenarios

**S1 — No CORS handling**: Flask app with GET endpoint, no CORS headers, no OPTIONS handler. Send browser cross-origin request. Document error in browser console and OPTIONS response code.

**S2 — OPTIONS handler only**: Add `@app.route('/api', methods=['OPTIONS'])` returning 200 with `Access-Control-Allow-Origin: *`. Test preflight success but document that actual request still fails without CORS headers on the response.

**S3 — Full CORS via flask-cors**: Use `CORS(app)` from `flask-cors`. Verify both OPTIONS preflight and actual request succeed from browser.

**S4 — Envoy CORS headers**: Check whether Envoy adds any CORS headers of its own. Inspect raw HTTP responses for Envoy-injected headers.

## 9. Expected signal

- **S1**: OPTIONS returns 405 (Method Not Allowed). Browser blocks actual request with CORS error.
- **S2**: OPTIONS returns 200 with CORS headers. Browser sends actual GET. Response lacks CORS headers → browser blocks.
- **S3**: OPTIONS preflight 200 + CORS headers. Actual request 200 + CORS headers. Browser succeeds.
- **S4**: Envoy adds no CORS headers of its own — no `Access-Control-*` headers from the platform layer.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Different browsers may have different CORS enforcement behavior; test with Chrome (strictest enforcement).
- Browser DevTools may show the error differently than what's in the network tab.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Envoy does not auto-handle CORS | **Strongly Suggested** (no documented CORS feature in ACA) |
| OPTIONS without handler returns 405 | **Inferred** |
| Preflight failure blocks actual request | **Observed** (standard browser behavior) |

## 14. Related experiments

- [Ingress SNI / Host Header](../ingress-sni-host-header/overview.md) — Envoy ingress routing behavior
- [HTTP Ingress Timeout](../liveness-probe-failures/overview.md) — Envoy timeout configuration

## 15. References

- [CORS specification (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [Flask-CORS documentation](https://flask-cors.readthedocs.io/)

## 16. Support takeaway

For CORS issues in Container Apps:

1. Container Apps Envoy ingress does NOT handle CORS — the application must implement it. There is no built-in CORS configuration in the Container Apps portal or CLI.
2. The most common mistake: adding `Access-Control-Allow-Origin` to GET/POST responses but not implementing an OPTIONS handler. OPTIONS preflight fails → browser blocks the actual request.
3. Use `flask-cors` (Python), `cors` npm package (Node.js), or `[EnableCors]` attribute (.NET) to handle both preflight and response headers in one library call.
4. Diagnose by testing OPTIONS preflight with curl directly — if it returns 404 or 405, the app is not handling OPTIONS. This is always an app-level fix, not a platform configuration.
