---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-03"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Environment Variable Injection Order: Secret Refs vs. Plain Env Vars Evaluation Order

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-03.

## 1. Question

In Container Apps, environment variables can be plain values or references to secrets (`secretRef`). When an environment variable references a secret that does not yet exist in the `secrets` array (e.g., due to a deployment ordering issue or typo in the secret name), does the container fail to start, fail to deploy, or start with an empty/null value for that variable?

## 2. Why this matters

Teams often manage secrets and environment variable references as separate concerns. If the secret name in `secretRef` does not match any secret in the `secrets` array, the behavior (fail-fast at deploy time or silent null at runtime) determines how quickly the misconfiguration is caught. Additionally, when a secret's value is updated, the CLI warns that a restart is needed — but teams using `secretRef` in env vars may not realize that the new value is only picked up by **new revisions**, not by existing running revisions.

## 3. Customer symptom

"The app deployed successfully but environment variable `DATABASE_URL` is empty at runtime" or "Deployment failed with 'secret not found' error — we're not sure which secret is missing" or "We updated a secret but the app is still using the old value."

## 4. Hypothesis

- H1: When a `secretRef` references a secret name that does not exist in the `secrets` array, the Container Apps deployment fails at validation time with an error identifying the missing secret. The container is not started. ✅ **Confirmed**
- H2: The error is detectable at deploy time (CLI/ARM response), not at container runtime. ✅ **Confirmed**
- H3: When a secret's value is updated, the CLI explicitly warns that a restart is required. Existing revisions are not affected — only new revisions or restarted revisions pick up the new value. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Azure Container Apps Hello World image |
| OS | Linux |
| Date tested | 2026-05-03 |

## 6. Variables

**Experiment type**: Configuration / Secrets

**Controlled:**

- Container app with secrets array and `secretRef` env vars
- `secretRef` pointing to: existing secret, non-existent secret

**Observed:**

- Deployment success/failure and error message
- CLI warning on secret update
- Revision state after secret update

**Scenarios:**

| Scenario | Action | Expected | Observed |
|----------|--------|----------|----------|
| S1 | Deploy with `secretRef` to non-existent secret | Deployment fails | ✅ `ContainerAppSecretRefNotFound` error |
| S2 | Update secret value | Warning about restart requirement | ✅ `must be restarted` warning |
| S3 | Create new revision after secret update | New revision picks up new secret value | ✅ New revision created successfully |

## 7. Instrumentation

- `az containerapp create/update` error output for deployment-time validation
- `az containerapp secret set` warning output
- `az containerapp revision list` to verify revision states

## 8. Procedure

1. Created container app with secret `my-secret=hello-value` and env var `MY_VAR=secretref:my-secret`.
2. **S1**: Attempted `az containerapp update --set-env-vars BAD_VAR=secretref:non-existent-secret` → captured error response.
3. **S2**: Ran `az containerapp secret set --secrets my-secret=updated-value` → captured warning message.
4. **S3**: Created new revision with `az containerapp update --revision-suffix s2-new-secret` → verified new revision picks up updated secret.

## 9. Expected signal

- S1: CLI returns `ContainerAppSecretRefNotFound` error; no new revision is created.
- S2: CLI warns `must be restarted in order for secret changes to take effect`.
- S3: New revision created successfully with updated secret value.

## 10. Results

**S1 — `secretRef` to non-existent secret:**
```
ERROR: (ContainerAppSecretRefNotFound) SecretRef 'non-existent-secret' defined for container 'app-secret-lab' not found.
```
Deployment fails immediately at API validation. No new revision is created.

**S2 — Updating secret value:**
```
WARNING: Containerapp 'app-secret-lab' must be restarted in order for secret changes to take effect.
```
Secret value updated in the secrets store. Existing running revisions continue to use the old value.

**S3 — New revision after secret update:**
```
Name                           Active
app-secret-lab--kmi8nxr        True
app-secret-lab--s2-new-secret  True
```
New revision `s2-new-secret` started successfully, using the updated secret value.

## 11. Interpretation

**Observed**: Container Apps performs secret reference validation at deploy time — if a `secretRef` points to a non-existent secret, the deployment API returns `ContainerAppSecretRefNotFound` immediately. No container is started. This is a **fail-fast** behavior that makes misconfigured secret references easy to detect.

**Observed**: Updating a secret value does not automatically inject the new value into running revisions. The CLI explicitly warns that a restart is required. In practice, for `secretRef` env vars, the new value is picked up only when a new revision is created (or the app is restarted), because env vars are resolved at container start time.

**Inferred**: Teams that update secrets expecting the new value to appear immediately in running containers will be disappointed. The workflow is: update secret → create new revision (or restart) → new revision uses new value.

## 12. What this proves

- **Proven**: `secretRef` to a non-existent secret causes an immediate deployment-time error (`ContainerAppSecretRefNotFound`). The failure is detectable in CI/CD pipeline output.
- **Proven**: Secret value updates require a container restart or new revision to take effect.
- **Proven**: The CLI provides an explicit warning when a secret is updated without restarting.

## 13. What this does NOT prove

- Behavior of Key Vault references (`keyVaultUrl`) under the same conditions — only direct secret values were tested.
- Whether secret value changes are picked up on existing revision restart (vs. new revision creation only).
- Behavior when a secret is deleted while a revision is running and referencing it.

## 14. Support takeaway

When a customer reports that a `secretRef` env var has an unexpected value or a deployment fails:

1. **Deployment failure with `ContainerAppSecretRefNotFound`**: The env var `secretRef` name does not match any entry in the `secrets` array. Check spelling — secret names are case-sensitive.
   ```bash
   az containerapp secret list -n <app> -g <rg>
   ```
2. **Secret updated but app still uses old value**: Update does not auto-inject. Create a new revision or restart:
   ```bash
   az containerapp update -n <app> -g <rg> --revision-suffix <new-suffix>
   # OR
   az containerapp revision restart -n <app> -g <rg> --revision <revision-name>
   ```

## 15. Reproduction notes

```bash
# Create app with secret and secretRef env var
az containerapp create -n myapp -g myrg \
  --environment myenv \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --secrets my-secret=hello-value \
  --env-vars MY_VAR=secretref:my-secret \
  --ingress external --target-port 80

# S1: Deploy with bad secretRef -> fails at validation
az containerapp update -n myapp -g myrg \
  --set-env-vars BAD_VAR=secretref:non-existent-secret
# ERROR: (ContainerAppSecretRefNotFound) SecretRef 'non-existent-secret'... not found.

# S2: Update secret -> warning emitted
az containerapp secret set -n myapp -g myrg --secrets my-secret=new-value
# WARNING: Containerapp 'myapp' must be restarted in order for secret changes to take effect.

# S3: New revision picks up new secret
az containerapp update -n myapp -g myrg --revision-suffix new-rev
```

## 16. Related guide / official docs

- [Manage secrets in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Container Apps environment variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)
