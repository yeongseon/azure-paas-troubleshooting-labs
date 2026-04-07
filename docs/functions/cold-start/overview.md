# Cold Start and Dependency Initialization

!!! info "Status: Planned"

## Question

What is the relative contribution of host startup, package restoration, framework initialization, and application code execution to total cold start duration on Azure Functions?

## Why this matters

Cold start duration is a top concern for serverless workloads. Customers frequently ask "why does my first request take 10 seconds?" but the answer depends on which phase dominates. Without a breakdown, optimization efforts may target the wrong phase — for example, reducing application init code when the bottleneck is actually package restore or host startup.

## Customer symptom

"First request after idle takes 10+ seconds" or "Cold start is inconsistent — sometimes 3 seconds, sometimes 15."

## Planned approach

Deploy Functions with varying dependency sizes and initialization complexity on both Consumption and Flex Consumption plans. Instrument each startup phase (host init, package load, framework init, app code) using custom telemetry and trace markers. Compare cold start breakdown across configurations.

## Key variables

**Controlled:**

- Number and size of dependencies
- Application initialization complexity (minimal vs. heavy)
- Hosting plan (Consumption vs. Flex Consumption)
- Runtime (Python, Node.js)

**Observed:**

- Total cold start duration (time to first response)
- Per-phase duration breakdown
- Consistency across multiple cold starts
- Impact of dependency count on total duration

## Expected evidence tags

Measured, Correlated, Inferred

## Related resources

- [Microsoft Learn: Azure Functions cold start](https://learn.microsoft.com/en-us/azure/azure-functions/event-driven-scaling#cold-start)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
