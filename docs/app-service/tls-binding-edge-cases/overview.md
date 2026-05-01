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

# TLS Binding Edge Cases: SNI vs IP, Wildcard Certificates, and Handshake Failures

!!! info "Status: Planned"

## 1. Question

When multiple custom domain bindings coexist on an App Service — mixing SNI-based and IP-based TLS bindings, wildcard certificates, and root vs. subdomain hostnames — under what conditions does the wrong certificate get presented to the client, causing handshake failures that are indistinguishable from application errors?

## 2. Why this matters

TLS handshake failures on App Service are frequently misattributed to application code or network issues. In practice, they often stem from binding ordering, certificate selection precedence, or SNI fallback behavior. When a wildcard certificate covers `*.contoso.com` but not `contoso.com`, root-domain requests fail with a certificate mismatch. When SNI is not supported by a legacy client, the IP-based binding (if any) governs certificate selection. Support engineers who focus on the application layer miss these binding-layer failures entirely.

## 3. Customer symptom

"My app works on `www.contoso.com` but HTTPS fails on `contoso.com` even though I uploaded the same certificate" or "After adding a new custom domain, existing SSL connections started getting certificate mismatch errors" or "Our legacy client can't connect — it worked before we added more SSL bindings."

## 4. Hypothesis

- H1: A wildcard certificate (e.g., `*.contoso.com`) does not cover the apex/root domain (`contoso.com`). Binding the wildcard certificate to the root domain results in a certificate mismatch at the TLS handshake layer; the client receives the wildcard cert with `*.contoso.com` as the subject, which is not valid for `contoso.com`.
- H2: When multiple SNI bindings exist for different hostnames, App Service selects the certificate based on the SNI extension in the `ClientHello`. If a client does not send SNI (legacy TLS 1.0 clients), App Service falls back to the IP-based binding's certificate (if one exists) or the default App Service certificate, not the custom certificate.
- H3: Adding a new SNI binding for an additional hostname does not affect existing bindings. However, if the new binding uses a certificate with a Subject Alternative Name (SAN) that overlaps with an existing binding's hostname, the certificate presented may change depending on binding evaluation order.
- H4: A custom domain binding requires domain ownership verification before the certificate is served. If verification is revoked or the TXT record is removed after binding, the binding remains active but re-verification may be required after certificate renewal, causing renewal failures that surface as expired certificate errors in clients.

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

**Experiment type**: Networking / TLS

**Controlled:**

- App Service with two custom domains: apex (`contoso-lab.com`) and subdomain (`www.contoso-lab.com`)
- Wildcard certificate covering `*.contoso-lab.com` (not apex)
- Separate single-domain certificate for apex

**Observed:**

- Certificate presented per hostname (captured via `openssl s_client`)
- TLS handshake success/failure per client type (SNI-capable vs SNI-less)
- Certificate Subject and SAN fields in the server response
- Error type at client: `SSL_ERROR_BAD_CERT_DOMAIN`, `ERR_CERT_COMMON_NAME_INVALID`, etc.

**Scenarios:**

- S1: Wildcard cert bound to apex domain — verify mismatch
- S2: Correct single-domain cert for apex, wildcard for subdomain — verify correct cert per hostname
- S3: SNI-less client (simulated via `openssl s_client` without `-servername`) — verify fallback cert
- S4: Two SNI bindings with overlapping SAN — verify which cert is presented

**Independent run definition**: One `openssl s_client` connection per scenario per hostname.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `openssl s_client -connect <hostname>:443 -servername <hostname>` — certificate inspection with SNI
- `openssl s_client -connect <ip>:443` (no `-servername`) — SNI-less fallback cert inspection
- `curl -v https://<hostname>` — TLS handshake details in verbose output
- Azure Portal: App Service > TLS/SSL settings > Custom Domains — binding list and certificate assignment
- Certificate SAN inspection: `openssl x509 -text -noout -in cert.pem | grep -A1 "Subject Alternative Name"`

## 8. Procedure

_To be defined during execution._

### Sketch

1. Obtain a wildcard certificate for `*.contoso-lab.com` and a single-domain certificate for `contoso-lab.com`; upload both to App Service.
2. S1: Bind the wildcard cert to the apex domain; use `openssl s_client` to verify the mismatch; capture the presented certificate's Subject field.
3. S2: Bind the correct single-domain cert to apex; re-verify with `openssl s_client`; confirm correct cert per hostname.
4. S3: Issue `openssl s_client -connect <ip>:443` without `-servername`; record which certificate is presented; compare to the IP-based binding (if configured) or App Service default cert.
5. S4: Add a second SNI binding with a SAN that includes `www.contoso-lab.com`; inspect which certificate is presented for `www.contoso-lab.com` and whether the order of bindings affects the result.

## 9. Expected signal

- S1: `openssl s_client` shows the wildcard cert with Subject `*.contoso-lab.com`; client reports `ERR_CERT_COMMON_NAME_INVALID` for `contoso-lab.com`.
- S2: Correct certificate presented per hostname; no mismatch.
- S3: Without SNI, App Service serves either the IP-based binding cert or the default App Service cert (`*.azurewebsites.net`), not the custom SNI cert.
- S4: Binding order or explicit binding assignment governs which cert is served; overlapping SANs do not cause automatic cert substitution.

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

- Wildcard certificates cover `*.example.com` but not `example.com` (apex). This is a TLS standard constraint, not an App Service limitation. Apex domains require a separate certificate.
- SNI is the default binding type for App Service; IP-based SSL requires a dedicated outbound IP and incurs additional cost.
- `openssl s_client` without `-servername` simulates a TLS 1.0 client that does not send the SNI extension; this is the only reliable way to test SNI fallback behavior from a command line.
- Certificate bindings are evaluated at the platform ingress layer (Front Door / ARR), not within the application container.

## 16. Related guide / official docs

- [Add a TLS/SSL certificate in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate)
- [Secure a custom DNS name with a TLS/SSL binding](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-bindings)
- [SNI SSL vs IP SSL in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-bindings#remap-a-record-for-ip-ssl)
