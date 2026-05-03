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

# Key Vault Reference Resolution Failure at App Startup

!!! info "Status: Planned"

## 1. Question

When App Service app settings reference Key Vault secrets using the `@Microsoft.KeyVault(...)` syntax, under what conditions does resolution fail at startup, and how does each failure mode (identity misconfiguration, firewall restriction, wrong secret URI, version pinning) manifest differently in the app settings panel and application logs?

## 2. Why this matters

Key Vault references are a common pattern for secrets management in App Service. When resolution fails, the app setting is silently set to the literal reference string (e.g., `@Microsoft.KeyVault(SecretUri=https://...)`), which causes the application to start with incorrect configuration — often resulting in connection failures or authentication errors that appear to be application bugs rather than platform configuration issues. The resolution status is surfaced in the portal but is easy to miss.

## 3. Customer symptom

"Our database connection string shows a weird `@Microsoft.KeyVault(...)` value inside the application instead of the actual secret" or "The app works locally but fails in Azure even though the app setting is configured" or "Key Vault reference was working and suddenly stopped after we added a firewall rule."

## 4. Hypothesis

- H1: When the system-assigned Managed Identity does not have `Key Vault Secrets User` RBAC on the Key Vault, resolution fails and the app receives the literal reference string. The portal shows a red "!" icon on the app setting.
- H2: When the Key Vault has a firewall enabled and the App Service outbound IPs are not whitelisted (and VNet Integration is not configured), resolution fails with a network connectivity error. The failure mode is indistinguishable from the RBAC failure in the app — both result in the literal reference string.
- H3: When the secret URI includes a specific version that has been disabled or deleted, resolution fails even if the identity and network are correctly configured.
- H4: When the secret URI omits the version (latest), resolution succeeds and always retrieves the current active version. Adding a new version to the secret is reflected on the next app restart without a configuration change.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Authentication

**Controlled:**

- App Service with system-assigned Managed Identity enabled
- Key Vault with a test secret
- App setting using `@Microsoft.KeyVault(SecretUri=...)` syntax

**Observed:**

- App setting value as seen by the application (via `/env` endpoint)
- Portal "Key Vault reference" status icon
- Application startup behavior and error messages

**Scenarios:**

- S1: Correct identity, correct URI, no firewall → successful resolution
- S2: Identity without RBAC → resolution fails, literal string delivered
- S3: Key Vault firewall blocks App Service IPs → resolution fails
- S4: Pinned to a disabled secret version → resolution fails
- S5: Pinned to latest version, rotate secret → verify new value picked up on restart

## 7. Instrumentation

- App Service portal **Configuration** blade (Key Vault reference status column)
- Application `/env` or `/config` endpoint that prints environment variables
- Key Vault diagnostic logs (`AuditEvent` category) to observe failed access attempts
- App Service application logs for startup errors

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create Key Vault, add secret `DB-PASSWORD` with value `correct-value`.
2. Enable system-assigned Managed Identity on App Service.
3. S1: Assign `Key Vault Secrets User` role; set app setting to `@Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/DB-PASSWORD/)`; restart; verify app sees `correct-value`.
4. S2: Remove the RBAC assignment; restart; verify app sees the literal reference string. Check portal icon.
5. S3: Re-add RBAC; add Key Vault firewall rule to block all networks; restart; verify failure.
6. S4: Re-enable network access; disable the current secret version; restart; verify failure on specific version URI.
7. S5: Use versionless URI; add new secret version; restart app; verify new value is loaded.

## 9. Expected signal

- S1: App sees `correct-value`; portal shows green checkmark on the app setting.
- S2: App sees `@Microsoft.KeyVault(...)`; portal shows red "!" with "Access denied" message.
- S3: App sees `@Microsoft.KeyVault(...)`; portal shows red "!" with "Failed to reach Key Vault" or network error.
- S4: App sees `@Microsoft.KeyVault(...)`; portal shows red "!" with "Secret version disabled or deleted."
- S5: After rotation and restart, app sees the new secret value; no configuration change needed.

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

- Key Vault reference syntax: `@Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/<secret-name>/<version>)` — omit version for latest.
- RBAC model: assign `Key Vault Secrets User` on the specific secret or the entire vault. Legacy access policy model also works but is deprecated.
- App Service outbound IPs can be found under **Properties > Outbound IP addresses** — add all to Key Vault firewall, or use VNet Integration + service endpoint for VNet-based access.
- Resolution happens at app startup / restart, not at request time. A configuration change that fixes the issue requires a restart to take effect.

## 16. Related guide / official docs

- [Use Key Vault references for App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references)
- [Grant your app access to Key Vault](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references#grant-your-app-access-to-a-key-vault)
