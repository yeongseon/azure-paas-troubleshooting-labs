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

# Secret Reference Provisioning Failure: Wrong secretRef Name

!!! info "Status: Planned"

## 1. Question

Container Apps uses secrets defined at the container app level and referenced in environment variables via `secretRef`. When the `secretRef` name in an environment variable definition does not match any defined secret name, what happens during revision provisioning — does the revision fail, and what is the error message?

## 2. Why this matters

Secret name mismatches are a common infrastructure-as-code mistake when secrets are renamed or when templates are copied between environments. A mismatched `secretRef` causes the revision to fail to provision, but the error may not be immediately visible in the ARM deployment result (the ARM deployment succeeds; the revision provisioning fails asynchronously). Teams may believe their deployment succeeded and only discover the failure when they notice traffic not shifting to the new revision.

## 3. Customer symptom

"Deployment succeeded but the new revision is stuck in 'Provisioning' state" or "Revision shows 'Failed' status but the ARM deployment returned success" or "The new container version was deployed but requests are still going to the old revision."

## 4. Hypothesis

- H1: When `secretRef: nonexistent-secret` is used in an environment variable and no secret named `nonexistent-secret` exists in the container app's secret store, the revision fails to provision with a provisioning error referencing the missing secret name.
- H2: The ARM deployment for the container app update returns HTTP 200 (success) because the deployment is accepted; the revision provisioning error is an asynchronous event that surfaces in the revision status (`az containerapp revision show`), not in the ARM deployment result.
- H3: The error is visible in the container app **Revision management** blade under the failed revision's details, and in the activity log for the container app resource.

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

**Experiment type**: Deployment / Configuration

**Controlled:**

- Container app with one defined secret (`db-password`)
- New revision with environment variable referencing `secretRef: nonexistent-secret`

**Observed:**

- ARM deployment result
- Revision provisioning status
- Error message content and location

**Scenarios:**

- S1: Correct `secretRef: db-password` → revision provisions successfully
- S2: Wrong `secretRef: nonexistent-secret` → revision fails to provision
- S3: Fix `secretRef` name → new revision provisions successfully; traffic shifts

## 7. Instrumentation

- `az containerapp revision list --name <app> --resource-group <rg>` for revision status
- `az containerapp revision show --revision <rev-name>` for error details
- Azure Monitor `ContainerAppSystemLogs` for provisioning events

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy container app with secret `db-password` and correct `secretRef: db-password` → verify success.
2. S2: Update the container app with a new revision using `secretRef: nonexistent-secret`; observe ARM deployment result (expect 200); then check revision status.
3. Capture error message from revision details.
4. S3: Correct the `secretRef` to `db-password`; deploy; verify new revision provisions and receives traffic.

## 9. Expected signal

- S1: Revision provisions successfully; replicas start; traffic routes to new revision.
- S2: ARM deployment returns 200; revision status shows `Failed` or `Provisioning` with error; replicas never start; old revision continues serving.
- S3: Corrected revision provisions successfully.

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

- Secret names in Container Apps are lowercase alphanumeric and hyphens. Case-sensitive matching.
- Secrets are defined at the container app level (`properties.configuration.secrets`) and referenced by `secretRef` in `properties.template.containers[].env[].secretRef`.
- The ARM deployment succeeding does not guarantee revision provisioning success — always check revision status separately.

## 16. Related guide / official docs

- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Container Apps revision management](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
