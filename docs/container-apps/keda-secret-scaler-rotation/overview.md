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

# KEDA Scaler Authentication Secret Rotation Failure

!!! info "Status: Planned"

## 1. Question

When a KEDA scaler in Container Apps uses a secret for authentication (e.g., Service Bus connection string, Storage Queue SAS token) and that secret is rotated (new value set, old value revoked), does the scaler continue to function with the cached value, fail silently, or fail with an observable error that halts scaling?

## 2. Why this matters

Container Apps KEDA scalers use secrets from the container app's secret store for authentication. When the underlying service credential is rotated (for security compliance), the secret value in Container Apps must be updated. If the rotation is not synchronized, the KEDA scaler uses an invalid credential, causing it to fail to poll the queue depth. When the scaler cannot read the queue, it may scale to zero (no trigger signal) while messages accumulate, creating a processing backlog that is not immediately visible.

## 3. Customer symptom

"Messages are accumulating in the queue but the app is not scaling up" or "After rotating the Service Bus connection string, the consumer stopped processing messages" or "KEDA shows no queue depth even though we know messages are there."

## 4. Hypothesis

- H1: When the Service Bus connection string in the Container Apps secret is updated to a rotated value, but the container app is not restarted, the KEDA scaler continues using the cached secret value until the revision is restarted.
- H2: When the old Service Bus connection string is revoked and the Container Apps secret still holds the old value, the KEDA scaler fails to poll the queue. The scaling behavior defaults to 0 replicas (no trigger signal = scale to zero).
- H3: The KEDA scaler failure is visible in Container Apps system logs under `ContainerAppSystemLogs` as a scaler authentication error, but not in application logs (the scaler failure is platform-side, not application-side).
- H4: Updating the secret value in Container Apps and triggering a new revision (or waiting for the scaler cache to expire) restores scaler functionality.

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

**Experiment type**: Scaling / Security

**Controlled:**

- Container App with KEDA Service Bus trigger (queue depth scaling)
- Service Bus namespace with a test queue
- Container Apps secret holding the Service Bus connection string

**Observed:**

- Replica count behavior when scaler auth fails
- KEDA scaler error messages in system logs
- Queue depth vs. replica count during credential rotation

**Scenarios:**

- S1: Valid connection string, messages in queue → scaling triggers correctly
- S2: Revoke old key, secret still holds old value → scaling stops
- S3: Update Container Apps secret with new key → restore scaling

## 7. Instrumentation

- `az containerapp replica list` to observe replica count over time
- Service Bus queue depth metric in Azure Monitor
- `ContainerAppSystemLogs` for KEDA scaler errors
- Container app scaling trigger activity logs

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container App with KEDA Service Bus scaler; send messages; verify scaling triggers.
2. S2: Rotate the Service Bus SAS key (regenerate in portal); old key is now invalid. Do NOT update Container Apps secret. Send more messages; observe if replica count increases.
3. Check `ContainerAppSystemLogs` for scaler errors.
4. S3: Update Container Apps secret with new connection string (`az containerapp secret set`); create new revision; verify scaling resumes.

## 9. Expected signal

- S1: Replica count increases as messages arrive; queue depth decreases as messages are processed.
- S2: After key rotation, KEDA scaler fails; replica count stays at 0 or current value; queue depth increases; system logs show authentication error.
- S3: After secret update and revision, scaler reconnects; replica count responds to queue depth.

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

- Container Apps secrets are immutable per revision. Updating a secret requires creating a new revision (`az containerapp update` triggers a new revision by default for scaling rule changes).
- KEDA scalers in Container Apps cache authentication credentials; the exact cache TTL is platform-managed.
- Prefer Managed Identity-based KEDA authentication over connection strings to avoid secret rotation issues.

## 16. Related guide / official docs

- [Scale rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Service Bus scaling trigger](https://learn.microsoft.com/en-us/azure/container-apps/scale-app#azure-service-bus)
- [Rotate secrets for Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
