---
hide:
  - toc
validation:
  az_cli:
    last_tested: null
    result: not_tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Scale-to-Zero First Request 503/Timeout

!!! info "Status: Planned"

## 1. Question

When a Container App scales to zero replicas and the first request arrives, what is the latency distribution of that first request, and under what conditions does it result in a 503 or timeout rather than a delayed success?

## 2. Why this matters

Scale-to-zero is a key cost optimization feature, but it introduces cold-start latency. Customers expect the first request to be slow but successful. When it results in a 503 or timeout, the customer sees an outage rather than a delay. Understanding the conditions that cause failure vs. slow success helps support engineers guide customers toward appropriate min-replica settings and timeout configurations.

## 3. Customer symptom

- "The first request after idle always returns 503."
- "Users see a timeout error when the app hasn't been used for a while."
- "We set scale-to-zero for cost savings but now we have an unreliable service."

## 4. Hypothesis

The first request to a scaled-to-zero Container App will:

1. Succeed with 2-10 second latency if the container starts within the ingress timeout window
2. Return 503 if the container takes longer than the ingress timeout (default 240s, but envoy may have shorter internal timeouts)
3. Show high variance in first-request latency depending on image size, startup probe configuration, and registry pull speed

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (custom container) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Min replicas: 0
- Container image size: small (~50MB), medium (~200MB), large (~500MB)
- Startup probe: configured vs not configured
- Registry: ACR (same region) vs Docker Hub
- Idle time before first request: 5min, 15min, 30min

**Observed:**

- First request latency
- First request success/failure (HTTP status code)
- Container start time (from scale event to first successful health check)
- Image pull duration
- Subsequent request latency (warm baseline)

**Independent run definition**: Scale to zero confirmed (0 replicas for ≥5 minutes), then single cold request, measure response

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: No exclusion — the cold request IS the measurement

**Primary metric**: First-request latency; meaningful effect threshold: 2 seconds absolute or 50% relative change

**Comparison method**: Mann-Whitney U on first-request latencies across configurations

## 7. Instrumentation

- External HTTP client: precise request timing with timeout tracking
- Container Apps system logs: replica provisioning events, image pull logs
- Azure Monitor: `Replicas`, `Requests`, `RestartCount`
- Application logging: startup timestamp, first-request handling timestamp

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- First-request latency: 2-8 seconds for small images from ACR, 5-15 seconds for large images from Docker Hub
- 503 errors when container start exceeds ingress timeout
- Startup probe configuration reduces 503 rate by signaling readiness accurately
- High variance across runs (±2-5 seconds) due to infrastructure variability

## 10. Results

_Awaiting execution._

## 11. Interpretation

_Awaiting execution._

## 12. What this proves

_Awaiting execution._

## 13. What this does NOT prove

_Awaiting execution._

## 14. Support takeaway

_Awaiting execution._

## 15. Reproduction notes

- Scale-to-zero requires HTTP scaling rule with 0 min replicas
- Verify actual replica count is 0 before sending the test request
- ACR pull time is affected by image layer caching at the node level

## 16. Related guide / official docs

- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
