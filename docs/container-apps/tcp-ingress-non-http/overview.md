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

# TCP Ingress for Non-HTTP Protocols: Configuration and Limitations

!!! info "Status: Planned"

## 1. Question

Container Apps supports TCP ingress (non-HTTP) for protocols like raw TCP, gRPC, and custom binary protocols. What are the exact limitations of TCP ingress compared to HTTP ingress — specifically around TLS termination, load balancing behavior, and observability — and what failure modes occur when HTTP ingress is used for non-HTTP traffic?

## 2. Why this matters

Teams deploying database proxies, message brokers, or custom TCP services on Container Apps may configure HTTP ingress by default (assuming it is the standard choice) and then encounter unexpected behavior: the ingress attempts HTTP parsing on binary data, mangling the protocol. Understanding when to use TCP ingress vs. HTTP ingress and the trade-offs (TCP ingress does not do TLS termination at the ingress level, limiting observability) is essential for non-web workloads.

## 3. Customer symptom

"gRPC service connects but immediately returns a protocol error" or "Custom TCP client can't establish a connection even though the container is listening" or "Redis proxy on Container Apps works locally but fails when deployed."

## 4. Hypothesis

- H1: When a container listens on a custom TCP protocol port and HTTP ingress is configured, the ingress attempts HTTP parsing on the first bytes. Non-HTTP data (e.g., a database handshake) triggers a `400 Bad Request` or protocol error from the ingress before reaching the container.
- H2: TCP ingress configured for the correct port allows raw TCP connections to pass through to the container. TLS is handled by the client-container pair (passthrough TLS), not by the ingress.
- H3: TCP ingress does not provide per-request metrics (request count, latency) in Azure Monitor because individual TCP flows are not HTTP requests. Observability is limited to connection count and bytes transferred.
- H4: TCP ingress requires that the container expose a specific port; the ingress does not support multiple TCP ports per container app (unlike Kubernetes Services which can map multiple ports).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (raw TCP server) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Protocol

**Controlled:**

- Container running a custom TCP echo server (non-HTTP) on port 9000
- HTTP ingress configured on port 9000 (incorrect)
- TCP ingress configured on port 9000 (correct)

**Observed:**

- Connection behavior and error message under HTTP ingress
- Connection behavior and data integrity under TCP ingress
- Available metrics under each ingress type

**Scenarios:**

- S1: HTTP ingress, TCP client sends non-HTTP data → protocol error
- S2: TCP ingress, TCP client sends non-HTTP data → echo response received correctly
- S3: Observe metric availability for TCP vs HTTP ingress

## 7. Instrumentation

- `nc` or Python `socket` client to send raw TCP data
- Captured response (hex dump to verify echo integrity)
- Azure Monitor Container Apps metrics for TCP vs. HTTP ingress

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python TCP echo server (`asyncio` server) on port 9000.
2. S1: Configure HTTP ingress on port 9000; connect with TCP client; send binary data; observe error response.
3. S2: Switch to TCP ingress; connect TCP client; send binary data; verify echo response received intact.
4. S3: Compare available Azure Monitor metrics for each configuration.

## 9. Expected signal

- S1: Connection established but data mangled; HTTP 400 or protocol error returned by ingress.
- S2: Raw TCP echo works correctly; binary data round-trips intact.
- S3: HTTP ingress: request count, response codes, latency metrics available. TCP ingress: only connection-level metrics.

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

- TCP ingress is configured with `--transport tcp` in `az containerapp ingress enable`.
- TCP ingress supports TLS passthrough (the container handles TLS) but not TLS termination at the ingress layer.
- gRPC uses HTTP/2 and should use HTTP ingress with `--transport http2`, not TCP ingress.

## 16. Related guide / official docs

- [Container Apps ingress overview](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [TCP ingress in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to)
