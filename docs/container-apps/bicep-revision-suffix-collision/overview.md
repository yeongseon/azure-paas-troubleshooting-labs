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

# Bicep Revision Suffix Collision

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When Container Apps revisions are created by Bicep/ARM deployments, what happens when two deployments attempt to create revisions with the same suffix, or when the `revisionSuffix` is not specified and the platform auto-generates one? Can concurrent deployments cause collision errors or silent no-ops?

## 2. Why this matters

Container Apps Bicep deployments in CI/CD pipelines can cause puzzling behaviors around revision creation. Teams using GitOps or automated deployment pipelines frequently encounter:
- Deployments that succeed at the ARM level but don't create a new revision
- `revisionSuffix` collisions causing 409 Conflict errors
- Auto-generated suffixes that change unexpectedly across re-deployments
- Confusion between "deploy same revision" (idempotent ARM) and "create new revision" (image or config change required)

## 3. Customer symptom

- "Our Bicep deployment says it succeeded but the revision didn't change."
- "We're getting a 409 error when deploying — 'revision already exists'."
- "Two parallel pipelines created revisions with the same name."
- "The traffic isn't shifting to the new revision after our deployment."

## 4. Hypothesis

**H1 — Static revisionSuffix causes collision**: If `revisionSuffix` is set to a static value in Bicep (e.g., `"v1"`), re-deploying the same template creates a 409 Conflict if no other property has changed (ARM detects no drift and skips the update) OR returns a conflict if the revision exists with a different config.

**H2 — No-op on identical deployment**: Deploying the same Bicep template twice with no changes results in no new revision — ARM's idempotency model detects no drift and skips the revision creation.

**H3 — Auto-suffix is timestamp-based**: When `revisionSuffix` is omitted, the platform generates a suffix (likely timestamp or random). Concurrent deployments will produce different suffixes and both revisions will be created, with the last one taking traffic.

**H4 — Traffic split config is not revision-aware**: Specifying traffic split percentages in the same Bicep template as a new revision can cause a race between revision creation and traffic assignment.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| IaC | Bicep (ARM API) |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config + IaC

**Controlled:**

- `revisionSuffix` value: static vs. dynamic (timestamp in pipeline)
- Deployment repetition: deploy same template 2× in quick succession
- Concurrent deployments: two pipelines simultaneously
- Traffic configuration: `latestRevision: true` vs. explicit revision reference

**Observed:**

- ARM deployment output: new revision name vs. existing
- Container Apps revision list: revision count, active status
- Traffic split after deployment
- ARM error responses for collisions

## 7. Instrumentation

- `az containerapp revision list` before and after each deployment
- ARM deployment operation status and duration
- Traffic validation: `/health` endpoint response includes revision name

**Revision tracking query:**

```bash
az containerapp revision list \
  --name app-bicep-collision \
  --resource-group rg-bicep-collision \
  --query "[].{name: name, active: properties.active, trafficWeight: properties.trafficWeight}" \
  --output table
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bicep
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'app-bicep-collision'
  location: location
  properties: {
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
      }
    }
    template: {
      revisionSuffix: revisionSuffix  // parameter
      containers: [...]
    }
  }
}
```

### 8.2 Scenarios

**S1 — Static suffix, same template deployed 2×**: Set `revisionSuffix: 'v1'`. Deploy. Deploy again (no changes). Observe whether second deployment creates a new revision or is a no-op.

**S2 — Static suffix, config changed**: Deploy with `revisionSuffix: 'v1'`, env var A=1. Deploy same suffix with A=2. Observe: new revision created or error?

**S3 — Concurrent deployments**: Launch two `az deployment group create` calls simultaneously. Both use auto-generated suffix. Observe: one succeeds, both succeed, or one fails?

**S4 — Traffic split race condition**: Bicep that creates a new revision AND sets traffic weights in the same template. Deploy and observe whether traffic assignment succeeds on first deployment.

## 9. Expected signal

- **S1**: Second deployment is a no-op (ARM detects no drift). No new revision created. ARM reports success.
- **S2**: ARM creates new revision with same suffix on config change, or returns a conflict error.
- **S3**: Both deployments succeed with different auto-generated suffixes.
- **S4**: Traffic assignment races with revision creation — may require retry logic.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- ARM idempotency behavior varies across API versions; test on `2023-05-01` may differ from `2022-03-01`.
- Bicep deterministic compilation may affect ARM what-if results vs. actual deployment behavior.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Identical Bicep deploy is a no-op (no new revision) | **Strongly Suggested** |
| Static suffix collision causes 409 on config change | **Unknown** |
| Concurrent deployments with auto-suffix both succeed | **Inferred** |

## 14. Related experiments

- [Revision Update Downtime](../revision-update-downtime/overview.md) — revision creation and traffic shift
- [Multi-Revision Traffic Split](../multi-revision-traffic-split/overview.md) — traffic weight management
- [Azure Policy Revision Block](../liveness-probe-failures/overview.md) — policy-blocked revision creation

## 15. References

- [Container Apps Bicep reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps)
- [Revision management in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions)

## 16. Support takeaway

For Bicep/ARM deployment issues with Container Apps revisions:

1. If a deployment "succeeds" but no new revision appears, the deployment was likely a no-op — no property changed from the ARM perspective. Add a unique `revisionSuffix` (e.g., `utcNow()` function in Bicep) to force revision creation.
2. `revisionSuffix` must be unique within the Container App's revision history. Using a static value works only for the first deployment; subsequent identical-suffix deployments are no-ops if no other property changed.
3. For CI/CD pipelines, use `revisionSuffix: '${buildId}'` or `utcNow()` to guarantee a new revision on every deployment.
4. Traffic split configuration in the same template as revision creation may require a second deployment pass to stabilize. Consider separating revision creation and traffic assignment into separate ARM operations.
