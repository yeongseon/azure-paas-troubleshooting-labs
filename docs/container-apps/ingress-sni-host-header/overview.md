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

# Ingress Host Header and SNI Behavior

!!! info "Status: Planned"

## 1. Question

How does Azure Container Apps ingress handle Server Name Indication (SNI) and host header routing, and what happens with mismatched or missing headers in custom domain scenarios?

## 2. Why this matters

Container Apps uses an Envoy-based ingress layer that routes traffic based on host headers and SNI. When customers configure custom domains, mismatches between the SNI value (TLS layer) and the host header (HTTP layer) can cause unexpected routing — traffic may reach the wrong app, receive a default certificate error, or fail silently. These edge cases are difficult to debug without understanding the ingress routing logic.

## 3. Customer symptom

"Custom domain works intermittently" or "Getting responses from the wrong app when using my custom domain."

## 4. Hypothesis

Ingress routing decisions in Azure Container Apps depend on both TLS SNI and HTTP host header context. Missing or mismatched values will produce deterministic routing or certificate outcomes that explain wrong-app responses and TLS/domain errors in custom domain scenarios.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption environment |
| Region | Korea Central |
| Runtime | Containerized HTTP app (nginx + test API) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

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

## 7. Instrumentation

- `curl` and `openssl s_client` with explicit SNI and host-header permutations
- Container app access logs and revision-level request logs
- Azure Monitor logs for ingress and environment diagnostics
- DNS query tools (`nslookup`, `dig`) to confirm resolution path during each case
- Test endpoint responses that include app identity for unambiguous routing verification

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Matching SNI and host header routes traffic predictably to the intended app with expected certificate.
- Missing or mismatched SNI produces certificate mismatches or default ingress certificate behavior.
- Mismatched host header can route to an unexpected backend or return domain-not-configured style errors.
- The observed outcome category is repeatable for each SNI/host-header combination.

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

- Use unique response payload markers per app so routing destination is obvious in every test.
- Flush local DNS cache when switching between FQDN and direct test variants.
- Capture full TLS handshake output alongside HTTP response for each case.
- Keep one certificate and domain change at a time to avoid overlapping configuration effects.

## 16. Related guide / official docs

- [Microsoft Learn: Custom domains in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
