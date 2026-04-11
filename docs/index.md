---
hide:
  - toc
---

# Azure PaaS Troubleshooting Labs

Reproducible experiments for Azure App Service, Azure Functions, and Azure Container Apps.

By Yeongseon Choe

---

This site documents hypothesis-driven experiments that reproduce failure modes, performance edge cases, and platform boundary ambiguities in Azure PaaS services. Each experiment records what was observed, what can be concluded, and what remains unproven.

The target audience is Azure support engineers, escalation engineers, and platform operators who need to distinguish between platform-side and application-side issues under real-world conditions.

This site is the troubleshooting companion to the [practical guide series](https://github.com/yeongseon?tab=repositories&q=practical-guide), not a replacement. The guides cover broad reference material; these labs cover deep, narrow investigation.

## Experiment Status Overview

| Service | Experiment | Status | Last Updated |
|---------|-----------|--------|-------------|
| App Service | [Filesystem Persistence](app-service/filesystem-persistence/overview.md) | **Published** | 2026-04 |
| App Service | [Health Check Eviction](app-service/health-check-eviction/overview.md) | **Published** | 2026-04 |
| App Service | [SNAT Exhaustion](app-service/snat-exhaustion/overview.md) | **Published** | 2026-04 |
| App Service | [Memory Pressure](app-service/memory-pressure/overview.md) | **Published** | 2025-07 |
| Container Apps | [Scale-to-Zero 503](container-apps/scale-to-zero-502/overview.md) | **Published** | 2026-04 |
| Container Apps | [Target Port Detection](container-apps/target-port-detection/overview.md) | **Published** | 2026-04 |
| Container Apps | [OOM Visibility Gap](container-apps/oom-visibility-gap/overview.md) | **Published** | 2026-04 |
| App Service | [Custom DNS Resolution](app-service/custom-dns-resolution/overview.md) | Planned | — |
| Functions | [Cold Start](functions/cold-start/overview.md) | Draft | — |
| Container Apps | [Startup Probes](container-apps/startup-probes/overview.md) | Draft | — |

!!! success "7 Experiments Published"
    Seven experiments across App Service and Container Apps have been completed with real Azure data. Each includes full evidence chains, raw data, and reproducible procedures.

## Getting Started

New to this project? Start here:

1. **Read the methodology** — [Experiment Framework](methodology/experiment-framework.md) explains the standardized structure every experiment follows.
2. **Understand evidence levels** — [Evidence Levels](methodology/evidence-levels.md) defines how findings are tagged with calibrated confidence.
3. **Browse published experiments** — Start with any experiment that matches your area of interest:
    - App Service: [Filesystem Persistence](app-service/filesystem-persistence/overview.md), [Health Check Eviction](app-service/health-check-eviction/overview.md), [SNAT Exhaustion](app-service/snat-exhaustion/overview.md)
    - Container Apps: [OOM Visibility Gap](container-apps/oom-visibility-gap/overview.md), [Scale-to-Zero 503](container-apps/scale-to-zero-502/overview.md), [Target Port Detection](container-apps/target-port-detection/overview.md)
4. **Check the glossary** — [Glossary](reference/glossary.md) defines key Azure and troubleshooting terms used throughout this site.

## Quick Links

- **[App Service Labs](app-service/index.md)** — Filesystem persistence, health check eviction, SNAT exhaustion, memory pressure (4 published)
- **[Container Apps Labs](container-apps/index.md)** — Scale-to-zero, target port detection, OOM visibility gap (3 published)
- **[Functions Labs](functions/index.md)** — Cold start, storage edge cases, dependency visibility (planned)
- **[Cross-cutting](cross-cutting/index.md)** — MI RBAC propagation, PE DNS negative caching
- **[Methodology](methodology/experiment-framework.md)** — Experiment framework, evidence model, interpretation guidelines
- **[Glossary](reference/glossary.md)** — Key terms and definitions

## Site Map

### Methodology

- [Experiment Framework](methodology/experiment-framework.md) — standardized structure for all experiments
- [Statistical Methods](methodology/statistical-methods.md) — repeated-run methodology for performance experiments
- [Evidence Levels](methodology/evidence-levels.md) — tagging system for calibrated confidence
- [Platform vs App Boundary](methodology/platform-vs-app-boundary.md) — framework for boundary analysis
- [Interpretation Guidelines](methodology/interpretation-guidelines.md) — how to read and communicate results

### App Service Labs

- [Filesystem Persistence](app-service/filesystem-persistence/overview.md) — /home vs writable layer data survival — **Published**
- [Health Check Eviction](app-service/health-check-eviction/overview.md) — cascading outage from partial dependency failure — **Published**
- [SNAT Exhaustion](app-service/snat-exhaustion/overview.md) — connection failures without CPU/memory pressure — **Published**
- [Memory Pressure](app-service/memory-pressure/overview.md) — plan-level degradation, swap thrashing, kernel page reclaim — **Published**
- [Custom DNS Resolution](app-service/custom-dns-resolution/overview.md) — private name resolution drift after VNet changes
- [procfs Interpretation](app-service/procfs-interpretation/overview.md) — /proc reliability and limits in Linux containers
- [Slow Requests](app-service/slow-requests/overview.md) — frontend timeout vs. worker-side delay vs. dependency latency
- [Zip Deploy vs Container](app-service/zip-vs-container/overview.md) — deployment method behavioral differences

### Container Apps Labs

- [Scale-to-Zero 503](container-apps/scale-to-zero-502/overview.md) — first-request failure modes after idle scale-down — **Published**
- [Target Port Detection](container-apps/target-port-detection/overview.md) — auto-detection failures causing 502 — **Published**
- [OOM Visibility Gap](container-apps/oom-visibility-gap/overview.md) — observability gaps for OOM kills — **Published**
- [Ingress SNI / Host Header](container-apps/ingress-sni-host-header/overview.md) — SNI and host header routing behavior
- [Private Endpoint FQDN vs IP](container-apps/private-endpoint-fqdn-vs-ip/overview.md) — FQDN vs. direct IP access differences
- [Startup Probes](container-apps/startup-probes/overview.md) — probe interaction and failure patterns — *Draft*

### Functions Labs

- [Flex Router Queueing](functions/flex-router-queueing/overview.md) — hidden latency between request arrival and invocation
- [HTTP Concurrency Cliffs](functions/http-concurrency-cliffs/overview.md) — per-instance degradation thresholds
- [Telemetry Auth Blackhole](functions/telemetry-auth-blackhole/overview.md) — monitoring misconfiguration preventing startup
- [Flex Consumption Storage](functions/flex-consumption-storage/overview.md) — storage identity misconfiguration edge cases
- [Cold Start](functions/cold-start/overview.md) — dependency initialization and cold start duration breakdown — *Draft*
- [Dependency Visibility](functions/dependency-visibility/overview.md) — outbound dependency observability limits

### Patterns

- [Symptom to Hypothesis](patterns/symptom-to-hypothesis.md) — common symptoms and investigation starting points
- [False Positives](patterns/false-positives.md) — signals that suggest problems that don't exist
- [Metric Misreads](patterns/metric-misreads.md) — commonly misinterpreted Azure metrics

## Background

See [About](about.md) for the full motivation, goals, and positioning of this project.
