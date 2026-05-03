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

# Environment Variable Injection Order: Secret Refs vs. Plain Env Vars Evaluation Order

!!! info "Status: Planned"

## 1. Question

In Container Apps, environment variables can be plain values or references to secrets (`secretRef`). When an environment variable references a secret that does not yet exist in the `secrets` array (e.g., due to a deployment ordering issue or typo in the secret name), does the container fail to start, fail to deploy, or start with an empty/null value for that variable?

## 2. Why this matters

Teams often manage secrets and environment variable references as separate concerns — secrets are created first, then the container app is deployed referencing them. If the secret name in `secretRef` does not match any secret in the `secrets` array, the behavior (fail-fast at deploy time or silent null at runtime) determines how quickly the misconfiguration is caught. A silent null value can cause application-level authentication failures, missing credentials, or NullPointerExceptions that are far from the root cause.

## 3. Customer symptom

"The app deployed successfully but environment variable `DATABASE_URL` is empty at runtime" or "We renamed a secret but forgot to update the env var ref — the app is silently connecting without credentials" or "Deployment failed with 'secret not found' error — we're not sure which secret is missing."

## 4. Hypothesis

- H1: When a `secretRef` in the `env` array references a secret name that does not exist in the `secrets` array, the Container Apps deployment fails at validation time with an error message identifying the missing secret. The container is not started.
- H2: When a secret exists but its value is an empty string (e.g., a Key Vault reference that failed to resolve), the environment variable is injected with an empty string. The container starts, but the application receives an empty value.
- H3: Plain environment variable values are evaluated at deployment time (static string), while `secretRef` values are resolved at container start time. This means a secret whose value changes after deployment is reflected in new container instances (new revisions) but not in existing running containers.
- H4: The order of entries in the `env` array does not affect evaluation — each variable is resolved independently.

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

**Experiment type**: Configuration / Secrets

**Controlled:**

- Container app with secrets and env vars
- `secretRef` pointing to: existing secret, non-existent secret, empty-value secret

**Observed:**

- Deployment success/failure
- Environment variable value at runtime (via `env` endpoint or logs)
- Error message if deployment fails

**Scenarios:**

- S1: `secretRef` to non-existent secret → deployment fails (H1) or starts with null
- S2: `secretRef` to secret with empty value → container starts with empty env var
- S3: Update secret value → create new revision → verify new revision picks up new value

## 7. Instrumentation

- `az deployment group create` error output for deployment-time validation
- Application endpoint returning `os.environ.get('MY_VAR', 'NOT_SET')` to inspect injected value
- `az containerapp secret list` to verify secret existence and names

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy container app with env var `MY_VAR` referencing secret `my-secret` (which exists with value `hello`); verify `MY_VAR=hello` at runtime.
2. S1: Change `secretRef` to `non-existent-secret`; redeploy; observe whether deployment fails or container starts with null.
3. S2: Create `empty-secret` with value `""`; reference it; verify `MY_VAR` is empty string at runtime.
4. S3: Update `my-secret` value; observe that existing revision still sees old value; create new revision → new revision sees new value.

## 9. Expected signal

- S1: Deployment fails with ARM error: `Secret 'non-existent-secret' not found`; no new revision is created.
- S2: Container starts; `MY_VAR` is empty string (`""`); application receives empty credential.
- S3: Existing revision env var unchanged; new revision reflects updated secret value.

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

- Secret management: `az containerapp secret set --name <app> --resource-group <rg> --secrets my-secret=hello`.
- Env var with secret ref in Bicep: `{ name: 'MY_VAR', secretRef: 'my-secret' }`.
- Verify secret names are case-sensitive and must exactly match the `name` field in the `secrets` array.

## 16. Related guide / official docs

- [Manage secrets in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Container Apps environment variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)
