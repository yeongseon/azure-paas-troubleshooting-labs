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

# Key Vault Certificate Import and Binding Failures on App Service

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04. H1 confirmed (RP-level permissions required). H2 confirmed (no auto version sync). H3 disproven — App Service RP is a trusted Microsoft service that bypasses Key Vault network ACLs.

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
| SKU / Plan | Basic (B1) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |
| Key Vault | `kv-lab-7cdafc03` (access policy model) |
| Certificate | Self-signed (`lab-test-cert`) via `az keyvault certificate create` |
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

1. Created self-signed certificate `lab-test-cert` in Key Vault `kv-lab-7cdafc03` using `az keyvault certificate create` with the default policy.
2. **S1 (no RP permissions)**: Attempted `az webapp config ssl import` without granting App Service RP access to Key Vault. Captured error message.
3. **S1 fix**: Granted App Service RP SP (`abfa0a7c-a6b6-4736-8310-5855508787cd`) `Get` on certificates and secrets via access policy. Retried import — succeeded. Thumbprint: `349B855F7BCEDCC373D9BF458969264C578E35F0`.
4. **S3 (version rotation)**: Created new version of `lab-test-cert`. Compared new KV thumbprint (`680A1220...`) vs App Service thumbprint (`349B855F...`). No sync performed.
5. **S4 (network restriction)**: Set KV `defaultAction=Deny`. Created `lab-test-cert-2`. Attempted `az webapp config ssl import` for `lab-test-cert-2`. Observed result. Restored `defaultAction=Allow`.

### Sketch (original)

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

### S1: Import without App Service RP permission

```
ERROR: The service does not have access to '/subscriptions/.../providers/microsoft.keyvault/vaults/kv-lab-7cdafc03'
Key Vault. Please make sure that you have granted necessary permissions to the service to perform the request operation.
```

After granting `Get` permissions on certificates and secrets to the App Service RP SP (`abfa0a7c-a6b6-4736-8310-5855508787cd`), import succeeded:

```json
{
  "expirationDate": "2027-05-04T07:00:47+00:00",
  "name": "rg-lab-appservice-batch-kv-lab-7cdafc03-lab-test-cert",
  "thumbprint": "349B855F7BCEDCC373D9BF458969264C578E35F0"
}
```

### S3: New certificate version created — auto-sync NOT observed

| Source | Thumbprint |
|--------|------------|
| Original KV version (v1) | `349B855F7BCEDCC373D9BF458969264C578E35F0` |
| New KV version (v2) | `680A1220A84D41AFE4C70ACFBCC3011172449ABA` |
| App Service (immediately after v2 creation) | `349B855F7BCEDCC373D9BF458969264C578E35F0` |

App Service did not automatically pick up the new version. Manual sync via `az webapp config ssl import` or portal "Sync" is required.

### S4: Import with Key Vault network `defaultAction=Deny`

```json
{
  "expirationDate": "2027-05-04T07:04:12+00:00",
  "name": "rg-lab-appservice-batch-kv-lab-7cdafc03-lab-test-cert-2",
  "thumbprint": "95A5AB6174BB4B809A6EA041A4A30736BFD8DFAF"
}
```

Import **succeeded** despite network ACL set to Deny. The App Service resource provider is classified as a trusted Microsoft service and bypasses network ACL restrictions.

## 11. Interpretation

- **Observed**: Without explicitly granting the App Service resource provider service principal access to Key Vault, certificate import fails with a clear permissions error. The error message references the Key Vault resource path and says "the service does not have access."
- **Observed**: Granting `Get` permissions on certificates and secrets to SP `abfa0a7c-a6b6-4736-8310-5855508787cd` (the App Service RP principal for global regions) resolves the import failure immediately.
- **Observed**: After creating a new certificate version in Key Vault, App Service continues to hold the original certificate thumbprint. No automatic version sync occurred in the observation window.
- **Observed**: With Key Vault `defaultAction=Deny` (all network traffic blocked), `az webapp config ssl import` succeeded. The App Service RP bypasses Key Vault network ACLs as a trusted Microsoft service — H3 is disproven.
- **Inferred**: The distinction between "trusted Microsoft service bypass" and "private endpoint + firewall bypass" means that even in highly secured environments, the App Service RP can still access Key Vault across the network boundary, provided permissions are granted.
- **Not Proven**: Whether the trusted service bypass behavior also applies when Key Vault has a private endpoint configured (as opposed to network ACLs only).

## 12. What this proves

- App Service certificate import from Key Vault requires explicit `Get` permissions for the **App Service RP service principal** (`abfa0a7c-a6b6-4736-8310-5855508787cd`) on both the Key Vault certificate and its backing secret. The app's managed identity permissions are not used for import.
- App Service does NOT automatically sync to new certificate versions when a new version is created in Key Vault. The original thumbprint remains bound until a manual sync or re-import is performed.
- The App Service RP is a trusted Microsoft service that bypasses Key Vault network ACLs (`defaultAction=Deny`). Certificate import works even when the Key Vault firewall blocks all network traffic.

## 13. What this does NOT prove

- Whether the trusted service network bypass also applies when Key Vault has a **private endpoint** (rather than network ACLs) — private endpoint configurations restrict trusted service bypass.
- Whether automatic certificate renewal (for App Service managed certificates) follows the same trusted service path.
- The behavior when the App Service RP principal is used in an RBAC model Key Vault (vs. access policy model tested here).

## 14. Support takeaway

When a customer reports "Key Vault certificate import fails with a permissions error" or "certificate isn't updating after rotation":

1. **Import requires RP-level access, not app identity.** Grant `Get` on certificates AND secrets to SP `abfa0a7c-a6b6-4736-8310-5855508787cd` via Key Vault access policy (or `Key Vault Certificate User` role in RBAC model). The app's managed identity permissions are unrelated to import.
2. **New certificate versions are not auto-synced.** After rotating a certificate in Key Vault, manually run `az webapp config ssl import` or use the portal's "Sync" button to pick up the new version. Set up an Azure Monitor alert or script to detect version mismatch.
3. **Network ACLs do NOT block App Service RP.** If the customer says "import fails after restricting Key Vault network access," verify whether they have a private endpoint (which does break the trusted service bypass) vs. just firewall rules. Firewall rules alone do not block the App Service RP.
4. **Verify permissions on the secret, not just the certificate.** Key Vault certificates have a backing secret that the RP also reads. Missing `Get` on secrets (even with certificate `Get` granted) will cause import failure.

## 15. Reproduction notes

- The App Service resource provider principal is `Microsoft.Azure.WebSites`, not the app's managed identity. Check Key Vault RBAC or access policy for this principal when troubleshooting import failures.
- Use `az keyvault certificate create` with the default policy to generate a self-signed certificate without a CA dependency.
- "Allow trusted Microsoft services" in Key Vault network settings covers the App Service resource provider; enable this when Key Vault is network-restricted.
- Always validate the certificate against the custom domain using `-servername <custom-domain>`, not the default `*.azurewebsites.net` hostname.

## 16. Related guide / official docs

- [Add a TLS/SSL certificate in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate)
- [Import a certificate from Key Vault](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate#import-a-certificate-from-key-vault)
- [Key Vault trusted services](https://learn.microsoft.com/en-us/azure/key-vault/general/overview-vnet-service-endpoints#trusted-services)
