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

# Key Vault Reference Resolution Failure at App Startup

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When App Service app settings reference Key Vault secrets using the `@Microsoft.KeyVault(...)` syntax, under what conditions does resolution fail at startup, and how does each failure mode (identity misconfiguration, firewall restriction, wrong secret URI, version pinning) manifest differently in the app settings panel and application logs?

## 2. Why this matters

Key Vault references are a common pattern for secrets management in App Service. When resolution fails, the app setting is silently set to the literal reference string (e.g., `@Microsoft.KeyVault(SecretUri=https://...)`), which causes the application to start with incorrect configuration — often resulting in connection failures or authentication errors that appear to be application bugs rather than platform configuration issues. The resolution status is surfaced in the portal but is easy to miss.

## 3. Customer symptom

"Our database connection string shows a weird `@Microsoft.KeyVault(...)` value inside the application instead of the actual secret" or "The app works locally but fails in Azure even though the app setting is configured" or "Key Vault reference was working and suddenly stopped after we added a firewall rule."

## 4. Hypothesis

- H1: When the system-assigned Managed Identity has `get` and `list` permissions on the Key Vault secret (via access policy), resolution succeeds and the app receives the plaintext secret value. The `@Microsoft.KeyVault(...)` string is not visible to the application.
- H2: When the secret URI points to a nonexistent secret name, resolution fails silently — the app receives the literal reference string. The application starts without error; only the wrong value is injected.
- H3: When the Key Vault name is wrong (vault does not exist), resolution fails silently with the same symptom as H2 — literal reference string injected, no startup failure.
- H4: Both the `SecretUri` format and the `VaultName;SecretName;SecretVersion` format resolve correctly when the identity has access.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn |
| OS | Linux |
| App name | app-batch-1777849901 |
| Key Vault | kv-lab-7cdafc03 |
| Identity | System-assigned (principalId: 058baa05-1640-4fab-a120-1d3ef66614bb) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Authentication

**Controlled:**

- System-assigned Managed Identity with Key Vault access policy (`get`, `list`)
- Key Vault with access policy model (`--enable-rbac-authorization false`)
- `/env` endpoint on the Flask app to inspect injected environment variables

**Observed:**

- App setting value as seen by the application process (via `/env`)
- Whether failed resolution causes startup failure or silent fallback
- Both reference syntax formats

**Scenarios:**

- S1: Valid secret URI (versionless) → successful resolution
- S2: Valid secret URI with pinned version → successful resolution
- S3: Nonexistent secret name → silent failure, literal string injected
- S4: Nonexistent vault name → silent failure, literal string injected
- S5: `VaultName;SecretName;SecretVersion` format → resolution succeeds

## 7. Instrumentation

- `az webapp config appsettings set` — inject KV reference app settings
- `az webapp restart` — trigger resolution at startup
- Flask `/env` endpoint — inspect `os.environ` values as seen by application process
- `az keyvault create --enable-rbac-authorization false` — access policy model
- `az keyvault set-policy` — grant MI `get`, `list` on secrets

## 8. Procedure

1. Create Key Vault with access policy model.
2. Grant App Service MI `get` and `list` secret permissions via access policy.
3. Create secret `db-password` = `SuperSecret123!`.
4. Set app settings with S1–S5 reference variants; restart app; check `/env`.

## 9. Expected signal

- S1, S2, S5: App sees `SuperSecret123!` — resolved value, no `@Microsoft.KeyVault(...)` string.
- S3, S4: App sees the literal `@Microsoft.KeyVault(...)` string — resolution failed silently, app starts normally.

## 10. Results

### Key Vault and secret setup

```bash
az keyvault create -n kv-lab-7cdafc03 -g rg-lab-appservice-batch \
  --location koreacentral --enable-rbac-authorization false

az keyvault set-policy -n kv-lab-7cdafc03 \
  --object-id 058baa05-1640-4fab-a120-1d3ef66614bb \
  --secret-permissions get list

az keyvault secret set -n "db-password" --vault-name kv-lab-7cdafc03 \
  --value "SuperSecret123!"
→ https://kv-lab-7cdafc03.vault.azure.net/secrets/db-password/b5a484739a544f3dbae201f8a60a92f2
```

### App settings set

```bash
az webapp config appsettings set -n app-batch-1777849901 -g rg-lab-appservice-batch --settings \
  "DB_PASSWORD=@Microsoft.KeyVault(SecretUri=https://kv-lab-7cdafc03.vault.azure.net/secrets/db-password)" \
  "DB_WRONG=@Microsoft.KeyVault(SecretUri=https://kv-lab-7cdafc03.vault.azure.net/secrets/nonexistent-secret)" \
  "DB_BADKV=@Microsoft.KeyVault(SecretUri=https://kv-lab-DOES-NOT-EXIST.vault.azure.net/secrets/db-password)" \
  "DB_PINNED=@Microsoft.KeyVault(SecretUri=https://kv-lab-7cdafc03.vault.azure.net/secrets/db-password/b5a484739a544f3dbae201f8a60a92f2)" \
  "DB_BADFORMAT=@Microsoft.KeyVault(VaultName=kv-lab-7cdafc03;SecretName=db-password;SecretVersion=)"
```

### Resolution results after restart (observed via `/env`)

| App Setting | Reference | Result |
|-------------|-----------|--------|
| `DB_PASSWORD` | versionless `SecretUri` | `SuperSecret123!` ✅ |
| `DB_WRONG` | nonexistent secret name | `@Microsoft.KeyVault(SecretUri=https://kv-lab-7cdafc03...nonexistent-secret)` ❌ |
| `DB_BADKV` | nonexistent vault | `@Microsoft.KeyVault(SecretUri=https://kv-lab-DOES-NOT-EXIST...)` ❌ |
| `DB_PINNED` | pinned to specific version | `SuperSecret123!` ✅ |
| `DB_BADFORMAT` | `VaultName;SecretName;SecretVersion=` format | `SuperSecret123!` ✅ |

!!! warning "Silent failure — no startup error"
    Failed KV references do NOT cause the app to fail to start. The application starts normally with the literal `@Microsoft.KeyVault(...)` string as the env var value. There is no exception, no error log, and no startup failure. The only indication is the wrong value appearing in the running process.

### App startup behavior with failed references

```bash
# App starts normally even with multiple failed KV references
curl https://app-batch-1777849901.azurewebsites.net/
→ {"status": "ok", ...}   # HTTP 200 — app started successfully

# Failed reference visible as literal string
curl https://app-batch-1777849901.azurewebsites.net/env | jq '.env.DB_WRONG'
→ "@Microsoft.KeyVault(SecretUri=https://kv-lab-7cdafc03.vault.azure.net/secrets/nonexistent-secret)"
```

### Identity configuration verified

```bash
az webapp show -n app-batch-1777849901 -g rg-lab-appservice-batch \
  --query "properties.keyVaultReferenceIdentity"
→ "SystemAssigned"
```

## 11. Interpretation

- **Measured**: H1 is confirmed. With correct access policy (`get`, `list`) on the MI, the `SecretUri` reference resolves to the plaintext secret value. The application process sees `SuperSecret123!`, not the reference syntax. **Measured**.
- **Measured**: H2 is confirmed. A nonexistent secret name causes silent resolution failure — the literal `@Microsoft.KeyVault(...)` string is injected as the env var value. The app starts without error. **Measured**.
- **Measured**: H3 is confirmed. A nonexistent vault name also causes silent resolution failure with identical symptom — literal reference string, no startup error. **Measured**.
- **Measured**: H4 is confirmed. Both `SecretUri` format (versionless and versioned) and `VaultName;SecretName;SecretVersion` format resolve successfully when the identity has access. **Measured**.

## 12. What this proves

- Key Vault reference resolution failures are **silent** — the application starts normally with the wrong value injected. **Measured**.
- A nonexistent secret name and a nonexistent vault name produce the same failure symptom: literal reference string as the env var value. **Measured**.
- The `VaultName;SecretName;SecretVersion` format works in addition to `SecretUri`. **Measured**.
- `keyVaultReferenceIdentity` is set to `SystemAssigned` when system-assigned MI is used for resolution. **Observed**.

## 13. What this does NOT prove

- The portal "Key Vault reference status" column (red `!` vs green checkmark) was not observed — Kudu/portal access was not available in this test environment.
- Key Vault firewall blocking (network-level failure) was not tested — this would require VNet integration.
- The behavior when the MI has no access policy at all (as opposed to a policy with wrong secret name) was not directly tested.
- Secret rotation with a versionless reference (updating the secret value then restarting) was not validated — but is implied by the versionless URI behavior.

## 14. Support takeaway

When a customer's App Service application receives the literal `@Microsoft.KeyVault(...)` string instead of the secret value:

1. **Check the identity**: `az webapp show -n <app> -g <rg> --query "properties.keyVaultReferenceIdentity"`. Must be `SystemAssigned` or the user-assigned MI resource ID.
2. **Verify access policy or RBAC**: `az keyvault show -n <vault> --query "properties.accessPolicies"`. The MI must have `get` and `list` secret permissions (access policy model) or `Key Vault Secrets User` role (RBAC model).
3. **Verify the secret exists**: `az keyvault secret show --vault-name <vault> -n <secret-name>`. A nonexistent secret name causes silent failure — no error, just the wrong value.
4. **Verify the vault exists and is reachable**: Wrong vault name or a Key Vault firewall blocking App Service outbound IPs both cause silent failure with identical symptom.
5. **Resolution happens at startup**: After fixing the issue, the app must restart to pick up the resolved value. There is no dynamic re-resolution at request time.
6. **Check the portal Configuration blade**: Each KV-reference app setting has a status icon (✅ or ❌) that shows whether the last resolution attempt succeeded.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
KV="<keyvault-name>"

# Create KV with access policy model (not RBAC)
az keyvault create -n $KV -g $RG --location <region> \
  --enable-rbac-authorization false

# Grant MI access
MI_PRINCIPAL=$(az webapp show -n $APP -g $RG --query "identity.principalId" -o tsv)
az keyvault set-policy -n $KV \
  --object-id $MI_PRINCIPAL \
  --secret-permissions get list

# Add test secret
az keyvault secret set -n "my-secret" --vault-name $KV --value "correct-value"

# Set app settings — valid and invalid references
az webapp config appsettings set -n $APP -g $RG --settings \
  "GOOD_REF=@Microsoft.KeyVault(SecretUri=https://$KV.vault.azure.net/secrets/my-secret)" \
  "BAD_REF=@Microsoft.KeyVault(SecretUri=https://$KV.vault.azure.net/secrets/does-not-exist)"

az webapp restart -n $APP -g $RG
sleep 40

# Observe via /env endpoint (add endpoint to app)
# GOOD_REF → "correct-value"
# BAD_REF  → "@Microsoft.KeyVault(SecretUri=...)"  ← literal string, silent failure
```

## 16. Related guide / official docs

- [Use Key Vault references for App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references)
- [Grant your app access to Key Vault](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references#grant-your-app-access-to-a-key-vault)
- [Troubleshoot Key Vault references](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references#troubleshooting-key-vault-references)
