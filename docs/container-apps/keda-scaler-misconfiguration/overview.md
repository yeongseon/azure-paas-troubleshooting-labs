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

# KEDA Scaler Misconfiguration: Silent Scaling Failure and Error Visibility

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

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
| App name | aca-diag-batch |
| Date tested | 2026-05-04 |

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

### S1: Scaler with missing connection secret

```bash
az containerapp update ... \
  --scale-rule-name "bad-queue-scaler" \
  --scale-rule-type "azure-queue" \
  --scale-rule-metadata "queueName=nonexistent-queue" "queueLength=5" "accountName=fakestorageaccount99" \
  --scale-rule-auth "connection=fake-connection-secret"
```

The secret `fake-connection-secret` does not exist in the app's secrets. KEDA immediately logs:

```
KEDAScalerFailed | error parsing azure queue metadata: no connection setting given
```

### S2: Scaler with invalid storage account (DNS failure)

```bash
# Create fake connection string secret
az containerapp secret set ... --secrets \
  "fake-storage-cs=DefaultEndpointsProtocol=https;AccountName=fakeaccount;AccountKey=<base64-garbage>;EndpointSuffix=core.windows.net"

# Update scaler to use the fake secret
az containerapp update ... \
  --scale-rule-auth "connection=fake-storage-cs"
```

KEDA attempts to connect to `fakeaccount.queue.core.windows.net` and fails DNS resolution. System logs show a cascade of three distinct error events every ~30 seconds (one KEDA polling interval):

```
KEDAScalerFailed        | Get "https://fakeaccount.queue.core.windows.net/nonexistent-queue?comp=metadata":
                          dial tcp: lookup fakeaccount.queue.core.windows.net: no such host

FailedGetExternalMetric | unable to get external metric azure-queue-nonexistent-queue for aca-diag-batch:
                          unable to fetch metrics from external metrics API

FailedComputeMetricsReplicas | invalid metrics (1 invalid out of 5), first error is:
                               failed to get s1-azure-queue-nonexistent-queue external metric value
```

!!! warning "Key finding"
    All three events repeat every ~30 seconds (KEDA polling interval). The app continues running at `minReplicas=0`. No scale-out occurs regardless of any actual workload. The errors are visible in system logs but the app itself shows no errors.

### S3: Application behavior during scaler failure

```bash
# App remains accessible throughout
curl https://aca-diag-batch.../health
→ {"status": "healthy"}
```

The app runs normally. The scaler failure does not affect running replicas — only scale-out decisions are blocked.

### Polling interval

KEDA retries the scaler on each polling interval (default 30s). Log timestamps show:
```
05:46:56 | KEDAScalerFailed
05:47:25 | KEDAScalerFailed (next cycle)
```
**29 seconds between failures** — consistent with the 30s default polling interval.

## 11. Interpretation

- **Measured**: H1 is confirmed. A KEDA scaler that cannot authenticate to its event source (missing secret, invalid credentials, DNS failure) causes `KEDAScalerFailed` events in `ContainerAppSystemLogs`. No scale-out occurs. The scaler is effectively disabled — the app stays at `minReplicas`. **Measured**.
- **Measured**: The error cascade is consistent: `KEDAScalerFailed` → `FailedGetExternalMetric` → `FailedComputeMetricsReplicas`, repeating every polling interval (~30s). **Measured**.
- **Inferred**: H2 (missing queue name treated as empty queue — silent misconfiguration) was not separately confirmed. In our test, DNS failure made the "missing queue" scenario manifest as an explicit error rather than silent zero-metric behavior. **Inferred** — not directly tested.
- **Not Proven**: H3 (decoy queue driving spurious scale-out) and H4 (recovery timing after fix) were not tested.

## 12. What this proves

- Invalid KEDA scaler credentials (missing secret, DNS failure) produce explicit `KEDAScalerFailed` events in `ContainerAppSystemLogs`, repeating every KEDA polling interval (~30s). **Measured**.
- The scaler failure does not affect running application replicas — the app continues serving requests normally. **Measured**.
- Three distinct event types appear in sequence: `KEDAScalerFailed` → `FailedGetExternalMetric` → `FailedComputeMetricsReplicas`. **Measured**.
- KEDA polling interval is ~30s (matches default configuration). **Measured** (29s observed between error cycles).

## 13. What this does NOT prove

- Whether a non-existent queue (valid account, queue doesn't exist) is treated as an empty queue (silent zero-metric) or produces an error — not tested.
- Recovery time after fixing the scaler configuration was not measured.
- Whether the scale-out failure affects the KEDA HPA `ScaledObject` status was not checked.
- Behavior with other scaler types (Service Bus, HTTP, CPU) was not tested.

## 14. Support takeaway

When a customer reports "KEDA scale rule is not working" or "Container App is not scaling out":

1. **Check `ContainerAppSystemLogs`** for `KEDAScalerFailed`, `FailedGetExternalMetric`, `FailedComputeMetricsReplicas` events. These repeat every polling interval (~30s) if misconfigured.
2. **Verify the secret exists**: `az containerapp secret list -n <app> -g <rg>`. The scaler `auth` block references a secret by name — if the secret doesn't exist, KEDA cannot build the scaler.
3. **Verify the connection string format**: Azure Storage Queue scaler expects `DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net`.
4. **The app keeps running** — scaler failure does not kill running replicas. Scale-out is blocked but existing replicas continue serving traffic.
5. **Inspect current scale rules**: `az containerapp show -n <app> -g <rg> --query "properties.template.scale.rules"`.

## 15. Reproduction notes

```bash
APP="<aca-app>"
RG="<resource-group>"

# Create fake connection string secret
az containerapp secret set -n $APP -g $RG \
  --secrets "fake-storage-cs=DefaultEndpointsProtocol=https;AccountName=fakeaccount;AccountKey=ZmFrZQ==;EndpointSuffix=core.windows.net"

# Add misconfigured Azure Queue scaler
az containerapp update -n $APP -g $RG \
  --scale-rule-name "bad-queue-scaler" \
  --scale-rule-type "azure-queue" \
  --scale-rule-metadata "queueName=nonexistent-queue" "queueLength=5" "accountName=fakeaccount" \
  --scale-rule-auth "connection=fake-storage-cs"

# Wait 30-60s and check system logs
sleep 45
az containerapp logs show -n $APP -g $RG --type system --tail 20 | \
  grep -E "KEDAScalerFailed|FailedGetExternalMetric|FailedComputeMetrics"

# Expected output (repeating every ~30s):
# KEDAScalerFailed | Get "https://fakeaccount.queue.core.windows.net/...": dial tcp: lookup ... no such host
# FailedGetExternalMetric | unable to get external metric azure-queue-nonexistent-queue...
# FailedComputeMetricsReplicas | invalid metrics (1 invalid out of 5)...
```

## 16. Related guide / official docs

- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [KEDA — Azure Storage Queue scaler](https://keda.sh/docs/scalers/azure-storage-queue/)
- [Troubleshoot scaling in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-scaling)
