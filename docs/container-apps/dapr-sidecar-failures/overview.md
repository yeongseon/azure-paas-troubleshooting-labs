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

# Dapr Sidecar Failures: Visibility and Log Surface

!!! info "Status: Planned"

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
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

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

_To be defined during execution._

### Sketch

1. Deploy publisher and subscriber Container Apps with Dapr enabled and correct config (S4 baseline); verify end-to-end message delivery.
2. Update publisher's Dapr component with an incorrect Service Bus connection string (S1); publish 10 messages; check sidecar logs and Service Bus metrics.
3. Change topic name to a non-existent topic (S2); publish 10 messages; compare dead-letter vs. active message count.
4. Deploy a callee app that always returns HTTP 500; invoke it from the caller app via Dapr service invocation (S3); capture caller's response and sidecar logs.
5. For each scenario, query Application Insights for Dapr dependency entries.
6. Record restart counts before and after each scenario.

## 9. Expected signal

- S1: Sidecar logs show connection or authentication errors under `daprd` container; app container logs are clean; Service Bus receives no messages; replica count unchanged.
- S2: No errors in any log; messages are published to Dapr but delivered to a non-existent topic; Service Bus active message count stays at 0 for the configured topic.
- S3: Caller app receives non-2xx from Dapr sidecar port; sidecar logs record the failed invocation; no replica restart.
- S4: Application Insights shows Dapr dependency entries with correct `dapr` source and operation correlation.

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

- Dapr sidecar logs are emitted under the `daprd` container name in `ContainerAppConsoleLogs`; always filter by this container name when investigating Dapr issues.
- Dapr service invocation uses `localhost:3500` inside the calling container; the HTTP status from this call is the Dapr-level result, not the target app's status directly.
- Topic name mismatches (S2) produce no error at the publisher side; the failure is detectable only by checking Service Bus message counts or Dapr subscriber logs.
- Application Insights Dapr telemetry requires the Container Apps environment to have Application Insights configured at the environment level.

## 16. Related guide / official docs

- [Dapr integration with Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/dapr-overview)
- [Use Dapr Service Invocation in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/microservices-dapr-service-invoke)
- [Observability in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/observability)
