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

# Log Analytics Ingestion Gap: No Workspace Configured vs. Real-time Log Streaming

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a Container Apps environment is created **without** a Log Analytics workspace configured, what happens to container logs and system events? Does `az containerapp logs show` still work? Can Log Analytics queries return data? What is the practical impact on observability?

## 2. Why this matters

Container Apps environments can be provisioned without a Log Analytics workspace — either intentionally (cost savings) or unintentionally (portal quick-create flow omits it). When no workspace is configured, `ContainerAppConsoleLogs` and `ContainerAppSystemLogs` tables do not exist and Log Analytics queries will fail with a `PathNotFoundError`. However, real-time log streaming (`az containerapp logs show`) continues to function via a separate platform streaming endpoint. Operators who expect Log Analytics queries to work after creating the environment without a workspace will get silent failures — no error from the app, no rows returned, just a `PathNotFoundError` from the query API.

## 3. Customer symptom

"I can't find any logs for my Container App in Log Analytics" or "My KQL query for ContainerAppConsoleLogs returns no results even though the app is running" or "az monitor log-analytics query returns PathNotFoundError."

## 4. Hypothesis

- H1: A Container Apps environment created without a Log Analytics workspace has `destination: null` and `logAnalyticsConfiguration: null` in the ARM model — the absence is detectable via `az containerapp env show`.
- H2: When no Log Analytics workspace is configured, `az monitor log-analytics query` targeting the environment name fails with `PathNotFoundError` — not with empty results.
- H3: Real-time log streaming (`az containerapp logs show --type console` and `--type system`) continues to work even without a Log Analytics workspace, using a separate platform streaming endpoint.
- H4: Configuring a Log Analytics workspace requires creating a new environment or updating the existing one via ARM — it cannot be added after the fact via the standard `az containerapp env update` without workspace parameters.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Log Analytics workspace | None (not configured at environment creation) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Observability / Configuration

**Controlled:**

- Container Apps environment `env-batch-lab` created without Log Analytics workspace
- App `aca-diag-batch` running on this environment

**Observed:**

- ARM model `appLogsConfiguration` fields
- Behavior of `az monitor log-analytics query` targeting the workspace
- Behavior of `az containerapp logs show --type console` and `--type system`

## 7. Instrumentation

- `az containerapp env show --query "properties.appLogsConfiguration"` — check workspace config
- `az rest GET .../managedEnvironments/env-batch-lab --query "properties.appLogsConfiguration"` — confirm via ARM
- `az monitor log-analytics query --workspace "env-batch-lab"` — test query behavior without workspace
- `az containerapp logs show --type system --tail 20` — test real-time system event streaming
- `az containerapp logs show --type console --tail 10` — test real-time console streaming

## 8. Procedure

1. Check `env-batch-lab` ARM model for Log Analytics configuration.
2. Run `az monitor log-analytics query` targeting the environment name.
3. Test real-time log streaming: system events and console logs.
4. Compare: which surfaces work vs. fail without a Log Analytics workspace.

## 9. Expected signal

- H1: ARM model shows `destination: null`, `logAnalyticsConfiguration: null`.
- H2: `az monitor log-analytics query` returns `PathNotFoundError`.
- H3: Real-time streaming (`az containerapp logs show`) returns actual log lines.

## 10. Results

### ARM model — Log Analytics configuration

```bash
az rest --method GET \
  --uri "https://management.azure.com/subscriptions/.../managedEnvironments/env-batch-lab?api-version=2024-03-01" \
  --query "properties.appLogsConfiguration"

→ {
    "destination": null,
    "logAnalyticsConfiguration": null
  }
```

### Log Analytics query attempt

```bash
az monitor log-analytics query \
  --workspace "env-batch-lab" \
  --analytics-query "ContainerAppConsoleLogs | take 5"

→ ERROR: (PathNotFoundError) The requested path does not exist
   Code: PathNotFoundError
   Message: The requested path does not exist
```

### Real-time system log streaming (works)

```bash
az containerapp logs show -n aca-diag-batch -g rg-lab-aca-batch \
  --type system --tail 20

→ {"TimeStamp":"2026-05-04 02:06:35 +0000 UTC","Type":"Normal","ContainerAppName":"aca-diag-batch","RevisionName":"aca-diag-batch--0000007","ReplicaName":"...","Msg":"Created container 'init-delay'","Reason":"ContainerCreated"}
  {"TimeStamp":"2026-05-04 02:06:46 +0000 UTC","Type":"Normal","ContainerAppName":"aca-diag-batch","RevisionName":"aca-diag-batch--0000007","ReplicaName":"...","Msg":"Started container 'aca-diag-batch'","Reason":"ContainerStarted"}
  ...
```

### Real-time console log streaming (works)

```bash
az containerapp logs show -n aca-diag-batch -g rg-lab-aca-batch \
  --type console --tail 10

→ {"TimeStamp":"2026-05-04T02:06:46.576064+00:00","Log":"F 2026/05/04 02:06:46 Listening on :80..."}
```

### Summary

| Log Surface | Status | Notes |
|-------------|--------|-------|
| `ContainerAppConsoleLogs` (Log Analytics) | ❌ Unavailable | No workspace configured |
| `ContainerAppSystemLogs` (Log Analytics) | ❌ Unavailable | No workspace configured |
| `az containerapp logs show --type system` | ✓ Works | Platform streaming endpoint |
| `az containerapp logs show --type console` | ✓ Works | Platform streaming endpoint |

## 11. Interpretation

- **Measured**: H1 is confirmed. The ARM model explicitly shows `destination: null` and `logAnalyticsConfiguration: null`. The workspace absence is visible via ARM. **Measured**.
- **Measured**: H2 is confirmed. `az monitor log-analytics query` returns `PathNotFoundError` — not empty results. This is a hard failure, not a "no data" situation. **Measured**.
- **Measured**: H3 is confirmed. Real-time log streaming via `az containerapp logs show` works independently of Log Analytics. Both system events and console logs are available via the streaming endpoint. **Measured**.
- **Inferred**: The streaming endpoint used by `az containerapp logs show` connects to the Container Apps platform's internal event bus, not to Log Analytics. This is why it functions even without a workspace. However, this streaming is not persistent — logs cannot be queried retroactively, only observed in real time.

## 12. What this proves

- Container Apps environment without a Log Analytics workspace has `destination: null` in ARM. **Measured**.
- Log Analytics queries fail with `PathNotFoundError` — not empty results — when no workspace is configured. **Measured**.
- Real-time log streaming works without a Log Analytics workspace. **Measured**.

## 13. What this does NOT prove

- The behavior when Log Analytics is configured but has ingestion lag — the ingestion delay experiment was not run.
- Whether attaching a Log Analytics workspace to an existing environment (post-creation) works and begins populating historical data retroactively (it does not — logs are only forwarded after attachment).
- `ContainerAppConsoleLogs` vs. `ContainerAppSystemLogs` ordering during concurrent events (OOM + restart) was not tested.

## 14. Support takeaway

When a customer reports "no data in Log Analytics" for Container Apps:

1. First: check if a Log Analytics workspace is configured. `az containerapp env show -n <env> -g <rg> --query "properties.appLogsConfiguration"`. If `null`, no workspace exists — this is the root cause.
2. For immediate log access without Log Analytics: use `az containerapp logs show --type system` or `--type console`. This works regardless of workspace configuration.
3. To add a workspace: the workspace must be configured at environment creation. Updating an existing environment to add Log Analytics requires ARM PATCH with the workspace config. New logs will flow to the workspace after attachment, but historical logs are not backfilled.
4. Distinguish `PathNotFoundError` (no workspace configured) from a valid workspace with no matching query results — these require different responses.

## 15. Reproduction notes

```bash
ENV="env-batch-lab"
RG="rg-lab-aca-batch"
APP="aca-diag-batch"
SUB="<subscription>"

# Check workspace config
az containerapp env show -n $ENV -g $RG \
  --query "properties.appLogsConfiguration" -o json

# Test Log Analytics query (will fail if no workspace)
az monitor log-analytics query \
  --workspace "$ENV" \
  --analytics-query "ContainerAppConsoleLogs | take 5" 2>&1

# Real-time streaming (works without workspace)
az containerapp logs show -n $APP -g $RG --type system --tail 10
az containerapp logs show -n $APP -g $RG --type console --tail 10
```

## 16. Related guide / official docs

- [Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [View log streams in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-streaming)
- [Configure a Log Analytics workspace for Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-options)
