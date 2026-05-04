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

# Bicep Property Drift: Container App Deployed with Stale Properties After Template Change

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a Container Apps resource is deployed via CLI (or Bicep) and a property is changed out-of-band (e.g., CPU/memory changed via portal or CLI), does re-deploying the original configuration always converge to the desired state? What properties are affected by drift and how is it corrected?

## 2. Why this matters

Infrastructure-as-Code relies on idempotency: re-deploying a template should always produce the state declared in the template. In practice, some Azure resource properties are not updated on re-deployment if the template omits them (they are treated as "not specified" rather than "remove this"). This causes configuration drift where the live resource has properties not reflected in source control, breaking the principle of a single source of truth and causing hard-to-debug differences between environments.

## 3. Customer symptom

"We updated the Bicep template but the running container still has the old environment variable" or "The CPU limit we removed from the template is still in effect on the running app" or "Redeploying the same template gives different results in different environments."

## 4. Hypothesis

- H1: Changing CPU/memory out-of-band (via `az containerapp update`) creates a new revision with the new resource values. A subsequent `az containerapp update` with the original values converges back to the original spec. ✅ **Confirmed**
- H2: CPU/memory changes always create new revisions in ACA — they are not applied in-place. ✅ **Confirmed** (revision count increases on each change)
- H3: `ephemeralStorage` changes alongside CPU/memory changes — new revision shows updated ephemeral storage allocation. ✅ **Confirmed** (0.25 CPU → 1Gi ephemeral; 0.5 CPU → 2Gi ephemeral)
- H4: The ACA CLI converges resource properties on re-apply. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| Environment | env-batch-lab (Consumption, Korea Central) |
| App | aca-diag-batch |
| Image | mcr.microsoft.com/azuredocs/containerapps-helloworld:latest |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: IaC / Configuration

**Controlled:**

- Initial state: 0.5 CPU, 1.0Gi memory
- Drifted state: 0.25 CPU, 0.5Gi memory (simulates out-of-band change)
- Re-apply: 0.5 CPU, 1.0Gi memory (convergence)

**Observed:**

- Resource values after drift
- Resource values after re-apply
- `ephemeralStorage` behavior across changes
- New revision creation on each change

**Scenarios:**

- S1: Query baseline resource config
- S2: Apply drift (0.25 CPU, 0.5Gi memory)
- S3: Re-apply original (0.5 CPU, 1.0Gi memory) to converge

## 7. Instrumentation

- `az containerapp show --query properties.template.containers[0].resources` — current resource values
- `az containerapp update --cpu --memory` — apply changes
- Revision count tracked via `az containerapp revision list`

## 8. Procedure

1. Queried baseline: `cpu: 0.5`, `memory: 1Gi`.
2. S2: Applied drift: `az containerapp update --cpu 0.25 --memory 0.5Gi`.
3. Confirmed new revision created with drifted values.
4. S3: Re-applied original: `az containerapp update --cpu 0.5 --memory 1.0Gi`.
5. Confirmed convergence to original values.

## 9. Expected signal

- Drift: `cpu: 0.25`, `memory: 0.5Gi`, `ephemeralStorage: 1Gi`
- Convergence: `cpu: 0.5`, `memory: 1Gi`, `ephemeralStorage: 2Gi`
- Each change creates a new revision (ACA resource model)

## 10. Results

**S1: Baseline:**

```json
{
  "cpu": 0.5,
  "maxReplicas": 3,
  "memory": "1Gi",
  "minReplicas": 0
}
```

**S2: After drift (0.25 CPU, 0.5Gi):**

```json
{
  "cpu": 0.25,
  "ephemeralStorage": "1Gi",
  "memory": "0.5Gi"
}
```

**S3: After re-apply (0.5 CPU, 1.0Gi):**

```json
{
  "cpu": 0.5,
  "ephemeralStorage": "2Gi",
  "memory": "1Gi"
}
```

**Revision history (multiple revisions mode, active only):**

```
aca-diag-batch--ounjrt9  (original)
aca-diag-batch--0000001  (after env var change)
aca-diag-batch--0000002  (after drift)
aca-diag-batch--0000003  (after re-apply)
```

## 11. Interpretation

- **Observed**: CPU/memory changes always trigger a new ACA revision. Unlike App Service (which applies configuration changes in-place), ACA creates a new revision on any template-level change. The old revision is not deleted; it persists in inactive state.
- **Observed**: `ephemeralStorage` is automatically calculated by ACA based on CPU allocation. At 0.25 CPU it allocates 1Gi ephemeral storage; at 0.5 CPU it allocates 2Gi. This value is not directly settable via CLI — it is derived.
- **Observed**: Re-applying the original CPU/memory values via `az containerapp update` converges the resource allocation back to baseline. The IaC idempotency for resource properties works correctly.
- **Observed**: In multiple-revision mode, all revisions (old and new) persist. The active revision (100% traffic) is the latest; others have 0 traffic but are not automatically deleted.
- **Inferred**: True IaC drift (where a template re-deployment does NOT converge because a property is silently ignored) is more likely to occur with complex nested properties (probe configurations, scale rules with multiple conditions) than with simple scalar properties like CPU/memory, which are always applied on update.

## 12. What this proves

- CPU and memory changes on ACA create new revisions — they are not in-place updates.
- `ephemeralStorage` is automatically derived from CPU allocation (not directly configurable via CLI).
- Re-applying original values via CLI converges back to the original spec (no silent drift for scalar properties).
- Multiple revisions accumulate; cleanup requires explicit deactivation/deletion.

## 13. What this does NOT prove

- Drift on complex properties (environment variables, scale rules, probe configurations) was **Not Tested** systematically.
- Bicep/ARM template idempotency for omitted properties was **Not Tested** — the experiment used CLI only.
- Whether ACA silently ignores some properties on re-deployment (the core IaC drift scenario) was **Not Proven** — CLI updates correctly converge for CPU/memory.
- Single-revision mode behavior during updates was **Not Tested** (experiment was in multiple-revision mode).

## 14. Support takeaway

- "The app doesn't have the resources I specified" — in ACA, every CPU/memory change creates a new revision. Check `az containerapp revision list` to confirm the latest active revision has the correct spec.
- "I changed the template but the app didn't update" — in single-revision mode, `az containerapp update` triggers a revision replacement. In multiple-revision mode, a new revision is created but traffic may still go to the old one if traffic split is configured manually.
- `ephemeralStorage` is automatically set by ACA; you cannot set it independently of CPU. It scales with CPU allocation.
- Old revisions accumulate in multiple-revision mode. Deactivate with: `az containerapp revision deactivate -n <app> -g <rg> --revision <revision-name>`.

## 15. Reproduction notes

```bash
# Check current resource allocation
az containerapp show -n <app> -g <rg> \
  --query "properties.template.containers[0].resources" -o json

# Apply drift (out-of-band change)
az containerapp update -n <app> -g <rg> --cpu 0.25 --memory 0.5Gi

# Re-apply original values (convergence)
az containerapp update -n <app> -g <rg> --cpu 0.5 --memory 1.0Gi

# List all revisions including inactive
az containerapp revision list -n <app> -g <rg> \
  --query "[].{name:name,active:properties.active,cpu:properties.template.containers[0].resources.cpu}" \
  -o table

# Deactivate old revisions
az containerapp revision deactivate -n <app> -g <rg> --revision <old-revision-name>
```

## 16. Related guide / official docs

- [Container Apps revisions overview](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Container Apps Bicep deployment](https://learn.microsoft.com/en-us/azure/container-apps/microservices-dapr-azure-resource-manager)
- [az containerapp update](https://learn.microsoft.com/en-us/cli/azure/containerapp#az-containerapp-update)
