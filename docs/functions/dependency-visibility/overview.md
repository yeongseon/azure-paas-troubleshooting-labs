# Outbound Dependency Visibility Limitations

!!! info "Status: Planned"

## Question

What can and cannot be observed about outbound dependency calls through Application Insights and platform telemetry in Azure Functions?

## Why this matters

When a Function App experiences slow responses, support engineers need to determine whether the bottleneck is in the function code or in a downstream dependency (database, API, storage). Application Insights auto-collects some dependency telemetry, but the coverage has gaps — certain HTTP clients, non-HTTP protocols, and custom SDK calls may not be tracked. Understanding these gaps prevents false conclusions about dependency behavior.

## Customer symptom

"I see slow responses but can't tell which dependency is causing it" or "App Insights shows no dependency calls but my function definitely calls external services."

## Planned approach

Deploy a Function App that calls multiple dependency types: HTTP APIs (using different HTTP clients), Azure Storage (SDK), Azure SQL, Redis, and custom TCP connections. Compare what Application Insights auto-collects versus what requires manual instrumentation. Test with both auto-instrumentation and explicit `TelemetryClient` tracking.

## Key variables

**Controlled:**

- Dependency types (HTTP, SDK, direct TCP)
- HTTP client libraries (requests, aiohttp, httpx, urllib)
- Application Insights SDK configuration

**Observed:**

- Which dependency calls appear in App Insights automatically
- Which require manual instrumentation
- Correlation ID propagation across dependencies
- Missing or broken distributed traces

## Expected evidence tags

Observed, Measured, Not Proven

## Related resources

- [Microsoft Learn: Application Insights dependency tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-dependencies)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
- [azure-monitoring-practical-guide](https://github.com/yeongseon/azure-monitoring-practical-guide)
