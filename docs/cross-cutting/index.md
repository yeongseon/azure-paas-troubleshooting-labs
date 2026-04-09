---
hide:
  - toc
---

# Cross-cutting Experiments

Experiments that span multiple Azure PaaS services and test platform-level behaviors shared across App Service, Functions, and Container Apps.

## Experiments

| Experiment | Type | Status |
|-----------|------|--------|
| [Managed Identity RBAC Propagation vs Token Cache](mi-rbac-propagation/overview.md) | Hybrid | Planned |
| [Private Endpoint DNS Negative Caching](pe-dns-negative-cache/overview.md) | Hybrid | Planned |

## Why cross-cutting?

Some troubleshooting scenarios are not specific to a single compute service. Identity propagation, DNS resolution, and networking behaviors apply across App Service, Functions, and Container Apps. Testing these cross-cutting behaviors reveals whether the root cause is in the shared platform infrastructure or in service-specific implementation.
