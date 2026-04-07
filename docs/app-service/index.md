# App Service Labs

Azure App Service troubleshooting experiments focused on worker behavior, memory management, deployment patterns, and platform/application boundary interpretation.

## Experiment Status

| Experiment | Status | Description |
|-----------|--------|-------------|
| [Memory Pressure](memory-pressure/overview.md) | **Published** | Plan-level degradation, swap thrashing, kernel page reclaim |
| [procfs Interpretation](procfs-interpretation/overview.md) | Planned | /proc reliability and limits in Linux containers |
| [Slow Requests](slow-requests/overview.md) | Planned | Frontend timeout vs. worker-side delay vs. dependency latency |
| [Zip Deploy vs Container](zip-vs-container/overview.md) | Planned | Deployment method behavioral differences |

## Experiments

### [Memory Pressure](memory-pressure/overview.md) — **Published**

Plan-level degradation under memory pressure. Investigates swap thrashing, kernel page reclaim effects, and cross-app impact on shared plans. Explores whether memory pressure manifests as CPU increase and how plan-level metrics can mislead per-app diagnosis.

??? success "Experiment Complete"
    This experiment has been executed and results are published. It covers B1/B2 Linux plans with multiple apps, measuring swap usage, page fault rates, CPU attribution, and cross-app latency impact.

### [procfs Interpretation](procfs-interpretation/overview.md)

Reliability and limits of reading `/proc` filesystem data inside App Service Linux containers. Examines where procfs values reflect the container vs. the host, and how cgroup v1/v2 boundaries affect metric interpretation.

### [Slow Requests](slow-requests/overview.md)

Diagnosing slow HTTP responses under pressure conditions. Distinguishes between frontend (ARR) timeout, worker-side processing delay, and downstream dependency latency. Tests how different bottleneck locations produce different diagnostic signals.

### [Zip Deploy vs Container](zip-vs-container/overview.md)

Behavioral differences between zip deployment and custom container deployment. Investigates startup time, file system behavior, environment variable handling, and troubleshooting signal availability across deployment methods.

!!! note
    These experiments target Linux App Service plans unless otherwise noted. Windows-specific behavior may differ.

## Related Experiments in Other Services

- **Functions** — [Cold Start](../functions/cold-start/overview.md) explores startup phase breakdown, which shares diagnostic overlap with App Service container startup behavior.
- **Container Apps** — [Startup Probes](../container-apps/startup-probes/overview.md) investigates container lifecycle management, relevant when comparing App Service custom container behavior.
