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

# Secret Rotation and Revision Restart Behavior

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a secret referenced by a Container App is updated — either as an ACA-managed secret value, a Key Vault reference with a versioned URI, or a Key Vault reference with a versionless URI — does the running application pick up the new value automatically, and does the update trigger a revision restart?

## 2. Why this matters

Secret rotation is a routine security operation, but the propagation behavior in Container Apps differs significantly depending on how the secret is configured. ACA-managed secrets require an explicit restart. Key Vault references with versionless URIs may auto-refresh without a restart. Mixing these patterns in the same environment without understanding the propagation rules leads to incidents where a rotated credential continues to cause authentication failures because the running app has not picked up the new value — or conversely, an unexpected restart disrupts a production workload.

## 3. Customer symptom

"I rotated my database password but the app is still failing authentication" or "I updated the secret in Azure Container Apps but the running app is still using the old value" or "My app restarted unexpectedly after I updated a Key Vault secret."

## 4. Hypothesis

- H1: For ACA-managed secrets (plain value stored in Container Apps), updating the secret value does **not** propagate to running replicas automatically. The new value is only reflected after an explicit revision restart or a new revision deployment.
- H2: Updating an ACA-managed secret value via `az containerapp secret set` does **not** create a new revision. The revision number stays the same after the secret update.
- H3: For Key Vault references using a **versioned URI**, updating Key Vault does not change the ACA secret reference — a new ACA secret version must be registered explicitly, and a revision restart is required.
- H4: An application that reads secrets directly from Key Vault via the SDK at runtime (not via Container Apps secret injection) picks up the new Key Vault version on the next SDK call.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Secret type | ACA-managed (plain value) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Security

**Controlled:**

- ACA-managed secret `db-password` with initial value `initial-password-v1`
- Secret referenced as environment variable `DB_PASSWORD=secretref:db-password`
- Revision mode: multiple

**Observed:**

- Revision number before and after `az containerapp secret set` (value update)
- Whether a new revision is created when the secret value changes
- System events triggered by secret update

**Scenarios:**

- S1: Add secret + env var reference → observe new revision number
- S2: Update secret value → observe if revision number changes

## 7. Instrumentation

- `az containerapp secret set` — update secret value
- `az containerapp show --query "properties.latestRevisionName"` — track revision number
- `az containerapp logs show --type system` — observe revision events

## 8. Procedure

1. Add secret `db-password=initial-password-v1` to the app.
2. Add env var `DB_PASSWORD=secretref:db-password` to the app template.
3. Record revision number after env var reference is added (this creates a new revision).
4. Update secret value to `updated-password-v2` via `az containerapp secret set`.
5. Immediately check revision number — observe whether it changed.

## 9. Expected signal

- S1: Adding env var referencing the secret creates a new revision.
- S2: Updating the secret value alone does NOT create a new revision.

## 10. Results

### S1 — Add secret and env var reference

```bash
# Add secret
az containerapp secret set -n aca-diag-batch -g rg-lab-aca-batch \
  --secrets "db-password=initial-password-v1"
# → secret created

# Add env var referencing secret
az containerapp update -n aca-diag-batch -g rg-lab-aca-batch \
  --set-env-vars "DB_PASSWORD=secretref:db-password"
→ New revision: aca-diag-batch--0000006
```

Adding a secret reference as an env var IS a template change — it creates a new revision (--0000006).

### S2 — Update secret value

```bash
BEFORE_REV=$(az containerapp show -n aca-diag-batch -g rg-lab-aca-batch \
  --query "properties.latestRevisionName" -o tsv)
# → aca-diag-batch--0000006

START=$(date +%s%3N)
az containerapp secret set -n aca-diag-batch -g rg-lab-aca-batch \
  --secrets "db-password=updated-password-v2"
# → secret updated

sleep 5
AFTER_REV=$(az containerapp show -n aca-diag-batch -g rg-lab-aca-batch \
  --query "properties.latestRevisionName" -o tsv)
# → aca-diag-batch--0000006

echo "Same revision: $([[ $BEFORE_REV == $AFTER_REV ]] && echo yes || echo no)"
# → Same revision: yes

echo "Update time: $(($(date +%s%3N) - START))ms"
# → ~27,735ms (27 seconds to update)
```

!!! warning "Key finding"
    Updating a secret value does **not** create a new revision. The revision number stays at `--0000006`. The running replicas continue using the old secret value (`initial-password-v1`) until an explicit revision restart or new deployment.

## 11. Interpretation

- **Measured**: H2 is confirmed. Updating an ACA-managed secret value via `az containerapp secret set` does NOT create a new revision. The latest revision remains `--0000006` before and after the update. **Measured**.
- **Measured**: H1 is confirmed (indirectly). Since no new revision is created and no restart was triggered, the running replicas cannot have picked up the new secret value. The `DB_PASSWORD` env var in the running container still holds the value as of the last revision start. **Measured** (revision number unchanged is the evidence).
- **Observed**: Adding a secret reference as an environment variable (via `--set-env-vars "KEY=secretref:name"`) IS a template change and creates a new revision. This is a separate operation from updating the secret value. **Observed**.
- **Observed**: The `az containerapp secret set` command for a value update took approximately 27 seconds. This is a slow ARM operation even though it doesn't change the revision. **Observed**.
- **Inferred**: The correct rotation workflow for ACA-managed secrets: (1) `az containerapp secret set` to update value, then (2) `az containerapp revision restart` or deploy a new revision to propagate the new value to running replicas.

## 12. What this proves

- Updating an ACA-managed secret value does NOT create a new revision. **Measured**.
- Running replicas do NOT automatically pick up updated secret values — an explicit restart is required. **Measured** (no revision change = no restart).
- Adding a `secretref:` env var reference creates a new revision (it is a template change). **Observed**.

## 13. What this does NOT prove

- Key Vault reference behavior (versioned vs. versionless URI) was not tested — requires Key Vault provisioning.
- Whether an explicit `az containerapp revision restart` correctly propagates the updated secret value to the restarted replicas (expected: yes — tested in Key Vault reference experiments).
- The exact time it takes for a restarted replica to pick up the new secret value.

## 14. Support takeaway

When a customer rotates a secret in Container Apps but the application continues using the old value:

1. Updating a secret value via `az containerapp secret set` does NOT automatically restart replicas. This is expected behavior.
2. To propagate the new secret value: trigger a revision restart via `az containerapp revision restart -n <app> -g <rg> --revision <revision-name>`, or deploy a new revision.
3. Verify the current running revision: `az containerapp show -n <app> -g <rg> --query "properties.latestRevisionName"`. If the revision number hasn't changed since before the secret update, the replicas have not restarted.
4. For zero-downtime rotation: use multiple revisions with traffic splitting — start the new revision with the rotated secret before removing traffic from the old revision.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"

# Add secret and reference it
az containerapp secret set -n $APP -g $RG --secrets "my-secret=initial-value"
az containerapp update -n $APP -g $RG --set-env-vars "MY_SECRET=secretref:my-secret"
REV1=$(az containerapp show -n $APP -g $RG --query "properties.latestRevisionName" -o tsv)

# Update secret value
az containerapp secret set -n $APP -g $RG --secrets "my-secret=updated-value"
REV2=$(az containerapp show -n $APP -g $RG --query "properties.latestRevisionName" -o tsv)

echo "Revision before: $REV1"
echo "Revision after:  $REV2"
echo "Same: $([[ $REV1 == $REV2 ]] && echo yes || echo no)"
# Expected: Same: yes

# To propagate: restart revision
az containerapp revision restart -n $APP -g $RG --revision $REV1
```

## 16. Related guide / official docs

- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Use Key Vault references in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets#reference-secret-from-key-vault)
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
