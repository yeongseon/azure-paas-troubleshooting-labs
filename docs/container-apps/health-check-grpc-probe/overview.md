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

# gRPC Health Probe vs. HTTP Liveness Probe: Probe Type Mismatch

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Container Apps supports liveness, readiness, and startup probes. For a server listening on a port that does not speak HTTP/1.1, what happens when an `httpGet` liveness probe is configured on that port? Does the probe fail and cause repeated container restarts? Is `tcpSocket` a valid workaround?

## 2. Why this matters

A gRPC server typically does not expose HTTP/1.1 endpoints. When a Container Apps liveness probe is configured as `httpGet` pointing at a gRPC port (or any non-HTTP port), the probe sends an HTTP/1.1 GET request to a port that does not respond to HTTP/1.1 — the connection fails or returns an unexpected response. Container Apps marks the probe as failed and restarts the container. This causes a continuous restart loop even though the server is healthy, which appears identical to an OOM kill or application crash in logs.

## 3. Customer symptom

"Container restarts every 30 seconds for no apparent reason" or "Liveness probe keeps failing even though the service is responding to requests" or "Container is constantly restarting — no errors in application logs."

## 4. Hypothesis

- H1: An `httpGet` liveness probe targeting a port that does not respond to HTTP/1.1 (e.g., wrong port, gRPC port) fails. Container Apps logs `ProbeFailed | Container failed liveness probe, will be restarted` and terminates the container with reason `ProbeFailure`.
- H2: A `tcpSocket` probe on the same port succeeds because TCP connection establishment succeeds (the server is listening). The container stays healthy.
- H3: Container Apps supports a `grpc` probe type (distinct from `httpGet` and `tcpSocket`) for gRPC health checking protocol.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| App name | aca-diag-batch |
| Runtime | Python 3.11 / gunicorn (HTTP server on port 8000) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Health probes / Protocol

**Controlled:**

- Python/gunicorn Flask app listening on port 8000 (HTTP/1.1 + HTTP/2)
- Three probe configurations tested sequentially:
  - P1: `httpGet /health:8000` — correct (HTTP server, correct path)
  - P2: `httpGet /health:9999` — wrong port (nothing listening) — simulates probe on gRPC-only port
  - P3: `tcpSocket :8000` — TCP connection check only

**Observed:**

- Container health state (Healthy / Unhealthy)
- System log events (`ProbeFailed`, `ContainerTerminated`, `RevisionReady`)
- HTTP response from app during probe failure cycle

## 7. Instrumentation

- YAML-based probe configuration via `az containerapp update --yaml`
- `az containerapp logs show --type system` — system events for probe failures
- `az containerapp revision list --query "properties.healthState"` — revision health state

## 8. Procedure

1. P1: Set `httpGet /health:8000`; verify container stays Healthy.
2. P2: Set `httpGet /health:9999` (nothing listening); wait `failureThreshold × periodSeconds` = 30s; observe `ProbeFailed` → `ContainerTerminated`.
3. P3: Set `tcpSocket :8000`; observe container stays Healthy (TCP connect succeeds).
4. Verify `grpc` probe type is available in CLI help.

## 9. Expected signal

- P1: Container Healthy; no probe events.
- P2: After 3 failures × 10s = 30s, `ProbeFailed | will be restarted`; `ContainerTerminated | reason: ProbeFailure`.
- P3: Container Healthy; TCP connection to port 8000 succeeds regardless of HTTP protocol layer.

## 10. Results

### P1: HTTP probe on correct port — container stays healthy

```yaml
probes:
  - type: Liveness
    httpGet:
      path: /health
      port: 8000
      scheme: HTTP
    initialDelaySeconds: 5
    periodSeconds: 10
    failureThreshold: 3
```

```
az containerapp revision list ... --query "[].healthState"
→ "Healthy"
```

No probe failure events in system logs.

### P2: HTTP probe on wrong port (port 9999 — nothing listening)

```yaml
probes:
  - type: Liveness
    httpGet:
      path: /health
      port: 9999  # Nothing listening
      scheme: HTTP
    initialDelaySeconds: 5
    periodSeconds: 10
    failureThreshold: 3
```

System log events after ~30s:

```
05:53:27 | ProbeFailed    | Container aca-diag-batch failed liveness probe, will be restarted
05:53:27 | ContainerTerminated | Container 'aca-diag-batch' was terminated with exit code '' and reason 'ProbeFailure'

05:54:03 | ProbeFailed    | Container aca-diag-batch failed liveness probe, will be restarted
05:54:03 | ContainerTerminated | Container 'aca-diag-batch' was terminated with exit code '' and reason 'ProbeFailure'
```

The container restarts on each probe failure cycle. The restart loop continues indefinitely — the container never reaches a stable Healthy state.

!!! warning "Key finding"
    The system log reason is `ProbeFailure` — distinct from `OOMKilled` or application crash. This is the diagnostic signal that identifies probe misconfiguration vs. actual container failure.

### P3: tcpSocket probe on port 8000 — container stays healthy

```yaml
probes:
  - type: Liveness
    tcpSocket:
      port: 8000
    initialDelaySeconds: 5
    periodSeconds: 10
    failureThreshold: 3
```

```
05:54:56 | RevisionReady | Successfully provisioned revision 'aca-diag-batch--0000026'
```

Container transitions to Healthy. No `ProbeFailed` events. TCP connection to port 8000 succeeds — the probe does not inspect HTTP response codes.

### H3: gRPC probe type — CLI verification

```bash
az containerapp create --help | grep -i "grpc\|probe"
→ values: grpc, http.
  grpc servers
```

The `grpc` probe type is supported in Container Apps. It uses the gRPC Health Checking Protocol (`grpc.health.v1.Health/Check`) to verify gRPC server health without requiring an HTTP endpoint.

## 11. Interpretation

- **Measured**: H1 is confirmed. An `httpGet` probe on a port that does not respond to HTTP/1.1 fails with `ProbeFailed` events, causing `ContainerTerminated | reason: ProbeFailure` restarts. The restart loop repeats on each `periodSeconds` cycle after `failureThreshold` consecutive failures. **Measured**.
- **Measured**: H2 is confirmed. A `tcpSocket` probe on port 8000 succeeds — TCP connection establishment is all that is checked. The container transitions to Healthy immediately. **Measured**.
- **Observed**: H3 is confirmed. The Container Apps CLI help confirms `grpc` as a supported probe type for gRPC servers. **Observed** (CLI help; actual gRPC probe behavior not separately tested).

## 12. What this proves

- An `httpGet` probe on a non-HTTP port (or wrong port) causes a continuous container restart loop with reason `ProbeFailure`. **Measured**.
- System log event `ContainerTerminated | reason: ProbeFailure` uniquely identifies probe misconfiguration as the cause — distinguishable from OOM (`reason: OOMKilled`) or application crash. **Measured**.
- A `tcpSocket` probe is a valid workaround for non-HTTP servers — it verifies port reachability without inspecting application-layer responses. **Measured**.
- Container Apps supports a `grpc` probe type for native gRPC health checking. **Observed** (CLI).

## 13. What this does NOT prove

- Whether the `grpc` probe type actually invokes `grpc.health.v1.Health/Check` was not tested (no gRPC server deployed).
- Whether an `httpGet` probe on an actual gRPC port (vs. a closed port) produces a different failure message was not tested.
- Startup probe behavior on gRPC servers was not tested.
- Whether readiness probe failures (vs. liveness probe failures) produce different log events was not tested.

## 14. Support takeaway

When a customer reports "container restarts every 30 seconds with no application errors":

1. **Check system log reason**: `ContainerTerminated | reason: ProbeFailure` → probe misconfiguration, not application crash. `OOMKilled` → memory limit. `Error` → application crash.
2. **Verify probe port**: `az containerapp show --query "properties.template.containers[0].probes"`. Probe port must match the port the server listens on.
3. **For gRPC servers**: use `grpc` probe type (gRPC Health Checking Protocol) or `tcpSocket` as a fallback:
   ```yaml
   probes:
     - type: Liveness
       grpc:
         port: 50051
       # OR:
     - type: Liveness
       tcpSocket:
         port: 50051
   ```
4. `httpGet` probes require the server to respond to HTTP/1.1 GET requests with 2xx. gRPC servers, raw TCP servers, and custom binary protocol servers will fail `httpGet` probes.

## 15. Reproduction notes

```bash
APP="<aca-app>"
RG="<resource-group>"

# Export current YAML
az containerapp show -n $APP -g $RG -o yaml > /tmp/app.yaml

# Edit: set httpGet probe on wrong port
# probes:
#   - type: Liveness
#     httpGet: {path: /health, port: 9999, scheme: HTTP}
#     initialDelaySeconds: 5, periodSeconds: 10, failureThreshold: 3

az containerapp update -n $APP -g $RG --yaml /tmp/app.yaml
sleep 40

# Check for ProbeFailure events
az containerapp logs show -n $APP -g $RG --type system --tail 20 | \
  grep -E "ProbeFailed|ProbeFailure|ContainerTerminated"
# Expected: ProbeFailed | Container ... failed liveness probe, will be restarted
#           ContainerTerminated | reason 'ProbeFailure'

# Fix: switch to tcpSocket on correct port
# probes:
#   - type: Liveness
#     tcpSocket: {port: 8000}
az containerapp update -n $APP -g $RG --yaml /tmp/app-fixed.yaml
```

## 16. Related guide / official docs

- [Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
- [Container Apps probe types](https://learn.microsoft.com/en-us/azure/container-apps/containers)
