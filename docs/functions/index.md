# Functions Labs

Azure Functions troubleshooting experiments focused on cold start behavior, scaling edge cases, dependency visibility, and hosting model differences.

## Experiment Status

| Experiment | Status | Description |
|-----------|--------|-------------|
| [Flex Consumption Storage](flex-consumption-storage/overview.md) | Planned | Storage identity misconfiguration edge cases |
| [Cold Start](cold-start/overview.md) | **Draft — Awaiting Execution** | Dependency initialization and cold start duration breakdown |
| [Dependency Visibility](dependency-visibility/overview.md) | Planned | Outbound dependency observability limits |

## Experiments

### [Flex Consumption Storage](flex-consumption-storage/overview.md)

Storage identity and misconfiguration edge cases in the Flex Consumption hosting plan. Investigates what happens when storage identity is changed, revoked, or misconfigured, and how the failure manifests to the developer.

### [Cold Start](cold-start/overview.md) — *Draft — Awaiting Execution*

Dependency initialization impact on cold start duration. Breaks down the relative contribution of host startup, package restoration, framework initialization, and application code to total cold start time.

!!! info "MVP Experiment — Draft"
    This is one of three MVP experiments. The experiment design is complete but execution has not yet started. It will deploy Functions with varying dependency sizes on Consumption and Flex Consumption plans to measure cold start phase breakdown.

### [Dependency Visibility](dependency-visibility/overview.md)

Limitations of observing outbound dependency calls through Application Insights and platform telemetry. Tests what is visible, what is missing, and where correlation breaks down in distributed tracing scenarios.

!!! note
    Experiments cover both Consumption and Flex Consumption plans where applicable. Dedicated (App Service) plan behavior may differ.

## Related Experiments in Other Services

- **App Service** — [Memory Pressure](../app-service/memory-pressure/overview.md) (**Published**) investigates plan-level resource contention, a pattern also relevant to understanding Functions scaling behavior.
- **Container Apps** — [Startup Probes](../container-apps/startup-probes/overview.md) covers container lifecycle management, which parallels cold start initialization sequencing in Functions.
