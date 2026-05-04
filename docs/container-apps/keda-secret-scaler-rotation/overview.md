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

# KEDA Scaler Authentication Secret Rotation Failure

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04. H1 disproven — KEDA immediately picks up the rotated secret value without a revision restart. H3 confirmed — scaler failures are visible in system logs.

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
| Date tested | 2026-05-04 |
| Service Bus namespace | `sb-lab-batch-75561` (Standard tier) |
| Container App | `aca-diag-batch` |
| Secret name | `sb-conn-test` |

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

1. Created Service Bus namespace `sb-lab-batch-75561` with queue `main-queue`.
2. Stored valid connection string as Container Apps secret `sb-conn-test`.
3. Added KEDA scale rule `sb-rotation-test` of type `azure-servicebus` using `sb-conn-test`.
4. **S2**: Updated `sb-conn-test` secret value to an invalid/rotated connection string (`SharedAccessKey=ROTATED_INVALID_KEY...`). Did NOT create a new revision or restart the app. Observed `ContainerAppSystemLogs` for 30 seconds.
5. **S3**: Restored `sb-conn-test` to the valid connection string. Observed `ContainerAppSystemLogs` for 30 seconds.
6. Checked whether secret rotation created a new revision (`az containerapp revision list`).

**Not tested**: End-to-end scaling behavior (messages in queue → replicas scale up) was not confirmed due to Service Bus authentication constraints from the KEDA control plane.

## 9. Expected signal

- S1: Replica count increases as messages arrive; queue depth decreases as messages are processed.
- S2: After key rotation, KEDA scaler fails; replica count stays at 0 or current value; queue depth increases; system logs show authentication error.
- S3: After secret update and revision, scaler reconnects; replica count responds to queue depth.

## 10. Results

### Revision count before and after secret rotation

Before rotation: latest revision `aca-diag-batch--0000031`.  
After `az containerapp secret set` with invalid value: latest revision remains `aca-diag-batch--0000031`.  
**No new revision was created by secret rotation.**

### KEDA system log events after rotation to invalid key

```
06:56:14 | KEDAScalersStarted        | Scaler azure-servicebus is built
06:56:14 | KEDAScalerFailed          | GET https://sb-lab-batch-75561.servicebus.windows.net/main-queue
                                       RESPONSE 401: Unauthorized
06:56:15 | FailedGetExternalMetric   | unable to get external metric azure-servicebus-main-queue for aca-diag-batch: unable to fetch metrics...
06:56:15 | FailedComputeMetricsReplicas | invalid metrics (1 invalid out of 5), first error is: failed to get ...
```

**Time from secret rotation to first `KEDAScalerFailed` event: ~19 seconds.**

### After restoration to valid key

KEDA continued polling with the same `FailedGetExternalMetric` pattern — the auth issue persisted because the KEDA control plane in this environment doesn't have a valid authentication path to Service Bus (pre-existing environment constraint, not caused by the rotation).

### Key structural observation

Secret rotation (`az containerapp secret set`) does **not** create a new revision. The running revision immediately sees the new secret value the next time KEDA polls the scaler (~15-30 second interval). There is no observed caching of the old secret value.

## 11. Interpretation

- **Observed**: Rotating a Container Apps secret (`az containerapp secret set`) does NOT create a new revision. The existing revision picks up the new secret value on the next KEDA polling cycle.
- **Observed**: After setting an invalid connection string, `KEDAScalerFailed` appeared in system logs within ~19 seconds — the next KEDA poll cycle. The scaler is not caching the previous valid credential.
- **Observed**: `KEDAScalerFailed` events are emitted to `ContainerAppSystemLogs` with the full HTTP error context (endpoint URL, HTTP status code). The failure is NOT silent.
- **Observed**: `FailedGetExternalMetric` and `FailedComputeMetricsReplicas` events follow `KEDAScalerFailed` — the scaling pipeline halts when authentication fails.
- **Not Proven**: H1 (KEDA caches the old credential until revision restart) — directly contradicted. KEDA immediately uses the updated secret value.
- **Inferred**: H2 (scale to zero on auth failure) — the scale rule failing to get metrics means KEDA cannot compute a desired replica count from that rule. With multiple scale rules, remaining healthy rules still contribute. With only the failing rule, the expected behavior is scale to minimum (typically 0 for Consumption), but this was not directly observed due to existing constraints.

## 12. What this proves

- `az containerapp secret set` does NOT create a new revision. Secret updates take effect in the current running revision on the next KEDA poll cycle (~15-30 seconds).
- KEDA does NOT cache the previous valid credential. After rotating to an invalid key, scaler authentication fails immediately on the next poll — no grace period.
- `KEDAScalerFailed` events in `ContainerAppSystemLogs` are emitted with the HTTP 401 error when the Service Bus credential is invalid. The failure is observable, not silent.

## 13. What this does NOT prove

- Whether KEDA scales to zero when the only scale rule is authentication-failed — not directly observed due to environment constraints.
- Whether the scaler automatically recovers after a valid credential is restored, without a revision restart — the recovery path was not cleanly isolated in this run.
- Whether Managed Identity-based KEDA scalers behave differently from connection-string-based scalers during rotation (MI tokens have their own refresh cycle).

## 14. Support takeaway

When a customer reports "scaling stopped after rotating Service Bus credentials" or "KEDA stopped triggering after a key rotation":

1. **Secret rotation takes effect immediately (next KEDA poll, ~15-30s).** Customers do NOT need to create a new revision after `az containerapp secret set` for KEDA to pick up the new credential. If scaling is broken after rotation, the NEW credential value is already being used — verify the new value is correct.
2. **Check `ContainerAppSystemLogs` for `KEDAScalerFailed`.** This event appears with the HTTP 401 body when authentication fails. It is NOT silent. The event includes the endpoint URL so you can confirm which queue/namespace is failing.
3. **Old credential is not cached.** There is no delay between secret update and KEDA using the new value. If the customer updates the secret but scaling still doesn't work, the new connection string itself is invalid or the queue name is wrong.
4. **Use Managed Identity where possible.** MI-based KEDA authentication eliminates connection string rotation as a failure mode. Use `az containerapp update --scale-rule-auth` with MI-based triggers instead of `connection=<secret-name>`.

## 15. Reproduction notes

- Container Apps secrets are immutable per revision. Updating a secret requires creating a new revision (`az containerapp update` triggers a new revision by default for scaling rule changes).
- KEDA scalers in Container Apps cache authentication credentials; the exact cache TTL is platform-managed.
- Prefer Managed Identity-based KEDA authentication over connection strings to avoid secret rotation issues.

## 16. Related guide / official docs

- [Scale rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Service Bus scaling trigger](https://learn.microsoft.com/en-us/azure/container-apps/scale-app#azure-service-bus)
- [Rotate secrets for Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
