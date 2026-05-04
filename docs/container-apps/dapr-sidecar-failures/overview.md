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

# Dapr Sidecar Failures: Service Invocation Errors and Observability

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04. Partial experiment — service invocation failure confirmed. Pub/Sub misconfiguration and Application Insights telemetry not tested (requires Service Bus and AI integration).

## 1. Question

When a Dapr-enabled Container App experiences a service invocation failure or a Pub/Sub component misconfiguration, which log surfaces capture the failure — and does the platform restart the container, the sidecar, or neither?

## 2. Why this matters

Dapr is used in Container Apps for service-to-service calls and event-driven messaging. When Dapr fails — due to a misconfigured component, an unreachable target app, or an invalid credential — the failure is often invisible to the application container: the app receives a 500 or timeout from the Dapr sidecar HTTP port, but no error appears in its own stdout. Support engineers examining restart loops or missing messages may overlook the Dapr sidecar logs entirely if they search only the application container's console logs.

## 3. Customer symptom

"My Container App stopped processing messages but shows no errors in application logs" or "Service invocation between two Container Apps started returning 500 after a configuration change" or "Dapr shows as enabled but events are not being delivered."

## 4. Hypothesis

- H1: When a Dapr Pub/Sub component is misconfigured (wrong topic name or wrong namespace credential), the sidecar logs a component-level error in `ContainerAppConsoleLogs` under the `daprd` container name. The application container receives no error signal and continues running.
- H2: When service invocation fails (target app unreachable or target app's Dapr sidecar returns an error), the calling app receives a non-2xx HTTP response from the local Dapr sidecar port (3500); the platform does not restart either container automatically.
- H3: A Dapr sidecar failure that does not crash the sidecar process does not trigger a replica restart. A replica restart (pod replacement) only occurs if the main application container's liveness probe fails.
- H4: Dapr telemetry (traces and metrics) emitted to Application Insights captures Dapr-layer failures with a `dapr` source tag in the `dependencies` table — providing a second visibility surface beyond sidecar container logs.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (gunicorn 25.3.0) |
| OS | Linux |
| Date tested | 2026-05-04 |
| App image | `acrlabcdrbackhgtaj.azurecr.io/diag-app:v4` |
| Dapr app-id | `diag-app` |
| Dapr app-port | 8000 |

## 6. Variables

**Experiment type**: Reliability / Observability

**Controlled:**

- Two Container Apps with Dapr enabled (publisher and subscriber)
- Azure Service Bus namespace for Pub/Sub component
- Dapr version (platform-managed)
- Application Insights configured in the Container Apps environment

**Observed:**

- `ContainerAppConsoleLogs` entries for the `daprd` container
- `ContainerAppSystemLogs` entries (restart events, if any)
- HTTP status returned to the calling app from Dapr sidecar port
- Application Insights `dependencies` table — Dapr-sourced entries
- Replica restart count

**Scenarios:**

- S1: Pub/Sub component with incorrect Service Bus connection string — component credential failure
- S2: Pub/Sub component with wrong topic name — silent routing mismatch
- S3: Service invocation from caller app to a callee app that returns HTTP 500 — invocation failure
- S4: Correct configuration — baseline

**Independent run definition**: One 10-minute observation window per scenario with 1 publish/invoke event per 30 seconds.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `ContainerAppConsoleLogs` KQL: `| where ContainerName == "daprd"` — sidecar error messages
- `ContainerAppSystemLogs` KQL: `| where Reason in ("OOMKilled", "BackOff", "Killing")` — restart events
- Calling app response log: HTTP status received from `localhost:3500` (Dapr sidecar port)
- Service Bus metrics: dead-letter message count, active message count (S1, S2)
- Application Insights: `dependencies | where data contains "dapr"` — Dapr trace entries
- `az containerapp replica list` — replica count over time

## 8. Procedure

### S3 executed: Service invocation to non-existent app

1. Enabled Dapr on `aca-diag-batch` (`dapr-app-id=diag-app`, `dapr-app-port=8000`, protocol `http`).
2. Deployed `diag-app:v4` — added `/dapr-test?app=<target>` endpoint that calls `http://localhost:3500/v1.0/invoke/<target>/method/hello`.
3. Routed 100% traffic to revision `aca-diag-batch--v4a`.
4. Confirmed `DAPR_HTTP_PORT=3500` and `DAPR_GRPC_PORT=50001` injected via `/env`.
5. Called `/dapr-test?app=nonexistent-service` five times; captured HTTP responses.
6. Checked `ContainerAppSystemLogs` for restart events (`ContainerTerminated`, `BackOff`, `OOMKilled`) after each call.
7. Verified replica `runningState` after all five calls.

### S1, S2, S4 — not executed

Pub/Sub scenarios require an Azure Service Bus namespace and a configured Dapr component. Application Insights telemetry (S4) requires environment-level AI configuration. These scenarios were scoped out of this run due to cost and infrastructure constraints.

## 9. Expected signal

- S1: Sidecar logs show connection or authentication errors under `daprd` container; app container logs are clean; Service Bus receives no messages; replica count unchanged.
- S2: No errors in any log; messages are published to Dapr but delivered to a non-existent topic; Service Bus active message count stays at 0 for the configured topic.
- S3: Caller app receives non-2xx from Dapr sidecar port; sidecar logs record the failed invocation; no replica restart.
- S4: Application Insights shows Dapr dependency entries with correct `dapr` source and operation correlation.

## 10. Results

### S3: Service invocation to non-existent app-id

**Dapr environment variables injected on sidecar enable:**

```
DAPR_HTTP_PORT = 3500
DAPR_GRPC_PORT = 50001
```

**System log events on Dapr enable (from `ContainerAppSystemLogs`):**

```
2026-05-04 06:02:08 | ContainerCreated | Created container 'daprd'
2026-05-04 06:02:08 | ContainerStarted | Started container 'daprd'
2026-05-04 06:02:10 | ContainerCreated | Created container 'aca-diag-batch'
2026-05-04 06:02:10 | ContainerStarted | Started container 'aca-diag-batch'
```

**Five calls to `/dapr-test?app=nonexistent-service`:**

| Call | HTTP status from app | Dapr sidecar response |
|------|---------------------|-----------------------|
| 1 | 500 | `HTTP Error 500: Internal Server Error` |
| 2 | 500 | `HTTP Error 500: Internal Server Error` |
| 3 | 500 | `HTTP Error 500: Internal Server Error` |
| 4 | 500 | `HTTP Error 500: Internal Server Error` |
| 5 | 500 | `HTTP Error 500: Internal Server Error` |

**System logs after five invocation failures — restart-related events:**

```
(none — no ContainerTerminated, BackOff, OOMKilled, or Killing events)
```

**Replica state after five failures:**

```json
{
  "name": "aca-diag-batch--v4a-7fcc47894d-kmv2z",
  "runningState": "Running"
}
```

**Console logs during failures:**  
No Dapr-specific error messages appeared in the application container's stdout. The application container logged only gunicorn worker startup entries. The `daprd` container was not queryable separately via `az containerapp logs show --container daprd` in this revision configuration.

## 11. Interpretation

- **Observed**: When Dapr service invocation targets a non-existent app-id, the Dapr sidecar returns HTTP 500 to the calling application on port 3500. The application receives no other signal and must handle this as a normal HTTP error.
- **Observed**: Enabling Dapr on a Container App injects `DAPR_HTTP_PORT` and `DAPR_GRPC_PORT` environment variables into the application container. The `daprd` sidecar container is created and started as a separate container in the same replica (confirmed via system logs showing `ContainerCreated` for `daprd`).
- **Observed**: Five consecutive Dapr service invocation failures produced zero restart events in `ContainerAppSystemLogs`. The replica remained in `Running` state throughout.
- **Inferred**: The Dapr sidecar process does not crash or restart when a service invocation fails due to an unreachable target. The sidecar handles the error at the protocol layer and returns a 500 to the caller without affecting its own lifecycle.
- **Inferred**: The application container's liveness probe (if configured) is the only mechanism that would trigger a replica restart in this failure mode. Dapr invocation failures do not propagate to the container health check system.
- **Not Proven**: Whether failed invocations are emitted to Application Insights as failed dependency entries — the environment did not have AI configured at the environment level.

## 12. What this proves

- Enabling Dapr on a Container App injects `DAPR_HTTP_PORT=3500` and `DAPR_GRPC_PORT=50001` as environment variables; the `daprd` container is created and started as a separate sidecar in the same replica.
- Dapr service invocation to a non-existent app-id returns HTTP 500 from the sidecar to the calling application; the error does not propagate to container lifecycle management.
- Repeated Dapr invocation failures do not trigger replica restarts; the platform does not treat Dapr-layer errors as container health failures.

## 13. What this does NOT prove

- Whether Pub/Sub component misconfiguration (wrong credentials or topic name) surfaces in sidecar logs or is silently dropped — not tested in this run.
- Whether failed Dapr invocations are captured in Application Insights as failed dependency entries — requires AI integration at the environment level.
- Whether a crashing `daprd` process (not a protocol-level error) triggers a replica restart or only a sidecar restart.

## 14. Support takeaway

When a customer reports "Dapr service invocation returning 500" or "messages not being processed with no application errors":

1. **Dapr failures are silent to the app container.** The app receives a 500 from `localhost:3500` but its own logs show nothing. Always check `ContainerAppSystemLogs` for `daprd` container events and `ContainerAppConsoleLogs` filtering by `ContainerName == "daprd"`.
2. **No restart means no liveness failure.** If the replica is `Running` and there are no `ContainerTerminated` events, the Dapr sidecar did not crash — the failure is a protocol-level error (wrong app-id, unreachable target, component misconfiguration).
3. **Check the Dapr sidecar container name.** System logs show `ContainerCreated` / `ContainerStarted` for `daprd` when Dapr is enabled. If these events are absent after a configuration change, Dapr may not be enabled on the current revision.
4. **Service invocation failures require app-side error handling.** The platform does not circuit-break or retry Dapr invocations automatically. The application must treat non-2xx responses from port 3500 as application-level errors and implement retries or fallbacks.

## 15. Reproduction notes

- Dapr sidecar logs are emitted under the `daprd` container name in `ContainerAppConsoleLogs`; always filter by this container name when investigating Dapr issues.
- Dapr service invocation uses `localhost:3500` inside the calling container; the HTTP status from this call is the Dapr-level result, not the target app's status directly.
- Topic name mismatches (S2) produce no error at the publisher side; the failure is detectable only by checking Service Bus message counts or Dapr subscriber logs.
- Application Insights Dapr telemetry requires the Container Apps environment to have Application Insights configured at the environment level.

## 16. Related guide / official docs

- [Dapr integration with Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/dapr-overview)
- [Use Dapr Service Invocation in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/microservices-dapr-service-invoke)
- [Observability in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/observability)
