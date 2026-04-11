---
hide:
  - toc
---

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

## Experiment-backed mappings

| Customer Symptom | Experiment-backed Hypothesis | First Investigation Steps | Reference |
|-----------------|------------------------------|---------------------------|-----------|
| "Memory is 85% but app still responds" | Memory plateau can hide reclaim pressure; risk shifts to startup delays and restart cascade, not immediate steady-state outage | Correlate `MemoryPercentage` with cold-start trend, swap indicators, and restart spikes | [Memory Pressure](../app-service/memory-pressure/overview.md) |
| "Outbound API calls fail randomly while CPU looks fine" | SNAT exhaustion can cause `TimeoutError` with normal CPU/memory | Count concurrent outbound connections per destination and verify connection pooling usage | [SNAT Exhaustion](../app-service/snat-exhaustion/overview.md) |
| "One dependency failed and traffic disappeared from one instance" | Health check eviction is binary after threshold failures; unhealthy instance can drop from ~50% to 0% traffic instantly | Compare health probe failures to traffic split timeline and instance state transitions | [Health Check Eviction](../app-service/health-check-eviction/overview.md) |
| "Files disappear after deploy but not after restart" | Stop/start and deploy recreate container (local layer lost); `/home` persists across lifecycle events | Check write path and verify whether files are under `/home` or local writable layer | [Filesystem Persistence](../app-service/filesystem-persistence/overview.md) |
| "First request after idle is very slow but eventually works" | Scale-to-zero cold start is often 20-40s; no 503 may still occur if timeout budget is high | Confirm zero replicas before test, then map cold-request latency against scale-up events | [Scale-to-Zero 503](../container-apps/scale-to-zero-502/overview.md) |
| "Container is running but endpoint always times out" | Wrong `targetPort` on fresh revision can keep revision in Activating with startup probe failures | Compare ingress `targetPort` to app listen port in container logs and system probe failures | [Target Port Detection](../container-apps/target-port-detection/overview.md) |
| "503 upstream connect error appears after ingress change" | Wrong port on running revision tends to fail fast with Envoy connection refused | Validate recent ingress changes and test direct response after port correction | [Target Port Detection](../container-apps/target-port-detection/overview.md) |
| "Memory drops periodically but restart count stays flat" | Worker-level OOM kills can be invisible in system logs and restart metrics | Query console logs for SIGKILL and correlate with `WorkingSetBytes` sawtooth pattern | [OOM Visibility Gap](../container-apps/oom-visibility-gap/overview.md) |
| "Revision flaps unhealthy during deploy" | Probe budget shorter than actual startup time causes deterministic probe-driven restart loops | Compute startup budget vs measured startup time and inspect `ProbeFailed` sequence | [Startup Probes](../container-apps/startup-probes/overview.md) |
| "No restarts, but app never receives traffic" | Readiness can block routing while process remains alive; not always a crash problem | Separate readiness vs liveness outcomes in logs before escalating runtime failure | [Startup Probes](../container-apps/startup-probes/overview.md) |

### Quick interpretation tips

- Use experiment links to validate likely failure signatures before escalating to platform incidents.
- Prioritize hypotheses with reproducible evidence in section 11/14 of each experiment.
- If symptom and metric disagree, prefer logs and state-transition evidence over coarse averages.
- Treat probe-driven failures and port-mismatch failures as configuration defects first.

## Guidance

!!! warning
    Symptom-to-hypothesis mapping is a starting point, not a diagnosis. Multiple symptoms can share the same root cause, and a single symptom can have multiple independent causes. Always validate hypotheses against observed evidence before concluding.

See also:

- [False Positives](false-positives.md) — signals that suggest problems that don't exist
- [Metric Misreads](metric-misreads.md) — commonly misinterpreted Azure metrics
- [Platform vs App Boundary](../methodology/platform-vs-app-boundary.md) — framework for boundary analysis
