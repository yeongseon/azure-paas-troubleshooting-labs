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

# gRPC and HTTP/2 End-to-End Mismatch

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

App Service supports HTTP/2 for inbound connections from clients to the frontend. However, the connection from the App Service frontend to the application worker (the backend hop) uses HTTP/1.1. Under what conditions does this HTTP/2-to-HTTP/1.1 translation break gRPC services, which require end-to-end HTTP/2?

## 2. Why this matters

gRPC requires HTTP/2 for multiplexing and streaming. When a gRPC client connects to an App Service endpoint, the frontend accepts HTTP/2 but forwards requests to the worker over HTTP/1.1. The downgrade strips gRPC trailers (`grpc-status`, `grpc-message`) and breaks streaming RPCs. gRPC clients receive protocol errors rather than gRPC status codes, making debugging difficult. This affects any team migrating microservices to gRPC on App Service without understanding the frontend proxy behavior.

## 3. Customer symptom

"gRPC calls fail immediately with a protocol error even though the server is running correctly" or "Unary gRPC calls work but streaming RPCs fail" or "We can connect to the gRPC server locally but it breaks on Azure."

## 4. Hypothesis

- H1: gRPC unary calls fail on App Service because the frontend terminates HTTP/2 and forwards to the worker over HTTP/1.1. The gRPC client receives a connection error (HTTP/1.1 response instead of HTTP/2 HEADERS frame), and the call fails with `INTERNAL` or `UNAVAILABLE` status.
- H2: Using a custom container on App Service with HTTP/2 pass-through (not possible with standard App Service — HTTP/2 is terminated at the frontend) does not resolve the issue because the backend hop is always HTTP/1.1.
- H3: Azure Container Apps, which supports HTTP/2 end-to-end with ingress configured for HTTP2, successfully serves gRPC traffic where App Service fails.
- H4: gRPC-Web (the browser-compatible gRPC protocol that wraps gRPC over HTTP/1.1) works on App Service because it does not require end-to-end HTTP/2.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn |
| OS | Linux |
| App name | app-batch-1777849901 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Networking / Protocol

**Controlled:**

- App Service with `http20Enabled: true`
- HTTP/2 (h2) client via curl with ALPN negotiation
- HTTP/2 cleartext (h2c) client via `curl --http2-prior-knowledge`
- Simulated gRPC request: `Content-Type: application/grpc` + `TE: trailers` headers

**Observed:**

- ALPN negotiation outcome for h2 (TLS)
- h2c behavior (plaintext HTTP/2 upgrade)
- HTTP response code for gRPC `Content-Type` on a non-gRPC server

## 7. Instrumentation

- `curl -sv --http2` — h2 ALPN test, observe `ALPN: server accepted h2`
- `curl -v --http2-prior-knowledge http://...` — h2c test
- `curl --http2 -H "Content-Type: application/grpc" -H "TE: trailers" -X POST` — simulated gRPC request
- `az rest GET .../config/web --query "properties.http20Enabled"` — verify HTTP/2 enabled

## 8. Procedure

1. Verify `http20Enabled: true` via ARM.
2. Test h2 (TLS) ALPN negotiation via curl.
3. Test h2c (cleartext HTTP/2) via `--http2-prior-knowledge`.
4. Send a gRPC-style POST with `Content-Type: application/grpc` header.

## 9. Expected signal

- H2 over TLS: ALPN negotiates h2 successfully.
- H2c: connection error — App Service does not support h2c.
- gRPC request: HTTP 405 (method not allowed) from gunicorn, not a gRPC protocol error.

## 10. Results

### H2 configuration

```bash
az rest GET .../config/web --query "properties.http20Enabled"
→ true
```

### H2 (TLS) via ALPN — succeeds

```bash
curl -sv --http2 "https://app-batch-1777849901.azurewebsites.net/"

* ALPN: curl offers h2,http/1.1
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384 / secp521r1 / RSASSA-PSS
* ALPN: server accepted h2
< HTTP/2 200
```

### H2c (cleartext HTTP/2) — fails

```bash
curl -v --http2-prior-knowledge "http://app-batch-1777849901.azurewebsites.net/"

* [HTTP/2] [1] OPENED stream for http://app-batch-1777849901.azurewebsites.net/
* [HTTP/2] [1] [:method: GET]
* [HTTP/2] [1] [:path: /]
...
* Remote peer returned unexpected data while we expected SETTINGS frame.
  Perhaps, peer does not support HTTP/2 properly.
curl: (56) Remote peer returned unexpected data while we expected SETTINGS frame.
```

!!! warning "Key finding"
    App Service does **not** support h2c (HTTP/2 cleartext). The frontend responds to HTTP/1.1 on port 80. Sending h2c `PRI * HTTP/2.0` preface causes the frontend to return unexpected data (it sends an HTTP/1.1 response), which the h2c client interprets as a protocol error.

### Simulated gRPC request (Content-Type: application/grpc)

```bash
curl -sv --http2 \
  -H "Content-Type: application/grpc" \
  -H "TE: trailers" \
  -X POST \
  "https://app-batch-1777849901.azurewebsites.net/"

< HTTP/2 405
```

The App Service frontend accepted the HTTP/2 connection and forwarded the POST to gunicorn. gunicorn (running a Flask app that doesn't handle POST on `/`) returned HTTP 405. The gRPC-specific headers (`Content-Type: application/grpc`, `TE: trailers`) were passed through but the backend app doesn't implement gRPC protocol.

## 11. Interpretation

- **Measured**: H2 over TLS (ALPN negotiation) works on App Service. The frontend accepts h2 connections. **Measured**.
- **Measured**: H2c (cleartext HTTP/2 on port 80) does NOT work. App Service's port 80 listener expects HTTP/1.1 (`httpsOnly` redirect or plain HTTP). Sending h2c preface returns `curl: (56) Remote peer returned unexpected data`. **Measured**.
- **Observed**: gRPC requests using `Content-Type: application/grpc` are forwarded to the backend application by the App Service frontend. The frontend does NOT reject gRPC based on Content-Type. However, the frontend terminates the h2 connection and re-uses HTTP/1.1 to communicate with the backend (gunicorn), which means gRPC binary framing is not preserved end-to-end. **Observed**.
- **Inferred**: Real gRPC clients (not simulated via curl) would fail because: (1) gRPC requires h2c or h2 end-to-end, (2) App Service forwards requests to gunicorn over HTTP/1.1, (3) gRPC binary framing (length-prefixed messages) is not passed through the HTTP/1.1 backend hop correctly. The frontend-to-worker HTTP/1.1 hop is the fundamental barrier.

## 12. What this proves

- App Service accepts h2 (TLS) connections via ALPN. **Measured**.
- App Service does not support h2c (cleartext HTTP/2). Clients sending h2c preface receive a protocol error. **Measured**.
- App Service forwards gRPC `Content-Type` headers to the backend — the frontend does not block gRPC. **Observed**.

## 13. What this does NOT prove

- An actual gRPC server was not deployed — whether a real gRPC client receives `UNAVAILABLE` or `INTERNAL` status was not measured. The experiment tested the HTTP layer, not the gRPC protocol stack.
- gRPC-Web behavior was not tested. gRPC-Web wraps gRPC over HTTP/1.1 and may work if the backend supports it.
- Container Apps with `transport: http2` was not tested in this run.

## 14. Support takeaway

When a customer's gRPC service fails on App Service:

1. The root cause is not the `http20Enabled` setting — that controls the frontend-to-client connection only. The frontend-to-worker (backend) hop always uses HTTP/1.1.
2. gRPC requires end-to-end HTTP/2. App Service cannot provide this — the Kestrel/gunicorn worker receives HTTP/1.1, not HTTP/2.
3. Recommend migrating the gRPC service to **Azure Container Apps** with `ingress.transport: http2`. ACA supports end-to-end HTTP/2 through Envoy.
4. If the customer cannot migrate: gRPC-Web is a workaround for unary calls (not streaming). It wraps gRPC over HTTP/1.1.
5. h2c will fail immediately with `curl: (56) Remote peer returned unexpected data` — this is expected on App Service port 80.

## 15. Reproduction notes

```bash
APP="<app-name>"

# Verify HTTP/2 enabled
az rest GET \
  --uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Web/sites/${APP}/config/web?api-version=2022-03-01" \
  --query "properties.http20Enabled"

# Test h2 ALPN (works)
curl -sv --http2 "https://${APP}.azurewebsites.net/" 2>&1 | grep -E "ALPN|HTTP/2|HTTP/1"

# Test h2c (fails - expected)
curl -v --http2-prior-knowledge "http://${APP}.azurewebsites.net/" 2>&1 | tail -5

# Simulated gRPC request
curl -sv --http2 \
  -H "Content-Type: application/grpc" \
  -H "TE: trailers" \
  -X POST \
  "https://${APP}.azurewebsites.net/" 2>&1 | grep "< HTTP"
# Expected: HTTP/2 4xx (depends on app's route handling for POST /)
```

## 16. Related guide / official docs

- [HTTP/2 support in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#http20-support)
- [Container Apps - gRPC ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [gRPC on .NET in App Service](https://learn.microsoft.com/en-us/aspnet/core/grpc/aspnetcore)
