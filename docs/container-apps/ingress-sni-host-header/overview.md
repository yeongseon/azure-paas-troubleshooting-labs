# Ingress Host Header and SNI Behavior

!!! info "Status: Planned"

## Question

How does Azure Container Apps ingress handle Server Name Indication (SNI) and host header routing, and what happens with mismatched or missing headers in custom domain scenarios?

## Why this matters

Container Apps uses an Envoy-based ingress layer that routes traffic based on host headers and SNI. When customers configure custom domains, mismatches between the SNI value (TLS layer) and the host header (HTTP layer) can cause unexpected routing — traffic may reach the wrong app, receive a default certificate error, or fail silently. These edge cases are difficult to debug without understanding the ingress routing logic.

## Customer symptom

"Custom domain works intermittently" or "Getting responses from the wrong app when using my custom domain."

## Planned approach

Deploy multiple Container Apps in the same environment with custom domains configured. Send requests with varying combinations of SNI and host header values — matching, mismatched, missing, and wildcard. Observe which app receives each request, what certificate is presented, and what error responses are returned.

## Key variables

**Controlled:**

- Number of Container Apps in the environment
- Custom domain and certificate configuration
- SNI value in TLS ClientHello
- Host header value in HTTP request

**Observed:**

- Which app receives the request
- Certificate presented during TLS handshake
- HTTP response status and body
- Ingress access logs

## Expected evidence tags

Observed, Measured, Inferred

## Related resources

- [Microsoft Learn: Custom domains in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
