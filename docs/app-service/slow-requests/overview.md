# Slow Requests Under Pressure

!!! info "Status: Planned"

## Question

When an App Service worker is under memory or CPU pressure, how do slow requests manifest in telemetry, and can we distinguish frontend (ARR) timeout from worker-side processing delay from downstream dependency latency?

## Why this matters

"Slow requests" is one of the most common support symptoms, but the root cause can originate at three different layers: the platform frontend/load balancer (ARR), the application worker, or a downstream dependency. Each layer produces different diagnostic signals, and misidentifying the layer wastes investigation time.

Support engineers need a reliable method to determine which layer is responsible based on available telemetry.

## Customer symptom

"Some requests take 30+ seconds and then timeout" or "We see 504 errors but our app should respond in under a second."

## Planned approach

Deploy an application on App Service Linux that can simulate slow responses at each layer: (1) CPU-bound processing delay in the worker, (2) blocking call to a slow downstream dependency, (3) inducing platform-level queueing through worker thread exhaustion. Monitor the differences in Azure Monitor, Application Insights, and ARR logs across each scenario.

## Key variables

**Controlled:**

- Delay injection point (worker, dependency, thread pool)
- Delay duration
- Concurrent request load

**Observed:**

- Application Insights request duration vs. dependency duration
- ARR timeout logs (230-second default)
- HTTP status codes (504 vs. 500 vs. 200 slow)
- Time-to-first-byte vs. total response time

## Expected evidence tags

Measured, Correlated, Strongly Suggested

## Related resources

- [Microsoft Learn: Troubleshoot slow app performance](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-performance-degradation)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
