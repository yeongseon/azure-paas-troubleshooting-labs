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

# Bicep Property Drift: Container App Deployed with Stale Properties After Template Change

!!! info "Status: Planned"

## 1. Question

When a Container Apps resource is deployed via Bicep and a template property is changed (e.g., CPU/memory, environment variable, ingress settings), does re-deploying the Bicep template always converge to the desired state? Or are there properties that silently persist from the previous deployment (drift), causing the running container to differ from what the template declares?

## 2. Why this matters

Infrastructure-as-Code relies on idempotency: re-deploying a template should always produce the state declared in the template. In practice, some Azure resource properties are not updated on re-deployment if the Bicep template omits them (they are treated as "not specified" rather than "remove this"). This causes configuration drift where the live resource has properties not reflected in source control, breaking the principle of a single source of truth and causing hard-to-debug differences between environments.

## 3. Customer symptom

"We updated the Bicep template but the running container still has the old environment variable" or "The CPU limit we removed from the template is still in effect on the running app" or "Redeploying the same template gives different results in different environments."

## 4. Hypothesis

- H1: Container Apps properties that are omitted from a Bicep template are not reset to defaults on re-deployment — they retain their previously set values. This is the expected ARM behavior for non-specified properties (partial update semantics).
- H2: To remove a property (e.g., an environment variable), it must be explicitly absent from the `env` array in the template, not just omitted. If the `env` array is omitted entirely, the existing environment variables are preserved.
- H3: Secret references in the `env` array that reference secrets not present in the `secrets` array cause a deployment validation error (not a silent drift), making this class of misconfiguration detectable at deploy time.
- H4: Using `az containerapp update` (imperative) and Bicep (declarative) on the same resource simultaneously causes drift, as imperative changes are overwritten on the next Bicep deployment but not immediately.

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

**Experiment type**: Infrastructure / IaC

**Controlled:**

- Container app deployed via Bicep with known initial state
- Bicep template modified to remove/change specific properties
- Re-deployment via `az deployment group create`

**Observed:**

- Live resource properties after re-deployment (`az containerapp show`)
- Diff between template-declared state and live state

**Scenarios:**

- S1: Remove env var from template array → verify env var removed from running container
- S2: Omit env array entirely → verify existing env vars are preserved (not removed)
- S3: Imperative `az containerapp update` followed by Bicep redeploy → verify imperative change is overwritten

## 7. Instrumentation

- `az containerapp show --name <app> --resource-group <rg>` for live property inspection
- Bicep what-if deployment (`az deployment group what-if`) to preview changes
- Container app revision environment variables via Azure portal

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy container app via Bicep with env vars `VAR_A=value_a` and `VAR_B=value_b`.
2. S1: Remove `VAR_B` from the `env` array in Bicep; redeploy; verify `VAR_B` is gone from the container.
3. S2: Remove the entire `env` array from the Bicep template; redeploy; verify whether `VAR_A` (still declared in the previous deployment) is preserved or removed.
4. S3: Run `az containerapp update --set-env-vars NEW_VAR=new_value`; then redeploy original Bicep (without `NEW_VAR`); verify `NEW_VAR` is absent after Bicep redeploy.

## 9. Expected signal

- S1: `VAR_B` is removed from the running container — explicit removal in template works.
- S2: `VAR_A` is preserved — omitting the `env` array is NOT the same as declaring an empty `env` array.
- S3: `NEW_VAR` is removed after Bicep redeploy — declarative wins over imperative.

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

- Use `az deployment group what-if` before deploying to preview which properties will change.
- To guarantee a clean state, export the full resource definition and diff against the Bicep template.
- Empty array `env: []` vs. omitting `env` are semantically different in ARM — test both.

## 16. Related guide / official docs

- [Bicep Container Apps resource reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps)
- [ARM template idempotency and what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/what-if-operation)
