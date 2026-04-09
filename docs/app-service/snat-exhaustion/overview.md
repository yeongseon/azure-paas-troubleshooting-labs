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

# SNAT Exhaustion Without High CPU

!!! info "Status: Planned"

## 1. Question

Can SNAT port exhaustion cause connection failures and latency spikes on App Service even when CPU and memory metrics remain normal, and what is the statistical distribution of failure rates across repeated runs?

## 2. Why this matters

Support engineers frequently look at CPU and memory first when customers report intermittent connection failures. SNAT exhaustion is invisible in those metrics — it appears only in connection failure counts and outbound connection metrics. Misattributing SNAT failures to application code leads to wasted debugging cycles.

## 3. Customer symptom

- "My app randomly fails to connect to external APIs, but CPU is only at 20%."
- "We see intermittent `SocketException` or `HttpRequestException` in our logs."
- "The problem comes and goes — sometimes 5% of requests fail, sometimes 25%."

## 4. Hypothesis

When an App Service application opens more than ~128 concurrent outbound connections to a single destination IP:port without connection pooling, SNAT port exhaustion will cause connection failures with no corresponding CPU or memory increase. The failure rate will be proportional to the degree of port exhaustion.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1, P1v3 (comparison) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Outbound connection count (ramp from 50 to 300 concurrent connections)
- Target endpoint (single external IP)
- Connection pooling: disabled (to trigger exhaustion) vs enabled (control)
- Request rate and duration per run

**Observed:**

- Connection failure rate
- Outbound SNAT connection count (Azure Monitor)
- Response latency (p50, p95, p99)
- CPU and memory percentage (to confirm they stay normal)

**Independent run definition**: Fresh deployment, 5-minute stabilization, identical load profile

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: First 2 minutes after load ramp begins

**Primary metric**: Connection failure rate; meaningful effect threshold: 1 percentage point absolute change

**Comparison method**: Mann-Whitney U on per-run failure rates

## 7. Instrumentation

- Application Insights: request traces, dependency calls, exception telemetry
- Azure Monitor: `TcpConnectionsOutbound`, `CpuPercentage`, `MemoryPercentage`
- Custom application logging: per-request connection attempt/failure timestamps
- Load testing: Locust or k6 with controlled concurrency levels

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Connection failure rate increases sharply when concurrent outbound connections exceed ~128 per destination
- CPU and memory remain under 30%
- `TcpConnectionsOutbound` in `TimeWait` state increases
- Failure rate is consistent across 5 independent runs (±5 percentage points)

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

- SNAT behavior depends on the number of instances and the Azure load balancer configuration
- Premium plans may have different SNAT port allocation than Basic plans
- Results may vary by region due to different load balancer configurations

## 16. Related guide / official docs

- [Troubleshoot outbound connection errors - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-intermittent-outbound-connection-errors)
- [SNAT for outbound connections - Azure Load Balancer](https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-outbound-connections)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
