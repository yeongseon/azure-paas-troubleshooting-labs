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

# Container Registry Authentication Expiry

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When the credential used to pull a container image from a private registry expires (e.g., admin credentials rotated, service principal secret expired, or managed identity RBAC removed), what happens to a running App Service container? Does the app continue running, fail on the next restart, or fail immediately?

## 2. Why this matters

Container deployments using private registries (Azure Container Registry or Docker Hub private repos) introduce an authentication dependency that is not present in code deployments. When registry credentials expire or are revoked, the impact is delayed and non-obvious: the currently running container continues working, but any restart (manual, platform, or deployment) will fail to pull the image.

Support cases arise when:
- A customer rotates ACR admin credentials but doesn't update the App Service settings
- A service principal used for ACR pull has its secret expire
- An ACR geo-replication outage prevents pull in the deployment region

## 3. Customer symptom

- "The app was working fine yesterday. Today after we restarted it, it's stuck on 'Image pull failed'."
- "We rotated our ACR password and now deployments fail."
- "The app runs but we can't deploy a new version — ACR authentication keeps failing."
- "Application Error is showing but the image hasn't changed."

## 4. Hypothesis

**H1 — Running container is unaffected**: A running container is not evicted when registry credentials are revoked. The image is already pulled and the container is executing from a local layer cache.

**H2 — Restart fails**: When the container is restarted (for any reason), the platform attempts a fresh pull. With invalid credentials, the pull fails and the app enters an error loop.

**H3 — Managed identity is more resilient**: Using managed identity for ACR pull (via `--assign-identity` and ACR role) is more resilient than admin credentials because the token is refreshed automatically. However, if the role assignment is removed, the next pull fails.

**H4 — Error visibility**: Pull failures appear in the App Service activity log and container event log, but not necessarily in Application Insights.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Linux |
| Region | Korea Central |
| Runtime | Custom container (Python Flask on mcr.microsoft.com/appsvc/python) |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config + Failure Injection

**Controlled:**

- Registry credential type (admin password, service principal, managed identity)
- Credential revocation timing (before restart vs. during deployment)
- App Service restart trigger (manual, `az webapp restart`, ARM config change)

**Observed:**

- App behavior while running with revoked credentials
- Container pull log entries on restart
- Time from restart trigger to error state
- Activity Log entries for failed pull

## 7. Instrumentation

- `/health` endpoint: running app remains accessible until restart
- App Service container logs: `az webapp log tail`
- Activity Log: `Microsoft.Web/sites/write` and pull failure events
- Azure Monitor alert: configure an alert on `AppServiceHTTPLogs` for 5xx during the test

**Key query:**

```kusto
AppServiceConsoleLogs
| where ResultDescription contains "pull" or ResultDescription contains "registry"
| project TimeGenerated, ResultDescription
| order by TimeGenerated desc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
# Create ACR
az acr create --name acrregauthtest --resource-group rg-regauth --sku Basic --admin-enabled true

# Build and push a simple test image
docker build -t acrregauthtest.azurecr.io/testapp:v1 .
az acr login --name acrregauthtest
docker push acrregauthtest.azurecr.io/testapp:v1

# Create App Service with ACR credentials
az webapp create --name app-regauth --resource-group rg-regauth --plan plan-regauth \
  --deployment-container-image-name acrregauthtest.azurecr.io/testapp:v1
```

### 8.2 Scenarios

**S1 — Running app with rotated credentials**: Verify app is running. Rotate ACR admin password. Check app `/health`. Confirm still running. Record how long.

**S2 — Restart with invalid credentials**: After rotating credentials, trigger `az webapp restart`. Observe pull failure. Check how App Service reports the error.

**S3 — Recovery**: Update App Service with new ACR credentials. Trigger restart. Measure time to recovery.

**S4 — Managed identity pull**: Configure managed identity with `AcrPull` role. Verify pull works. Remove role assignment. Trigger restart. Observe failure mode.

## 9. Expected signal

- **S1**: App continues running — no impact on running container.
- **S2**: Restart causes container pull failure within 60 seconds. App enters error state.
- **S3**: After credential update, next restart succeeds.
- **S4**: Role removal causes same failure as credential rotation — pull fails on restart.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- ACR pull behavior may differ with geo-replication enabled (pull from nearest replica vs. home registry).
- Docker Hub private registry has different error codes than ACR.
- Managed identity pull is only available on Standard tier and above (requires VNet or non-Basic SKU).

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Running container unaffected by credential rotation | **Strongly Suggested** (containers run from local image) |
| Restart fails with revoked credentials | **Strongly Suggested** |
| Managed identity more resilient than static credentials | **Inferred** |

## 14. Related experiments

- [Registry Pull Failures (Container Apps)](../zip-vs-container/overview.md) — same scenario on Container Apps
- [Zip vs Container Deployment](../zip-vs-container/overview.md) — deployment method comparison

## 15. References

- [Authenticate to ACR from App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container#use-an-image-from-a-private-registry)
- [Use managed identity for ACR pull](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container#use-managed-identity-to-pull-image-from-azure-container-registry)

## 16. Support takeaway

When a customer reports "Application Error" after a container was previously running:

1. Check whether any credential rotation occurred recently — ACR admin passwords, service principal secrets.
2. Verify: the app runs fine UNTIL a restart. The container image is locally cached; credential issues only matter on pull (restart/deploy).
3. Check App Service container logs for `unauthorized` or `pull access denied` errors.
4. For long-term reliability, recommend managed identity over admin credentials: tokens auto-refresh and there is no expiry concern. Requires `AcrPull` role on the ACR resource.
5. Distinguish from image-not-found errors (different error message) — both cause similar symptoms but different root causes.
