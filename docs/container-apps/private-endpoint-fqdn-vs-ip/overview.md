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

# Private Endpoint: FQDN vs IP Access

!!! info "Status: Planned"

## 1. Question

What are the behavioral differences when accessing a Container App via private endpoint FQDN versus direct IP address, and what breaks when bypassing DNS resolution?

## 2. Why this matters

Customers using private endpoints sometimes attempt to access Container Apps by IP address directly, bypassing the private DNS zone. This can fail due to TLS certificate validation (the certificate is issued for the FQDN, not the IP), SNI routing requirements, or ingress layer behavior that depends on the host header matching a configured domain. Support engineers need to explain why FQDN access works but IP access fails.

## 3. Customer symptom

"App works via FQDN but fails via IP address" or "Private endpoint connection intermittently fails" or "TLS handshake fails when connecting by IP."

## 4. Hypothesis

For a Container App behind a private endpoint, FQDN-based access through private DNS will consistently succeed, while direct IP access will fail or produce different TLS/routing outcomes unless both host header and SNI are explicitly aligned to the app domain; even then, certificate validation remains domain-bound rather than IP-bound.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption environment with VNet |
| Region | Korea Central |
| Runtime | Containerized HTTP app |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Private endpoint configuration
- Private DNS zone configuration
- Access method (FQDN, IP, IP + host header, IP + SNI)
- TLS verification mode (enabled, disabled)

**Observed:**

- TLS handshake success/failure and certificate presented
- HTTP response status and error message
- Ingress routing behavior
- DNS resolution path

## 7. Instrumentation

- `curl` (with/without host header and certificate validation)
- `openssl s_client` (explicit SNI and certificate inspection)
- DNS tools (`nslookup`, `dig`) for private zone resolution checks
- Container Apps logs (ingress/request and revision-level logs)
- Azure Monitor logs for networking and connection diagnostics

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- FQDN access via private DNS resolves to the private endpoint and succeeds with expected certificate/domain alignment.
- Direct IP access without matching SNI/host header fails TLS validation or returns ingress/domain errors.
- Direct IP access may only partially work when host header/SNI are forced, but behavior remains distinct from normal FQDN path and does not invalidate domain-bound certificate requirements.
- Failure category is repeatable by access pattern and explains customer reports where FQDN works while IP fails.

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

- Validate private DNS first (`privatelink` FQDN resolution) before testing direct IP variants.
- Record TLS handshake output and HTTP response together for each access pattern.
- Keep one variable change per request path (host header or SNI) to isolate failure causes.
- Run each case with TLS verification both enabled and explicitly disabled to separate certificate versus routing failures.
- Capture the exact endpoint string used (`https://fqdn` vs `https://ip`) in every test artifact.

## 16. Related guide / official docs

- [Microsoft Learn: Container Apps networking](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
- [azure-networking-practical-guide](https://github.com/yeongseon/azure-networking-practical-guide)
