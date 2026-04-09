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

# Managed Identity RBAC Propagation vs Token Cache

!!! info "Status: Planned"

## 1. Question

After assigning an RBAC role to a managed identity, how long does it take for the role to become effective across different Azure services, and how does the Azure Identity SDK token cache interact with RBAC propagation delays?

## 2. Why this matters

Customers frequently report that managed identity authentication "doesn't work" immediately after role assignment. The RBAC propagation delay (documented as "up to 10 minutes" but highly variable) combined with SDK-level token caching creates a confusing window where:

1. The role is assigned but not yet propagated → 403 errors
2. The role propagates but the SDK has cached a token without the role → continued 403s
3. Both caches expire and the new role finally takes effect → success

Understanding the actual timing distribution across services helps support engineers estimate resolution windows and avoid unnecessary troubleshooting.

## 3. Customer symptom

- "We assigned the role 15 minutes ago but still getting 403 Forbidden."
- "It works from one function app but not another, even though both have the same role."
- "If we restart the app, it starts working — but we don't want to restart in production."

## 4. Hypothesis

1. RBAC propagation delay varies by service: Storage and Key Vault propagate within 5 minutes; Service Bus and Event Hubs may take longer.
2. The Azure Identity SDK caches tokens for 24 hours by default, masking propagation completion.
3. The combination of RBAC propagation + token cache creates a worst-case delay of up to 30 minutes without restart.
4. Restarting the application clears the token cache and picks up the propagated role immediately.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service, Functions, Container Apps (all three) |
| SKU / Plan | Various |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Hybrid (Config: does it propagate? Performance: how long does it take?)

**Controlled:**

- Target services: Storage Blob, Key Vault, Service Bus, SQL Database
- Role assignments: new assignment, role change, role removal
- Token cache: default behavior vs cache disabled
- Application restart: before/after propagation

**Observed:**

- Time from role assignment to first successful authenticated call
- Token cache hit/miss behavior
- 403 error rate over time after role assignment
- Propagation time distribution across services

**Independent run definition**: Fresh role assignment (previous role fully removed and confirmed), measure time to first success

**Planned runs per configuration**: 5 per target service

**Warm-up exclusion rule**: None — propagation delay IS the measurement

**Primary metric**: Time to first successful authenticated call; meaningful effect threshold: 2 minutes absolute

**Comparison method**: Descriptive statistics per service; Mann-Whitney U for cross-service comparison

## 7. Instrumentation

- Application code: repeated authentication attempts every 30 seconds with timestamp logging
- Application Insights: dependency call traces with success/failure
- Azure Activity Log: role assignment timestamp
- Custom logging: token acquisition events, cache hits, 403/200 transitions

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Storage Blob: propagation in 2-5 minutes
- Key Vault: propagation in 2-5 minutes
- Service Bus: propagation in 5-10 minutes
- SQL Database: propagation in 5-15 minutes
- Token cache extends apparent delay by up to 5-10 minutes beyond propagation
- Restart eliminates cache-related delay

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

- RBAC propagation timing is not guaranteed and may vary by region and load
- System-assigned vs user-assigned managed identity may have different propagation characteristics
- Ensure previous role assignments are fully removed before testing new assignments
- Token cache behavior depends on the Azure Identity SDK version

## 16. Related guide / official docs

- [What is Azure RBAC?](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)
- [Troubleshoot Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting)
- [Managed identities for Azure resources](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Azure Identity client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme)
