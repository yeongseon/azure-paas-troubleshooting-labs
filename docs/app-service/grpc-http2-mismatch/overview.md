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

# gRPC and HTTP/2 End-to-End Mismatch

!!! info "Status: Planned"

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
| Service | Azure App Service (and Azure Container Apps for comparison) |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 (grpcio) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Protocol

**Controlled:**

- Python gRPC server (unary and server-streaming RPC)
- Python gRPC client connecting from an external VM
- App Service with HTTP/2 enabled in site settings

**Observed:**

- gRPC call success/failure for unary vs. streaming RPC
- HTTP protocol version used on the backend hop (visible via request headers in the app)
- Comparison with direct server connection (no App Service proxy)

**Scenarios:**

- S1: Direct connection to gRPC server (no App Service) → baseline success
- S2: Via App Service, unary RPC → observe failure mode
- S3: Via App Service, server-streaming RPC → observe failure mode
- S4: gRPC-Web client via App Service → observe if it works
- S5: Same gRPC server on Container Apps with HTTP2 ingress → verify success

## 7. Instrumentation

- gRPC client error codes and messages
- `SERVER_SOFTWARE` header or `X-Forwarded-Proto` to detect proxy behavior
- tcpdump on the server to observe incoming HTTP version
- Container Apps access logs for HTTP/2 traffic

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy a Python gRPC server (unary `SayHello` + server-streaming `StreamHellos`) on App Service.
2. S1: Connect directly to the app's internal address from Kudu SSH; verify gRPC works locally.
3. S2-S3: Connect from an external VM using `grpc.insecure_channel` pointing to the App Service hostname; observe errors.
4. S4: Use `grpc-web` Python client or `grpcurl --use-grpc-web`; test if the call succeeds.
5. S5: Deploy same server on Container Apps with `transport: http2`; connect from same client; verify success.

## 9. Expected signal

- S1: All RPC types succeed when calling the server directly.
- S2-S3: gRPC client reports `StatusCode.INTERNAL` or `StatusCode.UNAVAILABLE`; server receives HTTP/1.1 request (observe via headers).
- S4: gRPC-Web unary call succeeds; streaming may succeed or partially succeed depending on gRPC-Web implementation.
- S5: All RPC types succeed on Container Apps.

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

- App Service HTTP/2 setting (**Configuration > General settings > HTTP version**) controls the client-to-frontend connection only. The frontend-to-worker hop is always HTTP/1.1.
- gRPC requires end-to-end HTTP/2. App Service cannot provide this. Use Azure Container Apps (with `transport: http2` on the ingress) or a VM/AKS for gRPC services.
- gRPC-Web is a workaround for browser clients but not for native gRPC clients.

## 16. Related guide / official docs

- [HTTP/2 support in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#http20-support)
- [Container Apps - gRPC ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [gRPC on .NET in App Service](https://learn.microsoft.com/en-us/aspnet/core/grpc/aspnetcore)
