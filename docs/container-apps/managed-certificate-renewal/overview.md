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

# Managed Certificate Renewal Failure on Custom Domain

!!! warning "Status: Draft - Blocked"
    Execution blocked: Custom domain DNS record required. No custom domain available in this lab.

## 1. Question

Container Apps supports managed TLS certificates for custom domains. The platform handles certificate issuance and renewal automatically. Under what conditions does automatic renewal fail (DNS validation, domain ownership verification, rate limits), and what is the observable impact when a managed certificate expires?

## 2. Why this matters

Managed certificate renewal is automatic but not unconditional. If the custom domain's DNS validation record is removed or modified (e.g., during a DNS migration), the renewal validation fails and the certificate is not renewed. Because the renewal happens in the background without user notification (unless alerting is configured), the first indication of failure is a certificate expiry warning in browsers or an HTTPS connection error for users. The window between "renewal starts failing" and "certificate expires" may be days or weeks, giving time to fix if monitored.

## 3. Customer symptom

"HTTPS started showing a certificate error — the certificate expired" or "The managed certificate renewal failed and we don't know why" or "After migrating DNS providers, our Container App's certificate stopped renewing."

## 4. Hypothesis

- H1: Container Apps managed certificate renewal uses DNS-based domain validation (HTTP challenge or DNS TXT record). If the validation mechanism fails (DNS record missing or pointing to wrong target), the renewal fails silently. The existing certificate remains valid until its natural expiry (90 days for Let's Encrypt-based certs).
- H2: After the certificate expires, Container Apps serves no certificate or a self-signed certificate for the custom domain, causing TLS handshake failures for clients that enforce certificate validation.
- H3: The certificate status and renewal events are visible in the Container Apps environment **Certificates** blade and in the Activity Log under the managed certificate resource.
- H4: Re-adding the domain (triggering a fresh validation and issuance) resolves an expired or renewal-failed certificate.

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

**Experiment type**: Networking / Certificate management

**Controlled:**

- Custom domain bound to Container Apps with managed certificate
- DNS validation record present and removed (to simulate failure)

**Observed:**

- Certificate renewal status and events
- Browser/client behavior when certificate approaches expiry or validation fails
- Error messages in Activity Log

**Scenarios:**

- S1: Healthy DNS → certificate issues and renews correctly
- S2: Remove DNS validation record → renewal fails; observe failure notification
- S3: Certificate expires → observe client-visible error
- S4: Re-add domain → fresh certificate issued

## 7. Instrumentation

- Azure portal **Certificates** blade showing certificate status and expiry
- `openssl s_client -connect <domain>:443 -servername <domain>` to check certificate expiry
- Activity Log for `Microsoft.App/managedEnvironments/managedCertificates` events
- Azure Monitor alert on certificate expiry (if configured)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Bind a custom domain to Container Apps; request a managed certificate; verify issuance.
2. Record certificate expiry date and validation mechanism.
3. S2: Remove or modify the DNS validation record; wait for the next renewal attempt (may require waiting or triggering a forced renewal if the platform supports it).
4. S3: Cannot easily test natural expiry in lab — use `openssl` to simulate checking an expired certificate.
5. S4: Re-add the domain with correct DNS; verify new certificate is issued.

## 9. Expected signal

- S1: Certificate status "Active" with valid expiry date.
- S2: Certificate status changes to "Failed" or "Renewal Failed" after validation failure.
- S3: (Simulated) `openssl` reports certificate expired; browser shows NET::ERR_CERT_DATE_INVALID.
- S4: New certificate issued within minutes of correct DNS; status returns to "Active."

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

- Managed certificates in Container Apps use ACME protocol (Let's Encrypt or DigiCert) for issuance.
- Domain validation: Container Apps creates a DNS TXT record (`_dnsauth.<domain>`) for validation. This record must remain in DNS for renewal.
- Set up Azure Monitor alert on certificate expiry metric or use Azure Policy to audit certificate health.

## 16. Related guide / official docs

- [Custom domains and managed certificates in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates)
- [Let's Encrypt certificate lifecycle](https://letsencrypt.org/how-it-works/)
