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

# KEDA Scaler Misconfiguration: Scaler Errors That Look Like Application Errors

!!! info "Status: Planned"

## 1. Question

When a KEDA-based scaling rule in Container Apps is misconfigured — with an incorrect connection string, a missing secret reference, or an unsupported scaler parameter — how does the scaler error surface in system logs versus application logs, and does the misconfiguration prevent scaling entirely or only affect scaling decisions?

## 2. Why this matters

Container Apps scaling rules are powered by KEDA. When a KEDA scaler fails to poll its event source (e.g., cannot connect to a Service Bus namespace, cannot authenticate to a storage account), the scaling decision is absent — but the application may continue running normally. The absence of scaling under load then looks like an application performance problem rather than a scaler configuration problem. Conversely, a scaler that returns a consistently high metric value (due to misconfiguration) can trigger unwanted scale-out events that look like load-driven behavior. Both failure modes are invisible without inspecting KEDA-level logs.

## 3. Customer symptom

"My Container App isn't scaling even though the queue is filling up" or "The app is scaling out unexpectedly even when there's no traffic" or "I see no errors in my app logs but replicas keep going up."

## 4. Hypothesis

- H1: When a KEDA scaler cannot authenticate to its event source (e.g., incorrect Storage Queue connection string), the scaler fails to poll. The scale rule is effectively disabled — the Container App does not scale out, even when the queue has messages. The scaler error appears in `ContainerAppSystemLogs` with a reason related to the scaler, not the application.
- H2: A KEDA scaler with a wrong queue name or topic name that does not exist will return a zero-length metric (no messages). The scaling rule fires as if the queue is empty, and the app scales to `minReplicas` even if other queues have messages. The error may not appear in system logs if the scaler treats a missing queue as a valid empty queue.
- H3: A KEDA scaler that is misconfigured but not erroring (e.g., pointing to a different queue that always has a large backlog) will drive continuous scale-out events. The `ReplicaCount` metric increases without corresponding application load, and the scale-out appears to be driven by legitimate KEDA decisions in the activity log.
- H4: Correcting a KEDA scaler misconfiguration (via a new revision deployment or scaling rule update) takes effect within one KEDA polling interval (default: 30 seconds). The scaler recovers without an app restart.

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

**Experiment type**: Configuration / Scaling

**Controlled:**

- Container App with Azure Storage Queue KEDA scaler
- Scaling rule: `queueLength: 5` (1 replica per 5 messages)
- Scaling scenarios: correct config, wrong connection string, wrong queue name, queue pointing to a high-volume decoy queue

**Observed:**

- Replica count over time under each misconfiguration
- `ContainerAppSystemLogs` scaler error events
- Storage Queue message count vs. actual scale-out behavior
- Time from correction to scaler recovery

**Scenarios:**

- S1: Correct scaler config — baseline; enqueue 20 messages; confirm scale-out to 4 replicas
- S2: Incorrect connection string — enqueue 20 messages; observe scale-out does NOT occur; check system log
- S3: Non-existent queue name — enqueue messages to correct queue; observe scaler treats it as empty
- S4: Queue name pointing to decoy queue with 1000 messages — observe unexpected scale-out
- S5: Correct S2 misconfiguration → measure time to scale-out after fix

**Independent run definition**: One scaling event or scaler error observation per scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `ContainerAppSystemLogs` KQL: `| where Reason contains "Scale" or Message contains "keda" or Message contains "scaler"` — KEDA scaler events
- Azure Monitor metric: `ReplicaCount` — scale-out detection
- Storage Queue: Azure Portal > Queue > Approximate message count — queue depth confirmation
- `az containerapp show --query "properties.template.scale.rules"` — scaling rule configuration
- Time measurement: scaling rule correction timestamp → first scale-out event in system log

## 8. Procedure

_To be defined during execution._

### Sketch

1. S1: Deploy with correct scaler config; enqueue 20 messages; confirm 4 replicas scale out; process messages to zero; confirm scale-in.
2. S2: Change connection string to invalid value (wrong account key); redeploy; enqueue 20 messages; monitor `ReplicaCount` for 10 minutes — confirm no scale-out; inspect system log for scaler error.
3. S3: Change queue name to a non-existent queue; enqueue to the correct queue; monitor scale behavior.
4. S4: Point scaler at a decoy queue with persistent high message count; observe scale-out in `ReplicaCount` without application load; confirm scaler is driving the event.
5. S5: Fix S2 misconfiguration; measure time from fix deployment to first successful scale-out.

## 9. Expected signal

- S1: Replica count reaches 4 within ~2 KEDA polling intervals (60 seconds) of message enqueue.
- S2: No scale-out occurs; `ContainerAppSystemLogs` shows a scaler authentication error; the app continues running at `minReplicas`.
- S3: Scaler may treat missing queue as empty (zero messages); no scale-out; no error in system log — silent misconfiguration.
- S4: Replica count climbs toward `maxReplicas` driven by decoy queue depth; appears as load-driven scaling in `ReplicaCount` metric.
- S5: Scale-out begins within one KEDA polling interval (~30 seconds) after correct configuration is deployed.

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

- KEDA scaler errors in Container Apps are surfaced in `ContainerAppSystemLogs`; they are not visible in `ContainerAppConsoleLogs` (which is application stdout only).
- The KEDA polling interval for Azure Storage Queue scaler defaults to 30 seconds; changes to the scaler configuration (via new revision or rule update) take effect within one polling interval.
- A missing queue name may not produce a scaler error — KEDA treats a non-existent queue as an empty queue (zero messages), which causes scale-in to `minReplicas`, not an error. This is a silent misconfiguration.
- Use `az containerapp show --query "properties.template.scale.rules"` to inspect the current scaling rule configuration from the CLI; the portal shows a simplified view that may omit secret reference details.

## 16. Related guide / official docs

- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [KEDA — Azure Storage Queue scaler](https://keda.sh/docs/scalers/azure-storage-queue/)
- [Troubleshoot scaling in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-scaling)
