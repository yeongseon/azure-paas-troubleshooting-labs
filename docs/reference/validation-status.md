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
| [procfs Interpretation](../app-service/procfs-interpretation/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Slow Requests](../app-service/slow-requests/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Zip vs Container](../app-service/zip-vs-container/overview.md) | App Service | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Flex Consumption Storage](../functions/flex-consumption-storage/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Cold Start](../functions/cold-start/overview.md) | Functions | Draft | ➖ | ➖ | ➖ | — | Not tested |
| [Dependency Visibility](../functions/dependency-visibility/overview.md) | Functions | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Ingress SNI / Host Header](../container-apps/ingress-sni-host-header/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Private Endpoint FQDN vs IP](../container-apps/private-endpoint-fqdn-vs-ip/overview.md) | Container Apps | Planned | ➖ | ➖ | ➖ | — | Not tested |
| [Startup Probes](../container-apps/startup-probes/overview.md) | Container Apps | Unknown | ➖ | ➖ | ➖ | — | Not tested |

## Summary

| Metric | Count |
|---|---|
| Total experiments | 10 |
| Published | 1 |
| Draft | 1 |
| Planned | 7 |
| Tested (any method) | 0 |
| Stale (>90d) | 0 |

## Evidence Level Legend

| Emoji | Meaning |
|---|---|
| ✅ pass | Validated successfully |
| ❌ fail | Validation failed |
| ⚠️ stale | Passed but older than 90 days |
| ➖ | Not tested |
