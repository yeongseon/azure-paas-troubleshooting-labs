# Startup, Readiness, and Liveness Probe Interactions

!!! info "Status: Planned"

## Question

How do startup, readiness, and liveness probes interact in Azure Container Apps, and what failure patterns emerge from misconfigured probe timing or threshold settings?

## Why this matters

Container Apps supports all three Kubernetes-style probe types. Misconfigured probes are a frequent cause of containers that restart unexpectedly, appear healthy but don't receive traffic, or take excessively long to become available. The interaction between probe types — particularly the handoff from startup probe to liveness probe — creates edge cases that are not intuitive from the documentation alone.

## Customer symptom

"Container keeps restarting" or "App shows healthy but doesn't receive traffic" or "App takes 5 minutes to start receiving requests after deployment."

## Planned approach

Deploy a Container App with configurable startup duration. Test probe configurations: (1) startup probe too short for actual startup time, (2) liveness probe starting before startup completes (no startup probe configured), (3) readiness probe failing during initialization, (4) all three probes configured with tight thresholds. Document the container lifecycle behavior, restart count, and traffic routing state for each scenario.

## Key variables

**Controlled:**

- Application startup duration (configurable delay)
- Startup probe: initialDelaySeconds, periodSeconds, failureThreshold
- Readiness probe: same parameters
- Liveness probe: same parameters

**Observed:**

- Container restart count and timing
- Traffic routing state (receiving vs. not receiving)
- Probe success/failure logs
- Time from deployment to first successful request
- Container state transitions

## Expected evidence tags

Observed, Measured, Correlated

## Related resources

- [Microsoft Learn: Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
