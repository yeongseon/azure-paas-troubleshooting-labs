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

# Secret Reference Provisioning Failure: Wrong secretRef Name

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Container Apps uses secrets defined at the container app level and referenced in environment variables via `secretRef`. When the `secretRef` name in an environment variable definition does not match any defined secret name, what happens during revision provisioning — does the revision fail, and what is the error message?

## 2. Why this matters

Secret name mismatches are a common infrastructure-as-code mistake when secrets are renamed or when templates are copied between environments. A mismatched `secretRef` causes the revision to fail to provision, but the error may not be immediately visible in the ARM deployment result (the ARM deployment succeeds; the revision provisioning fails asynchronously). Teams may believe their deployment succeeded and only discover the failure when they notice traffic not shifting to the new revision.

## 3. Customer symptom

"Deployment succeeded but the new revision is stuck in 'Provisioning' state" or "Revision shows 'Failed' status but the ARM deployment returned success" or "The new container version was deployed but requests are still going to the old revision."

## 4. Hypothesis

- H1: Referencing a non-existent secret name in an environment variable `secretRef` produces a synchronous error during `az containerapp update`. The CLI returns an error before the revision is committed.
- H2: The error message explicitly names the missing `secretRef` value, making it immediately identifiable.
- H3: The existing active revision continues serving traffic when a new revision fails due to a bad `secretRef`.
- H4: No new revision record is created in `az containerapp revision list` when the update fails.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Reliability

**Controlled:**

- Container App: `aca-diag-batch` with active revision serving traffic
- No secrets defined at the app level

**Observed:**

- CLI error output and HTTP status when referencing non-existent secret
- App HTTP response during failed update
- Revision list state after failure

**Scenarios:**

- S1: Valid env var (no secretRef) → success (baseline)
- S2: `secretRef` pointing to non-existent secret name → observe error and traffic behavior

## 7. Instrumentation

- `az containerapp update --set-env-vars "VAR=secretref:<name>"` — trigger bad secretRef
- `curl` to app URL — verify traffic during failure
- `az containerapp revision list` — count and state of revisions after failure

## 8. Procedure

1. Baseline: App running with active revision, HTTP 200.
2. Attempt: `az containerapp update --set-env-vars "NONEXISTENT_SECRET=secretref:this-secret-does-not-exist"`.
3. Observe CLI error output.
4. Send HTTP request to app — verify existing revision still serves traffic.
5. Check `az containerapp revision list` — verify no new revision was created.

## 9. Expected signal

- S2: CLI returns error mentioning `SecretRef` not found; no new revision created; existing revision continues at HTTP 200.

## 10. Results

### S2 — Non-existent secretRef

```bash
$ az containerapp update -n aca-diag-batch -g rg-lab-aca-batch \
  --set-env-vars "NONEXISTENT_SECRET=secretref:this-secret-does-not-exist"
```

```
WARNING: The behavior of this command has been altered by the following extension: containerapp
ERROR: (ContainerAppSecretRefNotFound) SecretRef 'this-secret-does-not-exist' defined
for container 'aca-diag-batch' not found.
```

### App behavior during failure

```
HTTP after failed update: 200
# Previous revision continued serving traffic uninterrupted
```

### Revision state after failure

```
Name                     Active    Traffic    Healthy
-----------------------  --------  ---------  ---------
aca-diag-batch--0000001  True      70         Healthy
aca-diag-batch--0000002  True       0         Healthy
aca-diag-batch--0000003  True       0         Healthy
aca-diag-batch--0000004  True     100         Healthy
```

No new revision was created by the failed update.

## 11. Interpretation

- **Observed**: A `secretRef` pointing to a non-existent secret name produces a synchronous `ContainerAppSecretRefNotFound` error during `az containerapp update`. H1 is confirmed.
- **Observed**: The error message explicitly includes the missing secret name (`'this-secret-does-not-exist'`). H2 is confirmed.
- **Observed**: Existing active revisions continued serving HTTP 200. H3 is confirmed.
- **Observed**: No new revision was added to `az containerapp revision list`. H4 is confirmed.
- **Inferred**: The validation occurs at the ARM API layer (not asynchronously during provisioning). The error code `ContainerAppSecretRefNotFound` is a client-side validation error, not a backend provisioning failure. This means the ARM deployment also fails synchronously — no asynchronous provisioning state to wait for.

## 12. What this proves

- A missing `secretRef` is caught synchronously at the ARM API layer — the error is returned immediately by `az containerapp update`. **Observed**.
- The error code is `ContainerAppSecretRefNotFound` with the exact missing secret name in the message. **Observed**.
- Existing revisions continue serving traffic when a new revision update fails due to missing `secretRef`. **Observed**.
- No partial revision record is created on failure. **Observed**.

## 13. What this does NOT prove

- Behavior when using ARM templates or Bicep directly (vs. CLI) was not tested. It is likely that ARM template deployments also fail synchronously with the same error, but this was not confirmed.
- What happens when the secret exists but has an incorrect value (wrong Key Vault secret version, invalid connection string, etc.) — the revision would deploy successfully but the application would fail at runtime.
- Behavior when a Key Vault-referenced secret becomes unavailable after the revision is already running was not tested.

## 14. Support takeaway

When a customer reports "deployment succeeded but new revision is not receiving traffic":

1. Check if the `az containerapp update` / ARM deployment actually returned success or an error. A `ContainerAppSecretRefNotFound` error is synchronous and the deployment fails immediately.
2. List all secrets defined at the app level: `az containerapp secret list -n <app> -g <rg>`. Compare against `secretRef` values in env var definitions.
3. The error message includes the exact missing secret name — search for it in the ARM template or Bicep definition.
4. To fix: either (a) add the missing secret to the Container App (`az containerapp secret set`), then retry the update, or (b) remove the incorrect `secretRef` from the env var definition.
5. After fixing, verify with `az containerapp revision list` that a new revision was created and is healthy.

## 15. Reproduction notes

```bash
RG="rg-lab-aca-batch"
APP="aca-diag-batch"

# Create the bad secretRef (will fail)
az containerapp update -n $APP -g $RG \
  --set-env-vars "MY_SECRET=secretref:my-nonexistent-secret"
# Expected: ERROR: (ContainerAppSecretRefNotFound) SecretRef 'my-nonexistent-secret' ...

# Fix: add the secret first, then retry
az containerapp secret set -n $APP -g $RG \
  --secrets "my-nonexistent-secret=my-actual-value"

az containerapp update -n $APP -g $RG \
  --set-env-vars "MY_SECRET=secretref:my-nonexistent-secret"
# Expected: Success — new revision created
```

- Secret names in Container Apps are case-sensitive and must be lowercase alphanumeric with hyphens only.
- Key Vault-referenced secrets use a different format: `az containerapp secret set --secrets "secretname=keyvaultref:<uri>,<identity>"`.

## 16. Related guide / official docs

- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Use Key Vault secrets in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets#reference-secret-from-key-vault)
- [Container Apps environment variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)
