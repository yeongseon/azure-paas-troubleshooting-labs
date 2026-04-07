# Functions Labs

Azure Functions troubleshooting experiments focused on cold start behavior, scaling edge cases, dependency visibility, and hosting model differences.

## Experiments

### [Flex Consumption Storage](flex-consumption-storage/overview.md)

Storage identity and misconfiguration edge cases in the Flex Consumption hosting plan. Investigates what happens when storage identity is changed, revoked, or misconfigured, and how the failure manifests to the developer.

### [Cold Start](cold-start/overview.md)

Dependency initialization impact on cold start duration. Breaks down the relative contribution of host startup, package restoration, framework initialization, and application code to total cold start time.

### [Dependency Visibility](dependency-visibility/overview.md)

Limitations of observing outbound dependency calls through Application Insights and platform telemetry. Tests what is visible, what is missing, and where correlation breaks down in distributed tracing scenarios.

!!! note
    Experiments cover both Consumption and Flex Consumption plans where applicable. Dedicated (App Service) plan behavior may differ.
