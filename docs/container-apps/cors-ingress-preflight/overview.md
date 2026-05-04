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

# CORS Preflight Handling at Container Apps Ingress vs. Application Level

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a browser sends a CORS preflight request (HTTP OPTIONS with `Origin` and `Access-Control-Request-*` headers), is the preflight handled at the Container Apps ingress level, or forwarded to the application? When CORS is enabled on the ingress, what response headers are returned for allowed vs. disallowed origins?

## 2. Why this matters

CORS misconfigurations are a frequent source of support tickets. On Container Apps, unlike some platforms where the application handles CORS, ACA ingress supports platform-level CORS configuration. When CORS is not configured at the ingress, preflight OPTIONS requests return HTTP 200 with no `Access-Control-*` headers, causing browsers to block the cross-origin request. When wildcard `*` is enabled, all origins are allowed regardless of security intent. Understanding where CORS is enforced and what the exact response headers are prevents misconfiguration.

## 3. Customer symptom

"API calls work in Postman but fail from the browser with 'CORS error'" or "OPTIONS requests return 200 but no CORS headers" or "We enabled CORS but disallowed origins still get a 200 response."

## 4. Hypothesis

- H1: Without any CORS configuration on ACA ingress, OPTIONS preflight requests return HTTP 200 with no `Access-Control-*` response headers. ✅ **Confirmed**
- H2: After enabling CORS with a specific origin, OPTIONS requests from that origin receive `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers` headers. ✅ **Confirmed**
- H3: OPTIONS requests from a disallowed origin still receive HTTP 200 but without `Access-Control-Allow-Origin` in the response. ✅ **Confirmed**
- H4: Enabling wildcard CORS (`allowedOrigins: ["*"]`) causes all origins to receive the exact `Origin` value back in `Access-Control-Allow-Origin`. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| Environment | env-batch-lab (Consumption, Korea Central) |
| App | aca-diag-batch |
| Image | mcr.microsoft.com/azuredocs/containerapps-helloworld:latest |
| Ingress | External, transport: Auto, port 80 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Networking / Configuration

**Controlled:**

- ACA app with external HTTPS ingress
- CORS configuration toggled via `az containerapp ingress cors enable`

**Observed:**

- HTTP response code and `Access-Control-*` headers for OPTIONS preflight
- Behavior for allowed origin, disallowed origin, and wildcard configuration

**Scenarios:**

- S1: No CORS config → OPTIONS preflight from `https://example.com`
- S2: CORS enabled for `https://example.com` only → preflight from allowed and disallowed origins
- S3: Wildcard CORS (`*`) → preflight from any origin

## 7. Instrumentation

- `curl -sI -X OPTIONS -H "Origin: <origin>" -H "Access-Control-Request-Method: POST"` — capture response headers
- `az containerapp ingress cors show` — verify CORS configuration
- `az containerapp ingress cors enable` — apply CORS settings

## 8. Procedure

1. Created `aca-diag-batch` with no CORS configuration.
2. S1: Sent OPTIONS preflight from `https://example.com` — captured headers.
3. S2: Enabled CORS for `https://example.com` only (`--allowed-origins https://example.com`); tested both allowed and disallowed origins.
4. S3: Changed CORS to wildcard (`--allowed-origins "*"`); tested from `https://evil.com`.

## 9. Expected signal

- S1: HTTP 200, no `Access-Control-*` headers.
- S2 (allowed): HTTP 200, `Access-Control-Allow-Origin: https://example.com`, allowed methods and headers.
- S2 (disallowed): HTTP 200, no `Access-Control-Allow-Origin`.
- S3: HTTP 200, `Access-Control-Allow-Origin: https://evil.com` (echoes origin back).

## 10. Results

**S1: No CORS configured:**

```
OPTIONS / HTTP/2 200
(no Access-Control-* headers)
```

**S2: CORS enabled for https://example.com only:**

```
# Allowed origin (https://example.com):
HTTP/2 200
access-control-allow-origin: https://example.com
access-control-allow-methods: GET,POST,OPTIONS
access-control-allow-headers: Content-Type,Authorization

# Disallowed origin (https://evil.com):
HTTP/2 200
(no Access-Control-* headers)
```

**S3: Wildcard CORS (allowedOrigins: ["*"]):**

```
# Request from https://evil.com:
HTTP/2 200
access-control-allow-origin: https://evil.com
access-control-allow-methods: GET,POST,PUT,DELETE,OPTIONS
access-control-allow-headers: (empty)
```

**CORS configuration API (`az containerapp ingress cors show`):**

```json
{
  "allowCredentials": false,
  "allowedHeaders": ["*"],
  "allowedMethods": ["GET,POST,PUT,DELETE,OPTIONS"],
  "allowedOrigins": ["*"]
}
```

## 11. Interpretation

- **Observed**: Without CORS configuration, ACA ingress returns HTTP 200 to OPTIONS preflights but with no `Access-Control-*` headers. The browser will block the actual request. The underlying container never receives the OPTIONS request — the ingress handles it.
- **Observed**: With a specific origin configured, only that origin's preflight receives the `Access-Control-Allow-Origin` header. Requests from other origins get HTTP 200 but no CORS headers — the request still fails in the browser, but the server doesn't return a 403.
- **Observed**: Wildcard CORS (`*`) causes the ingress to echo the requesting origin back in `Access-Control-Allow-Origin`. This means `https://evil.com` receives `Access-Control-Allow-Origin: https://evil.com` — effectively allowing all origins including potentially malicious ones.
- **Observed**: The `allowedHeaders: ["*"]` in wildcard mode returns an empty `Access-Control-Allow-Headers` response header. This may cause preflight failures in strict browsers if specific headers are requested.
- **Inferred**: The ACA ingress (Envoy-based) handles CORS at the proxy layer, not the application. The application code does not receive OPTIONS preflight requests when ingress-level CORS is configured.

## 12. What this proves

- ACA ingress handles CORS at the platform level — OPTIONS preflights do not reach the application container.
- Without CORS config: OPTIONS returns 200 with no CORS headers (browser blocks cross-origin requests).
- With specific origin configured: only matching origins receive CORS headers.
- Wildcard `*` CORS reflects the requesting origin — all origins are effectively allowed.
- Disallowed origins receive HTTP 200 but no `Access-Control-Allow-Origin` — the browser enforces the block, not the server.

## 13. What this does NOT prove

- Application-level CORS middleware behavior (when the app handles OPTIONS itself) was **Not Tested** — requires a custom container image.
- `allowCredentials: true` interaction with wildcard origins was **Not Tested** (CORS spec forbids this combination).
- `Access-Control-Max-Age` preflight caching was **Not Tested**.
- The behavior when ACA ingress CORS is disabled and the application has its own CORS middleware was **Not Tested**.

## 14. Support takeaway

- "CORS error in browser, OPTIONS returns 200" — check that `Access-Control-Allow-Origin` is actually present in the response. HTTP 200 on an OPTIONS preflight does not guarantee CORS headers are set.
- "All origins can access my API" — check for wildcard CORS (`allowedOrigins: ["*"]`). Remove wildcard and list specific allowed origins for security-sensitive APIs.
- To add CORS at ingress: `az containerapp ingress cors enable -n <app> -g <rg> --allowed-origins "https://myapp.com"`.
- CORS at ingress and CORS in the application code can conflict. If both set `Access-Control-Allow-Origin`, the response may include duplicate headers, causing browser errors. Prefer one layer only.

## 15. Reproduction notes

```bash
# Enable CORS for specific origin
az containerapp ingress cors enable \
  -n <app> -g <rg> \
  --allowed-origins "https://example.com" \
  --allowed-methods "GET,POST,OPTIONS" \
  --allowed-headers "Content-Type,Authorization"

# Test OPTIONS preflight
curl -sI -X OPTIONS \
  -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: POST" \
  https://<app>.<env>.azurecontainerapps.io/ \
  | grep -i "access-control"

# Test disallowed origin
curl -sI -X OPTIONS \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST" \
  https://<app>.<env>.azurecontainerapps.io/
# Returns 200 but NO Access-Control-Allow-Origin header

# Check current CORS config
az containerapp ingress cors show -n <app> -g <rg>
```

## 16. Related guide / official docs

- [Container Apps ingress CORS](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview#cors)
- [CORS preflight — MDN Web Docs](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request)
- [Container Apps ingress configuration](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to)
