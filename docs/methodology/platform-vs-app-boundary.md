---
hide:
  - toc
---

# Platform vs. Application Boundary

In Azure PaaS, the platform (infrastructure managed by Azure) and the application (customer code and configuration) share responsibility for request processing. Effective troubleshooting requires identifying which layer is responsible for an observed behavior.

## Why the boundary matters

Support engineers must quickly determine:

- Is this a **platform issue** that Azure needs to investigate or mitigate?
- Is this an **application issue** that the customer needs to address in their code or configuration?
- Is this a **shared-resource effect** where platform and application interact in ways that neither side fully controls?

Misattribution in either direction has consequences. Blaming the platform for an application bug wastes Azure engineering time. Blaming the application for a platform event leaves the customer unable to resolve the issue.

## Common boundary scenarios

### CPU and memory

- **Platform side:** instance migration, host patching, noisy neighbor on shared plans, cgroup limit enforcement
- **Application side:** inefficient algorithms, memory leaks, unbounded caching, thread pool exhaustion
- **Shared:** GC pressure in managed runtimes can look like platform CPU overhead; cgroup memory limits interact with application allocation patterns

### Network latency

- **Platform side:** load balancer routing changes, SNAT port exhaustion, platform DNS resolution delays
- **Application side:** slow dependency calls, connection pool misconfiguration, synchronous blocking on external services
- **Shared:** the platform terminates TLS and routes to the worker; delays at either handoff point are hard to attribute without distributed tracing

### Cold start

- **Platform side:** instance allocation, sandbox initialization, storage mount operations
- **Application side:** dependency loading, framework initialization, database connection warmup
- **Shared:** total cold start duration is the sum of both layers; isolating each requires platform-level tracing that is not always available to customers

### Health checks

- **Platform side:** probe configuration, probe routing through the load balancer, probe timeout enforcement
- **Application side:** health endpoint implementation, readiness vs. liveness semantics, startup duration
- **Shared:** a probe failure can be caused by the platform sending probes before the app is ready, or by the app failing to respond within the platform's timeout window

## Approach to boundary analysis

### 1. Collect both layers

Gather platform-level metrics (Azure Monitor, platform logs, detector output) and application-level telemetry (Application Insights, custom logging, procfs/cgroup data) for the same time window.

### 2. Compare timelines

Overlay platform events (instance movements, scaling operations, patches) with application events (deployments, error spikes, latency changes). Temporal correlation is the first signal, though it is not proof of causation.

### 3. Use ground-truth sources

Where available, procfs and cgroup data provide ground-truth measurements that are independent of both Azure Monitor aggregation and Application Insights sampling. These are especially valuable for memory and CPU analysis on Linux App Service.

### 4. Check for platform events

Azure platform events — instance migrations, storage failovers, networking changes — can cause transient disruption that looks like an application problem. Check the platform event timeline before attributing an issue to application code.

### 5. Test the boundary hypothesis

If you suspect a platform issue, test whether the behavior persists after scaling to a new instance (different host). If you suspect an application issue, test whether the behavior reproduces consistently across instances.

## Caution

!!! warning
    The boundary is not always clean. Shared resources — CPU, memory, disk, network — mean platform effects and application effects can overlap. A memory-intensive application may trigger platform-level cgroup enforcement, which in turn causes platform-level metrics to spike. In these cases, both layers are involved and the root cause analysis must account for the interaction.

The goal is not to assign blame to a single layer, but to identify the most actionable remediation path.
