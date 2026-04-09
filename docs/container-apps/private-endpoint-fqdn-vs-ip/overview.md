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

## Question

What are the behavioral differences when accessing a Container App via private endpoint FQDN versus direct IP address, and what breaks when bypassing DNS resolution?

## Why this matters

Customers using private endpoints sometimes attempt to access Container Apps by IP address directly, bypassing the private DNS zone. This can fail due to TLS certificate validation (the certificate is issued for the FQDN, not the IP), SNI routing requirements, or ingress layer behavior that depends on the host header matching a configured domain. Support engineers need to explain why FQDN access works but IP access fails.

## Customer symptom

"App works via FQDN but fails via IP address" or "Private endpoint connection intermittently fails" or "TLS handshake fails when connecting by IP."

## Planned approach

Deploy a Container App with a private endpoint and private DNS zone. Test access via: (1) FQDN with proper DNS resolution, (2) direct IP with no host header, (3) direct IP with FQDN in host header, (4) direct IP with SNI set to FQDN. Document the failure mode and error message for each scenario.

## Key variables

**Controlled:**

- Private endpoint configuration
- Private DNS zone configuration
- Access method (FQDN, IP, IP+host header, IP+SNI)
- TLS verification (enabled, disabled)

**Observed:**

- TLS handshake success/failure and certificate presented
- HTTP response status and error message
- Ingress routing behavior
- DNS resolution path

## Expected evidence tags

Observed, Measured, Strongly Suggested

## Related resources

- [Microsoft Learn: Container Apps networking](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
- [azure-networking-practical-guide](https://github.com/yeongseon/azure-networking-practical-guide)
