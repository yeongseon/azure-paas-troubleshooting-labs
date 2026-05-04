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

# Certificate Store Mismatch: User vs. LocalMachine Store on Windows

!!! warning "Status: Draft - Blocked"
    Execution blocked: Windows App Service plan required. All lab plans are Linux.

## 1. Question

On Windows App Service, certificates uploaded to the App Service certificate store are loaded via the `WEBSITE_LOAD_CERTIFICATES` app setting. The certificate is placed in the `CurrentUser\My` certificate store for the application process. Under what conditions does code that looks up certificates from `LocalMachine\My` fail to find the certificate, and how does this behavior differ between Full Trust and partial trust applications?

## 2. Why this matters

.NET applications frequently load certificates from the Windows certificate store using `X509Store`. Code that hardcodes `StoreLocation.LocalMachine` (a common pattern from on-premises environments) does not find certificates loaded by App Service, which places them in `CurrentUser`. This causes a `CryptographicException` or `null` return from `Find()` that appears as a certificate-not-found error rather than a store location error, making it difficult to diagnose without understanding the platform's certificate loading behavior.

## 3. Customer symptom

"Certificate is visible in the portal but the app can't find it" or "`X509Store.Find()` returns empty even though we set `WEBSITE_LOAD_CERTIFICATES`" or "The code works on our VM but fails on App Service with a certificate error."

## 4. Hypothesis

- H1: App Service loads certificates (specified in `WEBSITE_LOAD_CERTIFICATES`) into `CurrentUser\My` store for the IIS worker process identity. Code that opens `StoreLocation.LocalMachine` finds an empty store and returns `null` or an empty collection.
- H2: When `WEBSITE_LOAD_CERTIFICATES=*` is set, all uploaded certificates are loaded. When set to a specific thumbprint (comma-separated), only those certificates are loaded. An incorrect thumbprint (case sensitivity, spaces) results in the certificate not being loaded.
- H3: `StoreLocation.CurrentUser` correctly finds the certificate after `WEBSITE_LOAD_CERTIFICATES` is set. A restart is required after adding or updating the setting.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | .NET 8 |
| OS | Windows |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Runtime

**Controlled:**

- Self-signed certificate uploaded to App Service Certificates
- `WEBSITE_LOAD_CERTIFICATES` set to the certificate thumbprint
- .NET 8 application that reads from both `LocalMachine` and `CurrentUser` stores

**Observed:**

- Certificate found/not found under each `StoreLocation`
- Behavior with `WEBSITE_LOAD_CERTIFICATES=*` vs. specific thumbprint vs. missing setting

**Scenarios:**

- S1: `WEBSITE_LOAD_CERTIFICATES` not set → neither store has the cert
- S2: `WEBSITE_LOAD_CERTIFICATES=<thumbprint>` → `CurrentUser` has cert; `LocalMachine` does not
- S3: Code searches `LocalMachine` → not found; code searches `CurrentUser` → found
- S4: `WEBSITE_LOAD_CERTIFICATES=*` → all uploaded certs available in `CurrentUser`

## 7. Instrumentation

- App `/cert-check` endpoint that enumerates both `LocalMachine\My` and `CurrentUser\My` and returns thumbprints found
- App Service platform log for certificate loading events
- Kudu console (PowerShell): `Get-ChildItem Cert:\CurrentUser\My` and `Get-ChildItem Cert:\LocalMachine\My`

## 8. Procedure

_To be defined during execution._

### Sketch

1. Generate and upload a self-signed certificate to App Service **TLS/SSL settings > Private Key Certificates**.
2. Deploy .NET app with `/cert-check` endpoint that lists certs in both stores.
3. S1: No `WEBSITE_LOAD_CERTIFICATES` setting → verify both stores empty.
4. S2: Set `WEBSITE_LOAD_CERTIFICATES=<thumbprint>` and restart → verify cert appears in `CurrentUser` only.
5. S3: Call the endpoint with `StoreLocation.LocalMachine` hardcoded → verify `null` return.
6. S4: Set `WEBSITE_LOAD_CERTIFICATES=*` → verify all uploaded certs in `CurrentUser`.

## 9. Expected signal

- S1: Both stores empty; `/cert-check` returns empty arrays for both.
- S2: `CurrentUser\My` contains the certificate; `LocalMachine\My` is empty.
- S3: `LocalMachine` lookup returns `null`; `CurrentUser` lookup returns the certificate object.
- S4: All uploaded certificates appear in `CurrentUser\My`.

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

- `WEBSITE_LOAD_CERTIFICATES` accepts a comma-separated list of thumbprints or `*` for all. Thumbprints must match exactly (case-insensitive, no spaces).
- After setting `WEBSITE_LOAD_CERTIFICATES`, restart the app to load the certificates. Changes to the setting without restart do not take effect.
- On Linux App Service, certificates are available as PEM files at `/var/ssl/private/<thumbprint>.p12`. There is no Windows certificate store on Linux.

## 16. Related guide / official docs

- [Use a TLS/SSL certificate in your code in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate-in-code)
- [WEBSITE_LOAD_CERTIFICATES app setting](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings#tls-and-ssl)
