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

# HTTP/2 and gRPC Timeout Behavior in Container Apps

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

How does Azure Container Apps Envoy ingress handle long-lived HTTP/2 streams used for gRPC? Does the idle timeout apply to the stream or the connection, and what happens to in-flight gRPC streaming calls that exceed the ingress timeout?

## 2. Why this matters

gRPC is increasingly used for microservice communication in Container Apps environments. Envoy (the underlying ingress proxy) applies timeouts to HTTP/2 streams differently from HTTP/1.1 connections. Support cases arise when:

- gRPC server-streaming RPCs are unexpectedly terminated after a fixed duration
- Bidirectional streaming calls fail at exactly the ingress timeout
- Clients receive `UNAVAILABLE` or `DEADLINE_EXCEEDED` from the gRPC layer rather than the application
- Health probe conflicts occur because gRPC health checking requires HTTP/2 but the probe is configured for HTTP/1.1

## 3. Customer symptom

- "Our gRPC streaming calls fail after exactly 4 minutes."
- "The gRPC connection works fine locally but fails in Container Apps."
- "We're getting UNAVAILABLE errors from gRPC even though the server is running."
- "gRPC health check is failing even though the server health endpoint works."

## 4. Hypothesis

**H1 — Stream timeout applies to idle streams**: Envoy's idle timeout applies to HTTP/2 streams with no bytes flowing. A gRPC server-streaming RPC that pauses sending data (even if the connection is alive) will be terminated at the idle timeout.

**H2 — Periodic messages prevent timeout**: Sending periodic heartbeat messages (or gRPC keepalive pings) resets the idle timer and prevents stream termination.

**H3 — gRPC health probe requires HTTP/2**: Configuring a liveness probe with `scheme: GRPC` requires HTTP/2 ingress. If ingress is HTTP/1.1, the probe fails. The error message may not clearly indicate the HTTP version mismatch.

**H4 — Connection reuse vs. stream timeout**: The HTTP/2 connection between Envoy and the upstream may be reused across multiple RPC calls. Connection-level keepalive is separate from stream-level timeout.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (grpcio) |
| Ingress | External, HTTP/2 enabled |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Network + Timeout

**Controlled:**

- Ingress timeout configuration (default 240s, custom values)
- gRPC streaming type (server-streaming, bidirectional)
- Heartbeat frequency (none, 30s, 60s, 120s)
- HTTP/2 vs. HTTP/1.1 ingress setting

**Observed:**

- Stream termination timing relative to configured timeout
- gRPC status code received by client on termination (`UNAVAILABLE`, `DEADLINE_EXCEEDED`, `INTERNAL`)
- Envoy access log entries showing stream duration
- Application-side stream completion vs. error

## 7. Instrumentation

- gRPC server: Python with `grpcio`, server-streaming RPC that sends one message every N seconds
- gRPC client: records received message count, stream duration, termination code
- Container Apps system logs: Envoy access logs
- Custom metric: stream duration histogram

**Envoy access log query:**

```kusto
ContainerAppConsoleLogs
| where ContainerAppName == "grpc-server"
| where Log contains "grpc"
| project TimeGenerated, Log
| order by TimeGenerated desc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az containerapp env create \
  --name env-grpc-test \
  --resource-group rg-grpc-timeout \
  --location koreacentral

az containerapp create \
  --name grpc-server \
  --resource-group rg-grpc-timeout \
  --environment env-grpc-test \
  --image <grpc-server-image> \
  --ingress external \
  --target-port 50051 \
  --transport http2
```

### 8.2 Scenarios

**S1 — Server-streaming, no heartbeat**: Client opens server-streaming RPC. Server sends messages every 120s. Measure when Envoy terminates the stream.

**S2 — Server-streaming, frequent heartbeat (30s)**: Same RPC, but server sends a heartbeat message every 30s. Verify stream survives beyond 240s.

**S3 — Bidirectional streaming**: Client and server send messages. Measure timeout behavior under bidirectional traffic.

**S4 — gRPC health probe**: Configure liveness probe with `type: GRPC`. Verify it works with HTTP/2 ingress. Switch to HTTP/1.1 ingress and observe probe failure.

## 9. Expected signal

- **S1**: Stream terminated at ~240s (Envoy default idle timeout). Client receives `UNAVAILABLE`.
- **S2**: Stream survives beyond 240s with heartbeat every 30s.
- **S3**: Bidirectional stream with active traffic survives indefinitely (idle timeout not triggered).
- **S4**: gRPC health probe requires HTTP/2 transport — fails with HTTP/1.1.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Envoy configuration in Container Apps is not directly accessible; timeout values are inferred from observed behavior.
- gRPC keepalive at the transport layer (PING frames) is separate from application-level heartbeat messages.
- Test uses Python grpcio; Go/Java gRPC clients may have different keepalive defaults.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Envoy applies idle timeout to HTTP/2 streams | **Strongly Suggested** (Envoy docs confirm this behavior) |
| Heartbeat messages reset idle timer | **Inferred** |
| gRPC health probe requires HTTP/2 | **Inferred** |

## 14. Related experiments

- [gRPC End-to-End in Container Apps](../liveness-probe-failures/overview.md) — full gRPC connectivity test
- [HTTP Ingress Timeout](../liveness-probe-failures/overview.md) — HTTP/1.1 timeout behavior

## 15. References

- [Container Apps HTTP/2 ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview#http2)
- [gRPC health checking protocol](https://grpc.github.io/grpc/core/md_doc_health-checking.html)
- [Envoy timeout documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/timeouts)

## 16. Support takeaway

For gRPC streaming issues in Container Apps:

1. Check if the stream fails at exactly the ingress timeout (default ~240s). This indicates Envoy idle timeout, not an application bug.
2. For long-lived streaming RPCs, implement application-level heartbeat messages sent at < (timeout/2) intervals.
3. Verify HTTP/2 transport is enabled on the ingress — gRPC requires HTTP/2. Check `az containerapp show` for `transport: http2`.
4. gRPC health probes (`type: GRPC`) require HTTP/2 transport on the ingress. If probes fail with no obvious error, check ingress transport setting.
5. For `DEADLINE_EXCEEDED` errors, check the client-side deadline first — these are set by the caller and enforced client-side, not by Envoy.
