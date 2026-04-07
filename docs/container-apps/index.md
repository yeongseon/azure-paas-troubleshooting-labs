# Container Apps Labs

Azure Container Apps troubleshooting experiments focused on ingress behavior, networking edge cases, and container lifecycle management.

## Experiment Status

| Experiment | Status | Description |
|-----------|--------|-------------|
| [Ingress SNI / Host Header](ingress-sni-host-header/overview.md) | Planned | SNI and host header routing behavior |
| [Private Endpoint FQDN vs IP](private-endpoint-fqdn-vs-ip/overview.md) | Planned | FQDN vs. direct IP access differences |
| [Startup Probes](startup-probes/overview.md) | **Draft — Awaiting Execution** | Probe interaction and failure patterns |

## Experiments

### [Ingress SNI / Host Header](ingress-sni-host-header/overview.md)

How Container Apps ingress handles Server Name Indication (SNI) and host header routing. Investigates edge cases with custom domains, mismatched headers, and multi-app environments where routing decisions may produce unexpected results.

### [Private Endpoint FQDN vs IP](private-endpoint-fqdn-vs-ip/overview.md)

Behavioral differences when accessing a Container App via private endpoint FQDN versus direct IP address. Investigates TLS validation, routing behavior, and failure modes specific to private network access patterns.

### [Startup Probes](startup-probes/overview.md) — *Draft — Awaiting Execution*

Interaction between startup, readiness, and liveness probes. Investigates failure patterns that emerge from misconfigured probe timing, threshold settings, and the order of probe evaluation during container initialization.

!!! info "MVP Experiment — Draft"
    This is one of three MVP experiments. The experiment design is complete but execution has not yet started. It will deploy Container Apps with configurable startup durations and test various probe configurations to document lifecycle behavior and restart patterns.

!!! note
    These experiments focus on the managed Container Apps environment and its ingress layer. Underlying Kubernetes control plane behavior is out of scope.

## Related Experiments in Other Services

- **App Service** — [Memory Pressure](../app-service/memory-pressure/overview.md) (**Published**) covers plan-level resource contention, relevant when comparing Container Apps scaling and resource isolation.
- **Functions** — [Cold Start](../functions/cold-start/overview.md) explores startup phase breakdown, which shares conceptual overlap with container startup probe timing and initialization sequencing.
