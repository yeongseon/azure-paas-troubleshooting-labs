# Container Apps Labs

Azure Container Apps troubleshooting experiments focused on ingress behavior, networking edge cases, and container lifecycle management.

## Experiments

### [Ingress SNI / Host Header](ingress-sni-host-header/overview.md)

How Container Apps ingress handles Server Name Indication (SNI) and host header routing. Investigates edge cases with custom domains, mismatched headers, and multi-app environments where routing decisions may produce unexpected results.

### [Private Endpoint FQDN vs IP](private-endpoint-fqdn-vs-ip/overview.md)

Behavioral differences when accessing a Container App via private endpoint FQDN versus direct IP address. Investigates TLS validation, routing behavior, and failure modes specific to private network access patterns.

### [Startup Probes](startup-probes/overview.md)

Interaction between startup, readiness, and liveness probes. Investigates failure patterns that emerge from misconfigured probe timing, threshold settings, and the order of probe evaluation during container initialization.

!!! note
    These experiments focus on the managed Container Apps environment and its ingress layer. Underlying Kubernetes control plane behavior is out of scope.
