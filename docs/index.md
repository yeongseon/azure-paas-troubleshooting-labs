# Azure PaaS Troubleshooting Labs

Reproducible experiments for Azure App Service, Azure Functions, and Azure Container Apps.

By Yeongseon Choe

---

This site documents hypothesis-driven experiments that reproduce failure modes, performance edge cases, and platform boundary ambiguities in Azure PaaS services. Each experiment records what was observed, what can be concluded, and what remains unproven.

The target audience is Azure support engineers, escalation engineers, and platform operators who need to distinguish between platform-side and application-side issues under real-world conditions.

This site is the troubleshooting companion to the [practical guide series](https://github.com/yeongseon?tab=repositories&q=practical-guide), not a replacement. The guides cover broad reference material; these labs cover deep, narrow investigation.

## Site map

### Methodology

- [Experiment Framework](methodology/experiment-framework.md) — standardized structure for all experiments
- [Evidence Levels](methodology/evidence-levels.md) — tagging system for calibrated confidence
- [Platform vs App Boundary](methodology/platform-vs-app-boundary.md) — framework for boundary analysis
- [Interpretation Guidelines](methodology/interpretation-guidelines.md) — how to read and communicate results

### App Service Labs

- [Memory Pressure](app-service/memory-pressure/overview.md) — plan-level degradation, swap thrashing, kernel page reclaim
- [procfs Interpretation](app-service/procfs-interpretation/overview.md) — /proc reliability and limits in Linux containers
- [Slow Requests](app-service/slow-requests/overview.md) — frontend timeout vs. worker-side delay vs. dependency latency
- [Zip Deploy vs Container](app-service/zip-vs-container/overview.md) — deployment method behavioral differences

### Functions Labs

- [Flex Consumption Storage](functions/flex-consumption-storage/overview.md) — storage identity misconfiguration edge cases
- [Cold Start](functions/cold-start/overview.md) — dependency initialization and cold start duration breakdown
- [Dependency Visibility](functions/dependency-visibility/overview.md) — outbound dependency observability limits

### Container Apps Labs

- [Ingress SNI / Host Header](container-apps/ingress-sni-host-header/overview.md) — SNI and host header routing behavior
- [Private Endpoint FQDN vs IP](container-apps/private-endpoint-fqdn-vs-ip/overview.md) — FQDN vs. direct IP access differences
- [Startup Probes](container-apps/startup-probes/overview.md) — probe interaction and failure patterns

### Patterns

- [Symptom to Hypothesis](patterns/symptom-to-hypothesis.md) — common symptoms and investigation starting points
- [False Positives](patterns/false-positives.md) — signals that suggest problems that don't exist
- [Metric Misreads](patterns/metric-misreads.md) — commonly misinterpreted Azure metrics

## Background

See [About](about.md) for the full motivation, goals, and positioning of this project.
