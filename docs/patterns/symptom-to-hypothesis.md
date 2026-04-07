# Symptom to Hypothesis Mapping

A reference for common customer-reported symptoms and the hypotheses worth investigating first. This is not exhaustive — it is a structured starting point for investigation.

## How to use this table

1. Match the customer's reported symptom to the closest entry
2. Review the possible hypotheses in priority order
3. Start with the listed investigation steps
4. Use the [evidence levels](../methodology/evidence-levels.md) framework to tag your findings

## Common symptom mappings

| Customer Symptom | Possible Hypotheses | First Investigation Steps |
|-----------------|---------------------|--------------------------|
| "My app is slow" | Memory pressure, CPU throttling, dependency timeout, cold start, thread pool exhaustion | App Service plan metrics (CPU, memory), App Insights dependency calls, procfs memory stats |
| "App restarts randomly" | OOM kill, health check failure, platform instance migration, unhandled exception, deployment in progress | Container logs, platform event timeline, memory usage timeline, deployment history |
| "Intermittent 502/503 errors" | Instance recycling, health check timeout, deployment slot swap, scale-in event, upstream dependency failure | Platform events, load balancer health probe config, instance count timeline, error distribution across instances |
| "Cold start takes too long" | Large dependency tree, heavy framework initialization, storage mount delay, package restore, database warmup | Startup trace timeline, deployment package size, init code profiling, dependency count |
| "High CPU but app isn't doing much" | GC pressure, swap thrashing, noisy neighbor (shared plans), background threads, platform overhead | procfs CPU breakdown, cgroup stats, per-process CPU, GC metrics, thread count |
| "Connections timing out" | SNAT port exhaustion, DNS resolution delay, downstream service overload, connection pool misconfiguration | Outbound connection metrics, SNAT port usage, DNS TTL settings, connection pool stats |
| "Deployment succeeds but app doesn't start" | Missing environment variables, incorrect port binding, startup command error, image pull failure, dependency crash | Container startup logs, environment variable audit, port configuration, image pull status |
| "Metrics show high memory but app is fine" | Plan-level vs. app-level metric confusion, committed vs. working set, buffer/cache inclusion | Verify metric scope (plan vs. instance vs. app), check per-instance view, compare with procfs |
| "Requests succeed locally but fail on Azure" | Missing dependencies in deployment, environment variable differences, network policy blocking outbound, platform proxy behavior | Compare local vs. deployed environment, check NSG/firewall rules, verify outbound connectivity |
| "Latency spikes at specific times" | Scheduled scaling events, platform maintenance window, cron job contention, log rotation, certificate renewal | Correlate with platform event timeline, check scheduled tasks, review scaling history |

## Guidance

!!! warning
    Symptom-to-hypothesis mapping is a starting point, not a diagnosis. Multiple symptoms can share the same root cause, and a single symptom can have multiple independent causes. Always validate hypotheses against observed evidence before concluding.

See also:

- [False Positives](false-positives.md) — signals that suggest problems that don't exist
- [Metric Misreads](metric-misreads.md) — commonly misinterpreted Azure metrics
- [Platform vs App Boundary](../methodology/platform-vs-app-boundary.md) — framework for boundary analysis
