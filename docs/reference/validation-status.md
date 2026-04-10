---
hide:
  - toc
---

# Validation Status

*Auto-generated on 2026-04-10 by `scripts/generate_validation_status.py`. Do not edit manually.*

## Overview

This dashboard tracks when each experiment was last validated against a real Azure environment.

- **Staleness threshold**: 90 days
- **Validation methods**: `az_cli` (manual CLI), `bicep` (IaC), `terraform` (IaC)

## Experiment Validation Status

| Experiment | Service | Status | az_cli | bicep | terraform | Last Tested | Staleness |
|---|---|---|---|---|---|---|---|
| [Memory Pressure](../app-service/memory-pressure/overview.md) | App Service | Published | ➖ | ➖ | ➖ | — | Not tested |
| [SNAT Exhaustion](../app-service/snat-exhaustion/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Health Check Eviction](../app-service/health-check-eviction/overview.md) | App Service | Published | ➖ | ➖ | ➖ | — | Not tested |
| [Filesystem Persistence](../app-service/filesystem-persistence/overview.md) | App Service | Published | ➖ | ➖ | ➖ | — | Not tested |
| [Custom DNS Resolution](../app-service/custom-dns-resolution/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [procfs Interpretation](../app-service/procfs-interpretation/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Slow Requests](../app-service/slow-requests/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Zip vs Container](../app-service/zip-vs-container/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Flex Router Queueing](../functions/flex-router-queueing/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [HTTP Concurrency Cliffs](../functions/http-concurrency-cliffs/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Telemetry Auth Blackhole](../functions/telemetry-auth-blackhole/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Flex Site Update Strategy](../functions/flex-site-update-strategy/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Flex Consumption Storage](../functions/flex-consumption-storage/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Cold Start](../functions/cold-start/overview.md) | Functions | Draft | ➖ | ➖ | ➖ | — | Not tested |
| [Dependency Visibility](../functions/dependency-visibility/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Scale-to-Zero 503](../container-apps/scale-to-zero-502/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Target Port Detection](../container-apps/target-port-detection/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [OOM Visibility Gap](../container-apps/oom-visibility-gap/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Custom DNS Forwarding](../container-apps/custom-dns-forwarding/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Ingress SNI / Host Header](../container-apps/ingress-sni-host-header/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Private Endpoint FQDN vs IP](../container-apps/private-endpoint-fqdn-vs-ip/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Startup Probes](../container-apps/startup-probes/overview.md) | Container Apps | Unknown | ➖ | ➖ | ➖ | — | Not tested |
| [MI RBAC Propagation](../cross-cutting/mi-rbac-propagation/overview.md) | Cross-cutting | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [PE DNS Negative Cache](../cross-cutting/pe-dns-negative-cache/overview.md) | Cross-cutting | Planned | ➖ | ➖ | ➖ | — | Not tested |

## Summary

| Metric | Count |
|---|---|
| Total experiments | 24 |
| Published | 3 |
| Draft | 1 |
| Planned | 19 |
| Tested (any method) | 0 |
| Stale (>90d) | 0 |

## Evidence Level Legend

| Emoji | Meaning |
|---|---|
| ✅ pass | Validated successfully |
| ❌ fail | Validation failed |
| ⚠️ stale | Passed but older than 90 days |
| ➖ | Not tested |
