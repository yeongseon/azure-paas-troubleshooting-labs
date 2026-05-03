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

# gRPC End-to-End on Container Apps: HTTP/2 Transport and TLS Requirements

!!! info "Status: Planned"

## 1. Question

Container Apps ingress supports HTTP/2 with gRPC. When a gRPC server is deployed and the ingress is configured with `transport: http2`, does gRPC work correctly for both unary and streaming calls? What breaks when the ingress is set to `http` (HTTP/1.1) or when the client does not negotiate HTTP/2, and how does TLS interact with gRPC over Container Apps ingress?

## 2. Why this matters

gRPC requires HTTP/2. Container Apps ingress terminates TLS and proxies traffic; the upstream connection between the Envoy proxy and the container can be HTTP/2 or HTTP/1.1 depending on the `transport` setting. When the ingress transport is not set to `http2`, gRPC calls fail with protocol negotiation errors or RST_STREAM frames. Additionally, gRPC clients that use plaintext (`grpc.insecure_channel`) cannot connect to a Container Apps ingress that terminates TLS — the client must use TLS (`grpc.secure_channel` with default credentials) for external gRPC calls.

## 3. Customer symptom

"gRPC calls fail with PROTOCOL_ERROR or GOAWAY frames" or "gRPC streaming works for unary but server streaming drops after a few messages" or "The gRPC client connects but immediately gets UNAVAILABLE" or "Works locally with plaintext but fails on Container Apps."

## 4. Hypothesis

- H1: Setting `transport: http` (HTTP/1.1) on Container Apps ingress causes gRPC calls to fail with an HTTP/2 protocol error or gRPC status `INTERNAL` because the proxy cannot upgrade to HTTP/2.
- H2: Setting `transport: http2` on Container Apps ingress allows gRPC unary and streaming calls to work correctly, provided the gRPC client uses TLS credentials matching the Container Apps-managed certificate.
- H3: gRPC clients using `grpc.insecure_channel` (plaintext) cannot connect to a Container Apps endpoint because the ingress requires TLS. The client must use `grpc.secure_channel` with SSL credentials.
- H4: Server streaming gRPC calls are subject to the Container Apps ingress timeout (default 240 seconds). Streams that run longer than the timeout are terminated by Envoy with RST_STREAM.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (grpcio) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Protocol

**Controlled:**

- Python gRPC server (unary + server streaming RPC)
- Container Apps ingress `transport` setting: `http` vs. `http2`
- Client channel type: insecure vs. secure (TLS)

**Observed:**

- gRPC status code returned to client
- Streaming call behavior (message count before failure)
- Envoy transport protocol negotiation logs

**Scenarios:**

- S1: `transport: http`, TLS client → gRPC fails (protocol error)
- S2: `transport: http2`, TLS client → gRPC works (unary + streaming)
- S3: `transport: http2`, insecure client → connection fails (TLS required)
- S4: `transport: http2`, long server stream (>240s) → stream terminated by ingress

## 7. Instrumentation

- `grpcurl` CLI for unary and streaming gRPC calls
- Python gRPC client status code inspection
- `ContainerAppConsoleLogs` for gRPC server logs
- Envoy access logs in `ContainerAppSystemLogs`

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python gRPC server (proto: `SayHello` unary, `StreamNumbers` server streaming).
2. S1: Set `transport: http`; test with `grpcurl`; observe error code.
3. S2: Set `transport: http2`; test with `grpcurl`; verify unary returns response; verify streaming receives all messages.
4. S3: Use plaintext Python gRPC channel (`grpc.insecure_channel`); attempt connection; observe error.
5. S4: Set streaming response to emit one message per second for 300 seconds; observe if stream is cut at ~240s.

## 9. Expected signal

- S1: `grpcurl` reports `Failed to dial target host: context deadline exceeded` or gRPC status `UNAVAILABLE`.
- S2: Unary returns correct response; streaming returns all expected messages.
- S3: Client gets `StatusCode.UNAVAILABLE: failed to connect to all addresses`.
- S4: Stream terminates at approximately 240 seconds with gRPC status `UNAVAILABLE` or `INTERNAL`.

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

- Container Apps ingress gRPC configuration in Bicep: `ingress: { transport: 'http2', targetPort: 50051, external: true }`.
- For Python gRPC client with TLS: `grpc.secure_channel('<app>.<env>.azurecontainerapps.io:443', grpc.ssl_channel_credentials())`.
- `grpcurl` with TLS: `grpcurl <app>.<env>.azurecontainerapps.io:443 proto.Service/Method`.

## 16. Related guide / official docs

- [Container Apps ingress with gRPC](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview#grpc)
- [gRPC on Azure](https://learn.microsoft.com/en-us/aspnet/core/grpc/azure)
