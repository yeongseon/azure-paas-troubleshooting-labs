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

# Key Vault Certificate Import and Binding Failures on App Service

!!! info "Status: Planned"

## 1. Question

When a TLS certificate stored in Azure Key Vault is imported into App Service and bound to a custom domain, under what conditions does the import fail, does the sync to a new certificate version stall, and does a Key Vault network restriction silently break the binding — and how does each failure surface differ?

## 2. Why this matters

Organizations commonly store TLS certificates in Key Vault and bind them to App Service custom domains by importing the certificate through the App Service resource provider. This path relies on the App Service resource provider's access to Key Vault (not the app's managed identity), and on correct permissions for both certificates and their backing secrets. When any link in this chain breaks — permissions, network access, or version sync — the failure is often silent at the application level: HTTPS continues serving the old certificate until it expires, or the custom domain HTTPS binding fails entirely with no clear error in application logs.

## 3. Customer symptom

"My custom domain shows a certificate error or an expired certificate even though I updated the certificate in Key Vault" or "The Key Vault certificate import in the portal fails with a permissions error but I already assigned the right role" or "Certificate binding worked before but broke after I restricted Key Vault network access."

## 4. Hypothesis

- H1: The App Service certificate import from Key Vault requires the **App Service resource provider** (`Microsoft.Azure.WebSites`) to have `Get` permission on both the Key Vault **certificate** and its backing **secret**. Granting permissions only to the app's managed identity is not sufficient and will result in a permission error during import.
- H2: After importing a certificate and a new version is created in Key Vault, App Service does **not** automatically pick up the new version; a manual sync via the portal or re-import is required. The binding continues serving the old certificate until manually refreshed.
- H3: If Key Vault network access is restricted (selected networks or private endpoint) and the "Allow trusted Microsoft services" exception is not enabled, the import operation fails — but the error message does not clearly indicate a network cause.
- H4: A successfully bound certificate continues to serve HTTPS even after the Key Vault source becomes inaccessible; the failure only surfaces at the next sync or renewal attempt.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Security

**Controlled:**

- App Service with a custom domain and HTTPS binding via Key Vault-imported certificate
- Key Vault with a self-signed certificate (created via `az keyvault certificate create`)
- Permission assignments: App Service resource provider (`Microsoft.Azure.WebSites`) vs. app managed identity

**Observed:**

- Import success/failure and error message in Azure Portal and Activity Log
- TLS handshake result (certificate subject, expiry) against the custom domain
- Auto-sync behavior after certificate version rotation in Key Vault
- Error message when Key Vault network restriction blocks the import

**Scenarios:**

- S1: Correct permissions to App Service resource provider — baseline import
- S2: Permissions to app managed identity only (not resource provider) — import attempt
- S3: Certificate rotated (new version in Key Vault) — measure auto-sync vs. manual sync
- S4: Key Vault network restriction without "Allow trusted Microsoft services" — import attempt

**Independent run definition**: One import or sync attempt per scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Azure Portal: App Service → TLS/SSL settings → Certificates — import status and error message
- Key Vault audit logs (`AuditEvent`): record `getCertificate` and `getSecret` caller identity
- `az webapp config ssl list --resource-group <rg> --name <app>` — current certificate bindings
- TLS handshake: `openssl s_client -connect <custom-domain>:443 -servername <custom-domain>` — certificate subject and expiry
- App Service Activity Log: certificate import and sync operations
- Key Vault RBAC / access policy: verify `Microsoft.Azure.WebSites` principal is present

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create Key Vault with a self-signed certificate. Assign `Key Vault Certificate User` to `Microsoft.Azure.WebSites` principal.
2. Import certificate via `az webapp config ssl import` (S1); bind to custom domain; verify with `openssl -servername`.
3. Remove resource provider permission; assign only to app managed identity (S2); re-attempt import; capture error.
4. Restore permission; rotate certificate (new version in Key Vault); observe auto-sync over 24 hours; compare with manual "Sync" (S3).
5. Enable Key Vault selected-network restriction without trusted services exception (S4); attempt import; record error message and Key Vault audit log.

## 9. Expected signal

- S1: Import succeeds; audit log shows caller as `Microsoft.Azure.WebSites`; `openssl` returns expected certificate.
- S2: Import fails; error message references permissions; audit log shows access denied or no entry under managed identity principal.
- S3: Binding continues serving old certificate after rotation; manual sync picks up new version within minutes; auto-sync unconfirmed within 24 hours.
- S4: Import fails with generic connectivity or authorization error; Key Vault audit log may have no entry (blocked before auth).

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

- The App Service resource provider principal is `Microsoft.Azure.WebSites`, not the app's managed identity. Check Key Vault RBAC or access policy for this principal when troubleshooting import failures.
- Use `az keyvault certificate create` with the default policy to generate a self-signed certificate without a CA dependency.
- "Allow trusted Microsoft services" in Key Vault network settings covers the App Service resource provider; enable this when Key Vault is network-restricted.
- Always validate the certificate against the custom domain using `-servername <custom-domain>`, not the default `*.azurewebsites.net` hostname.

## 16. Related guide / official docs

- [Add a TLS/SSL certificate in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate)
- [Import a certificate from Key Vault](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate#import-a-certificate-from-key-vault)
- [Key Vault trusted services](https://learn.microsoft.com/en-us/azure/key-vault/general/overview-vnet-service-endpoints#trusted-services)
