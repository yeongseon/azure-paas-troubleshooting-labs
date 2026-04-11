---
hide:
  - toc
---

# Container Apps Labs

Azure Container Apps troubleshooting experiments focused on ingress behavior, container lifecycle, OOM observability, networking edge cases, and scaling patterns.

## Architecture Overview

Azure Container Apps is a managed container platform built on Kubernetes. Understanding the ingress, scaling, and container lifecycle components is essential for diagnosing where failures originate.

```mermaid
graph TB
    subgraph "Azure Container Apps Environment"
        Client([Client]) --> ENVOY[Envoy Proxy<br/>Ingress Controller]

        ENVOY --> REV1[Revision 1<br/>Active]
        ENVOY --> REV2[Revision 2<br/>Inactive]

        subgraph "Revision (Active)"
            direction TB
            REV1 --> R1[Replica 1]
            REV1 --> R2[Replica 2]

            subgraph "Replica"
                direction LR
                R1 --> APP[App Container<br/>Target Port]
                R1 --> SIDE[Sidecar<br/>Optional]
            end
        end

        KEDA[KEDA<br/>Scale Controller] --> REV1
        KEDA --> |"scale to 0<br/>when idle"| ZERO([0 Replicas])

        subgraph "Container Resources"
            direction LR
            VCPU[vCPU<br/>0.25 - 4]
            CMEM[Memory<br/>0.5Gi - 8Gi]
            CGROUP[cgroup<br/>Memory Limit]
        end

        CGROUP --> |"OOM Kill"| APP

        PROBE[Startup / Readiness<br/>/ Liveness Probes] --> APP
    end

    subgraph "Logging & Metrics"
        SYSLOG[ContainerAppSystemLogs]
        CONLOG[ContainerAppConsoleLogs]
        METRICS[Azure Monitor Metrics]
    end

    APP --> CONLOG
    REV1 --> SYSLOG
    REV1 --> METRICS

    style ENVOY fill:#4a9eff,color:#fff
    style KEDA fill:#ff9800,color:#fff
    style CGROUP fill:#e91e63,color:#fff
    style PROBE fill:#9c27b0,color:#fff
    style CONLOG fill:#4caf50,color:#fff
    style SYSLOG fill:#607d8b,color:#fff
```

### Key Components for Troubleshooting

| Component | Role | Why It Matters |
|-----------|------|---------------|
| **Envoy Proxy** | Ingress controller handling HTTP routing and TLS | Target port misconfiguration, SNI routing, and host header handling happen here |
| **Revision** | Immutable deployment unit containing replica configuration | Traffic splitting, blue-green deployment, and rollback operate at revision level |
| **Replica** | Running container instance within a revision | Each replica has its own cgroup memory limit; OOM kills target processes inside |
| **KEDA** | Event-driven autoscaler | Scale-to-zero creates cold start latency; scaling decisions affect availability |
| **cgroup Memory Limit** | Kernel-enforced memory boundary per container | OOM kills are invisible in system logs when multi-process servers absorb worker kills |
| **Probes** | Startup, readiness, and liveness health checks | Misconfigured probe timing causes restart loops or premature traffic routing |
| **ContainerAppConsoleLogs** | Application stdout/stderr captured as logs | Often the ONLY evidence source for worker-level OOM kills |
| **ContainerAppSystemLogs** | Platform lifecycle events (start, stop, crash) | Does NOT capture worker-level OOM kills when PID 1 survives |

!!! note
    These experiments focus on the managed Container Apps environment and its Envoy ingress layer. Underlying Kubernetes control plane behavior is out of scope.

## Experiment Status

| Experiment | Status | Description |
|-----------|--------|-------------|
| [Scale-to-Zero 503](scale-to-zero-502/overview.md) | **Published** | First-request failure modes after idle scale-down |
| [Target Port Detection](target-port-detection/overview.md) | **Published** | Auto-detection failures causing 502 on running containers |
| [OOM Visibility Gap](oom-visibility-gap/overview.md) | **Published** | Observability gaps across metrics and logs for OOM kills |
| [Custom DNS Forwarding](custom-dns-forwarding/overview.md) | **Published** | Outbound resolution failure with unreachable custom DNS |
| [Ingress SNI / Host Header](ingress-sni-host-header/overview.md) | **Published** | SNI and host header routing behavior |
| [Private Endpoint FQDN vs IP](private-endpoint-fqdn-vs-ip/overview.md) | **Published** | FQDN vs. direct IP access differences |
| [Startup Probes](startup-probes/overview.md) | **Published** | Probe interaction and failure patterns |

## Published Experiments

### [Scale-to-Zero 503](scale-to-zero-502/overview.md) — **Published**

First-request failure modes after idle scale-down to zero replicas. Documents the cold start window where incoming requests receive 503 errors or experience extended timeouts while the first replica initializes.

??? success "Experiment Complete"
    Completed 2026-04 on Consumption tier (koreacentral). Captures the activation delay, error codes, and the timeline from zero replicas to first successful response.

### [Target Port Detection](target-port-detection/overview.md) — **Published**

Auto-detection failures causing 502 errors on running containers. Demonstrates how Container Apps' ingress port auto-detection can select the wrong port, causing all traffic to fail even though the container is healthy and listening.

??? success "Experiment Complete"
    Completed 2026-04 on Consumption tier (koreacentral). Documents the auto-detection algorithm behavior and the specific conditions that cause detection failure.

### [OOM Visibility Gap](oom-visibility-gap/overview.md) — **Published**

Observability gaps across Azure Monitor metrics, system logs, and console logs when containers are OOM-killed. Reveals that multi-process servers (gunicorn) absorb worker OOM kills without triggering any platform-level telemetry — console logs are the only evidence source.

??? success "Experiment Complete"
    Completed 2026-04 on Consumption tier (koreacentral). Five OOM kills across two variants (gradual and spike). WorkingSetBytes underreports peaks by 2.4×; RestartCount stays 0; SystemLogs contain zero events.

### [Startup Probes](startup-probes/overview.md) — **Published**

Interaction between startup, readiness, and liveness probes. Investigates failure patterns that emerge from misconfigured probe timing, threshold settings, and the order of probe evaluation during container initialization.

??? success "Experiment Complete"
    Completed 2026-04 on Consumption tier (koreacentral). Four probe scenarios tested: startup-only failure, no-startup with liveness, readiness-only failure, and combined aggressive probes. Documents restart cascades, traffic routing gaps, and probe handoff timing.
### [Ingress SNI / Host Header](ingress-sni-host-header/overview.md) — **Published**

How Container Apps ingress handles Server Name Indication (SNI) and host header routing. Demonstrates that Envoy routes by Host header (not SNI), SNI is required for TLS admission, and any app in a shared environment can be reached by manipulating the Host header.

??? success "Experiment Complete"
    Completed 2026-04 on Consumption tier (koreacentral). Eight SNI/Host permutations tested across 3 runs with 100% reproducibility. Key finding: Host header is the routing key; SNI is only a TLS admission gate.

### [Custom DNS Forwarding](custom-dns-forwarding/overview.md) — **Published**

Outbound resolution failure when custom DNS servers configured in the Container Apps environment become unreachable. Demonstrates that there is no DNS fallback to Azure Default DNS, that recovery requires VNet DNS change + propagation time + new revision, and that DNS failure also breaks platform-level operations (ACR image pulls).

??? success "Experiment Complete"
    Completed 2026-04-11 on Consumption tier (VNet-injected, koreacentral). 54 probes across 4 phases. All 4 hypothesis points confirmed; unexpected finding that recovery is asymmetric — breaking DNS takes ~30s but restoring takes 2-5 minutes.

### [Private Endpoint FQDN vs IP](private-endpoint-fqdn-vs-ip/overview.md) — **Published**

Behavioral differences when accessing a Container App via private endpoint FQDN versus direct IP address. Demonstrates that direct IP access fails at the TLS level due to missing SNI — not certificate validation — and that `curl --resolve` is the correct workaround.

??? success "Experiment Complete"
    Completed 2026-04-12 on Consumption tier (internal-only, VNet-injected, koreacentral). 10 access patterns tested across 5 runs with 100% reproducibility. Key finding: SNI is mandatory for TLS admission; `-k` and `-H Host:` do not help because the failure occurs before certificate presentation and before HTTP layer processing.

## Related Experiments in Other Services

- **App Service** — [Memory Pressure](../app-service/memory-pressure/overview.md) (**Published**) covers plan-level resource contention, relevant when comparing Container Apps scaling and resource isolation.
- **App Service** — [Health Check Eviction](../app-service/health-check-eviction/overview.md) (**Published**) investigates health check cascading failures, conceptually similar to probe misconfiguration in Container Apps.
- **Cross-cutting** — [PE DNS Negative Cache](../cross-cutting/pe-dns-negative-cache/overview.md) tests DNS negative caching during private endpoint cutover, affecting Container Apps with VNet integration.
