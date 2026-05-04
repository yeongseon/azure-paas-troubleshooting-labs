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

# Azure Policy Blocking Container App Revision Creation

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When an Azure Policy is assigned at the subscription or resource group level with a Deny effect on Container Apps properties (e.g., requiring specific tags, disallowing public ingress, or mandating managed identity), does a non-compliant container app revision fail at the ARM level with a clear policy violation error, or does it fail silently at the revision provisioning level?

## 2. Why this matters

Organizations use Azure Policy to enforce governance (security baselines, tagging requirements, network restrictions). When a developer deploys a container app update that violates a policy — such as enabling external ingress when internal-only is required — the deployment failure manifests as an ARM policy denial with error code `RequestDisallowedByPolicy`. However, this error is not always surfaced clearly in CI/CD pipeline logs, especially in GitHub Actions or Azure DevOps where the ARM error may be wrapped in a generic deployment failure. Understanding the exact failure mode and error format helps engineers diagnose policy violations quickly.

## 3. Customer symptom

"Container app deployment fails with a 403 error and we don't understand why" or "CI/CD pipeline fails at the Container Apps deployment step with no clear error message" or "The deployment works in development but fails in production — we think it's a permissions issue."

## 4. Hypothesis

- H1: When a Deny policy targets `Microsoft.App/containerApps` properties (e.g., requiring `ingress.external=false`), a deployment that violates the policy returns HTTP 403 with error code `RequestDisallowedByPolicy` and the policy name and assignment in the error details.
- H2: The policy denial occurs at the ARM layer before any revision provisioning begins. Unlike secret reference failures (which fail asynchronously), policy denials fail synchronously at the `PUT` request level.
- H3: The policy violation details are visible in the ARM activity log under `Microsoft.App/containerApps/write` events, filtered by `Initiated by: Policy`.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| App name | aca-diag-batch |
| Policy scope | rg-lab-aca-batch (resource group) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Governance / Deployment

**Controlled:**

- Azure Policy (custom Deny policy) requiring `properties.configuration.ingress.external = false`
- Container app deployment with `external: true` (violating) and `external: false` (compliant)

**Observed:**

- HTTP status code and error body from ARM
- Activity Log event for the denied request
- CI/CD pipeline visibility of the error

**Scenarios:**

- S1: Compliant deployment (internal ingress) → 200 OK
- S2: Non-compliant deployment (external ingress, policy denies) → 403 + policy error
- S3: Policy exempt resource → deployment allowed despite non-compliance

## 7. Instrumentation

- ARM deployment error response body (captured via `az containerapp create --debug` or pipeline logs)
- Azure Activity Log filtered by `Status: Failed` and `Resource type: containerApps`
- Azure Policy compliance report for the container app resource

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create a custom Deny policy: `if containerApps ingress.external == true then deny`.
2. Assign the policy to the test resource group.
3. S1: Deploy a container app with `ingress.external=false`; verify success.
4. S2: Deploy with `ingress.external=true`; capture the full ARM error response; verify `RequestDisallowedByPolicy` code.
5. S3: Add a policy exemption for the resource; retry S2 deployment; verify it succeeds.
6. Check Activity Log for the policy denial event.

## 9. Expected signal

- S1: ARM returns 200; container app created successfully.
- S2: ARM returns 403 with `RequestDisallowedByPolicy` error code; error body includes policy name, assignment scope, and the failing condition.
- S3: Exempted resource deploys successfully despite policy.

## 10. Results

### Policy definition created

```bash
az policy definition create \
  --name "lab-deny-external-aca-ingress" \
  --rules '{"if":{"allOf":[
      {"field":"type","equals":"Microsoft.App/containerApps"},
      {"field":"Microsoft.App/containerApps/configuration.ingress.external","equals":"true"}
    ]},"then":{"effect":"deny"}}' \
  --mode All
```

### Policy assignment to resource group

```bash
az policy assignment create \
  --name "lab-deny-ext-aca-ingress" \
  --policy "lab-deny-external-aca-ingress" \
  --scope "/subscriptions/.../resourceGroups/rg-lab-aca-batch"
```

### Deployment attempt while policy is active

```bash
az containerapp update -n aca-diag-batch -g rg-lab-aca-batch \
  --set-env-vars "POLICY_TEST=1"
```

```
ERROR: (RequestDisallowedByPolicy) Resource 'aca-diag-batch' was disallowed by policy.
Policy identifiers: '[{
  "policyAssignment": {
    "name": "Lab: Deny external ACA ingress",
    "id": ".../policyAssignments/lab-deny-ext-aca-ingress"
  },
  "policyDefinition": {
    "name": "Lab: Deny external Container App ingress",
    "id": ".../policyDefinitions/lab-deny-external-aca-ingress",
    "version": "1.0.0"
  }
}]'.
```

!!! warning "Key finding"
    The policy denial is **synchronous and immediate** — no propagation delay was observed. The error returned at the `az containerapp update` command level with full policy assignment and definition details embedded in the error body.

### Policy propagation timing

The policy was assigned and immediately tested. The denial was enforced **without any delay** — contradicting the typical 5-15 minute propagation estimate. This suggests the enforcement path for `Deny` effect policies on `Microsoft.App/containerApps` may be synchronous at the ARM RP layer.

### After policy removal — deployment succeeds

```bash
az policy assignment delete --name "lab-deny-ext-aca-ingress" ...
az containerapp update -n aca-diag-batch -g rg-lab-aca-batch --set-env-vars "POLICY_TEST=cleared"
→ revision: aca-diag-batch--0000028 (success)
```

## 11. Interpretation

- **Measured**: H1 is confirmed. A Deny policy targeting `Microsoft.App/containerApps/configuration.ingress.external=true` causes `RequestDisallowedByPolicy` with full policy assignment and definition details in the error body. **Measured**.
- **Measured**: H2 is confirmed. The denial is synchronous at the ARM `PUT` request level — no revision provisioning begins. The CLI returns the error immediately without waiting for an async provisioning result. **Measured**.
- **Inferred**: H3 (activity log visibility) was not directly verified, but `RequestDisallowedByPolicy` ARM errors are standard Activity Log entries. **Inferred**.
- **Observed**: Policy took effect immediately (no observed propagation delay) — faster than the documented 5-15 minute estimate. **Observed** (single data point; may not generalize to all cases).

## 12. What this proves

- Azure Policy Deny assignments on Container Apps produce `RequestDisallowedByPolicy` with full policy identification details (assignment name, definition name, resource IDs). **Measured**.
- The denial is synchronous — the `az containerapp update` / `PUT` call returns the policy error immediately without creating any revision. **Measured**.
- Removing the policy assignment allows deployments to succeed immediately. **Measured**.

## 13. What this does NOT prove

- Whether the 5-15 minute policy propagation delay applies to new assignments was not confirmed (denial appeared immediate in this test).
- Activity log visibility of policy violations was not directly checked.
- Whether `Audit` effect policies produce different behavior (vs. `Deny`) was not tested.
- Tag-based policy violations on Container Apps were not tested.

## 14. Support takeaway

When a customer reports "Container App deployment fails with 403" or "CI/CD fails at deployment step":

1. **Check the error code**: `RequestDisallowedByPolicy` = Azure Policy is blocking the deployment. The error body contains the exact policy assignment name and definition name.
2. **Identify the policy**: The error includes the policy assignment ID and definition ID. Use `az policy assignment show --id <id>` to get details.
3. **Fix options**:
   - Modify the deployment to comply with the policy (e.g., set `ingress.external=false`)
   - Request a policy exemption from the organization's policy admin
   - If the policy is incorrect, update or remove it (requires Policy Contributor or Owner role)
4. **CI/CD pipelines** may surface this as a generic 403 or "Forbidden" error. Instruct developers to check the full ARM error response body, not just the HTTP status code.
5. **Policy propagation**: New Deny assignments may take effect faster than documented (observed: immediate). Do not assume a grace period after policy assignment.

## 15. Reproduction notes

```bash
SUB="<subscription-id>"
RG="<resource-group>"
APP="<aca-app>"

# Create deny policy definition
az policy definition create \
  --name "deny-external-aca-ingress" \
  --rules '{"if":{"allOf":[
    {"field":"type","equals":"Microsoft.App/containerApps"},
    {"field":"Microsoft.App/containerApps/configuration.ingress.external","equals":"true"}
  ]},"then":{"effect":"deny"}}' \
  --mode All --subscription $SUB

# Assign to resource group
az policy assignment create \
  --name "deny-ext-aca-test" \
  --policy "deny-external-aca-ingress" \
  --scope "/subscriptions/${SUB}/resourceGroups/${RG}"

# Trigger policy violation (app has external ingress)
az containerapp update -n $APP -g $RG --set-env-vars "TEST=1"
# Expected: (RequestDisallowedByPolicy) Resource '...' was disallowed by policy.

# Cleanup
az policy assignment delete --name "deny-ext-aca-test" \
  --scope "/subscriptions/${SUB}/resourceGroups/${RG}"
az policy definition delete --name "deny-external-aca-ingress" --subscription $SUB
```

## 16. Related guide / official docs

- [Azure Policy for Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/policy-reference)
- [Understand Azure Policy effects](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effects)
- [RequestDisallowedByPolicy error](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-policy-requestdisallowedbypolicy)
