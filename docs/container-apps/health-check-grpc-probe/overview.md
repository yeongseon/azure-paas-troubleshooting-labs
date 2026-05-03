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

# gRPC Health Probe vs. HTTP Liveness Probe: Probe Type Mismatch on gRPC Server

!!! info "Status: Planned"

## 1. Question

Container Apps supports liveness, readiness, and startup probes using HTTP GET or TCP socket mechanisms. For a gRPC server that does NOT expose an HTTP health endpoint but implements the gRPC Health Checking Protocol (`grpc.health.v1.Health/Check`), what happens when an HTTP liveness probe is configured? Does the probe fail (gRPC server returns HTTP/2 frames that the probe interprets as a failure) and cause repeated container restarts?

## 2. Why this matters

gRPC servers typically do not expose HTTP endpoints. When a Container Apps liveness probe is configured as `httpGet` pointing at a gRPC port, the probe sends an HTTP/1.1 GET request to a port that speaks HTTP/2 gRPC — the server responds with a gRPC error or an HTTP/2 GOAWAY frame, which the probe interprets as a failure. This causes the platform to restart the container repeatedly even though the gRPC server is healthy, manifesting as an OOMKill-like restart loop that is actually a probe misconfiguration.

## 3. Customer symptom

"gRPC server restarts every 30 seconds for no apparent reason" or "Liveness probe keeps failing even though the gRPC service is responding to requests" or "Container is constantly restarting — no errors in application logs."

## 4. Hypothesis

- H1: An `httpGet` liveness probe targeting a gRPC server port returns a non-2xx response (the gRPC server speaks HTTP/2 binary, not HTTP/1.1). Container Apps marks the probe as failed and restarts the container.
- H2: A `tcpSocket` probe on the gRPC port succeeds because TCP connection establishment succeeds (the gRPC server is listening). This is a functional workaround but does not verify that the gRPC service is actually healthy.
- H3: The correct solution for a gRPC server is either: (a) add a sidecar HTTP health endpoint, (b) use the gRPC health checking protocol with a `grpc` probe type (not currently supported in Container Apps — verify), or (c) use `tcpSocket` as a pragmatic alternative.
- H4: Startup probes configured as `httpGet` on a gRPC server port also fail during startup, causing the container to be killed before it finishes initializing, especially for servers with long startup times.

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

**Experiment type**: Health probes / Protocol

**Controlled:**

- Python gRPC server on port 50051 (no HTTP endpoint)
- Liveness probe type: `httpGet` vs. `tcpSocket`

**Observed:**

- Container restart frequency
- Probe failure events in Container Apps system logs
- gRPC server health status (actual vs. probed)

**Scenarios:**

- S1: `httpGet` probe on port 50051 → probe fails → container restarts
- S2: `tcpSocket` probe on port 50051 → probe succeeds → container stable
- S3: Add HTTP health sidecar on port 8080 → `httpGet` probe on port 8080 → container stable

## 7. Instrumentation

- `ContainerAppSystemLogs` for probe failure events and restart events
- `az containerapp revision show` for restart count
- `az containerapp logs show --type system` for probe failure messages

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python gRPC server; configure `httpGet` liveness probe on port 50051; observe restart loop.
2. Confirm gRPC server is responding correctly with `grpcurl` from outside.
3. S2: Change probe to `tcpSocket` on port 50051; verify container stabilizes.
4. S3: Add HTTP health endpoint (`/healthz` returning 200) on port 8080; configure `httpGet` probe on port 8080; verify.

## 9. Expected signal

- S1: Container restarts every `failureThreshold × periodSeconds` seconds; system logs show `Liveness probe failed: HTTP probe failed with statuscode: ...` or `Connection refused` (if HTTP/2 rejects HTTP/1.1).
- S2: No restart events; container remains stable; gRPC service continues to serve requests.
- S3: HTTP probe succeeds; container stable; gRPC service unaffected.

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

- Container Apps probe configuration in Bicep: `probes: [{ type: 'Liveness', httpGet: { port: 50051, path: '/healthz' }, periodSeconds: 10, failureThreshold: 3 }]`.
- TCP socket probe: `probes: [{ type: 'Liveness', tcpSocket: { port: 50051 }, periodSeconds: 10 }]`.
- gRPC Health Checking Protocol: `grpc.health.v1.Health/Check` — verify if Container Apps natively supports `grpc` probe type (as of 2024, only HTTP and TCP are supported).

## 16. Related guide / official docs

- [Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
