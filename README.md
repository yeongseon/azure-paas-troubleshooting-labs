# Azure PaaS Troubleshooting Labs

[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-paas-troubleshooting-labs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read this in: [한국어](README.ko.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md)

**Support-engineer-style troubleshooting experiments for Azure App Service, Azure Functions, and Azure Container Apps.**

By Yeongseon Choe

---

## Why this exists

Official Azure documentation is accurate, but it does not cover every edge case that surfaces in real-world support scenarios. Common gaps include:

- **Failure mode reproduction** — how specific failure conditions actually manifest, beyond what the docs describe
- **Platform vs. application boundary** — determining whether an issue originates in Azure infrastructure or customer application code
- **Misleading metrics** — signals that suggest one root cause but actually indicate another
- **Evidence calibration** — knowing what can be stated with confidence and what requires additional data

This repository fills those gaps through hypothesis-driven experiments. Each experiment reproduces a specific scenario, records observations, and interprets the results with explicit confidence levels.

This is not a practical guide, not a tutorial, and not a Microsoft Learn replacement.

## What it covers

### App Service

- **Memory Pressure** — plan-level degradation, swap thrashing, kernel page reclaim effects
- **procfs Interpretation** — reliability and limits of /proc data inside Linux containers
- **Slow Requests** — frontend timeout vs. worker-side delay vs. dependency latency
- **Zip Deploy vs Container** — behavioral differences across deployment methods

### Functions

- **Flex Consumption Storage** — storage identity misconfiguration edge cases
- **Cold Start** — dependency initialization, host startup sequence, cold start duration breakdown
- **Dependency Visibility** — limitations of observing outbound dependency behavior through available telemetry

### Container Apps

- **Ingress SNI / Host Header** — SNI and host header routing behavior, custom domain edge cases
- **Private Endpoint FQDN vs IP** — behavioral differences between FQDN and direct IP access
- **Startup Probes** — interaction between startup, readiness, and liveness probes

### Cross-cutting Patterns

- Symptom-to-hypothesis mapping
- False positives and misleading signals
- Common metric misreads

## Methodology

Each experiment follows a standardized structure:

**Question** → **Hypothesis** → **Environment** → **Procedure** → **Results** → **Interpretation** → **Limits** → **Support Takeaway**

This structure enforces separation between observed facts and interpretation, and requires every experiment to state both what it proves and what it does not prove.

See [Experiment Framework](docs/methodology/experiment-framework.md) for the full template.

## Evidence model

All experiments tag their findings with calibrated evidence levels:

| Tag | Meaning |
|-----|---------|
| **Observed** | Directly seen in logs, metrics, or system behavior |
| **Measured** | Quantitatively confirmed with specific values |
| **Correlated** | Two signals moved together; causation not established |
| **Inferred** | Reasonable conclusion drawn from observations |
| **Strongly Suggested** | Strong evidence, but not definitive |
| **Not Proven** | Hypothesis tested but not confirmed |
| **Unknown** | Insufficient data to determine |

See [Evidence Levels](docs/methodology/evidence-levels.md) for definitions and usage guidance.

## Related resources

This repository is the troubleshooting companion to the practical guide series. They are complementary, not overlapping.

| Resource | Role |
|----------|------|
| [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide) | Comprehensive App Service reference |
| [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide) | Comprehensive Functions reference |
| [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide) | Comprehensive Container Apps reference |
| [azure-monitoring-practical-guide](https://github.com/yeongseon/azure-monitoring-practical-guide) | Monitoring and observability reference |
| [lab-memory-pressure](https://github.com/yeongseon/lab-memory-pressure) | Individual lab: plan-level memory pressure (Flask + Node.js) |
| [lab-node-memory-pressure](https://github.com/yeongseon/lab-node-memory-pressure) | Individual lab: Node.js memory pressure on B1 Linux |

## Migration from Legacy Repos

This repository consolidates experiments previously hosted in individual repositories:

| Legacy Repository | Status | Migrated To |
|---|---|---|
| [lab-memory-pressure](https://github.com/yeongseon/lab-memory-pressure) | Archived | [App Service: Memory Pressure](docs/app-service/memory-pressure/overview.md) |
| [lab-node-memory-pressure](https://github.com/yeongseon/lab-node-memory-pressure) | Archived | [App Service: Memory Pressure](docs/app-service/memory-pressure/overview.md) (Node.js comparison) |

### Why Consolidate?

- **Discoverability**: Single location for all PaaS troubleshooting experiments
- **Cross-referencing**: Easy comparison across services (App Service vs Functions vs Container Apps)
- **Consistent methodology**: Shared experiment template and evidence model
- **Easier maintenance**: Single documentation site, unified CI/CD

### Legacy Repo Policy

Legacy repositories are archived but remain accessible for reference. New experiments should be added to this consolidated repository.

## Disclaimer

This project is an independent community project and is not affiliated with,
endorsed by, or maintained by Microsoft.

Azure, Azure App Service, Azure Functions, and Azure Container Apps are trademarks of Microsoft Corporation.

## License

MIT
