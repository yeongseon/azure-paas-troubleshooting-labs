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

# Azure Policy Blocking Container App Revision Creation

!!! info "Status: Planned"

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
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

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

- Azure Policy custom definition for Container Apps: use `Microsoft.App/containerApps` as the resource type; target `properties.configuration.ingress.external` with a `field` condition.
- Policy assignment takes 5-15 minutes to take effect after creation.
- Built-in Container Apps policies: search for "container apps" in Azure Policy definitions in the portal.

## 16. Related guide / official docs

- [Azure Policy for Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/policy-reference)
- [Understand Azure Policy effects](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effects)
- [RequestDisallowedByPolicy error](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-policy-requestdisallowedbypolicy)
