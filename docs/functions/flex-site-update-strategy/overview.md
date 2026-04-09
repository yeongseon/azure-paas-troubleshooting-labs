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

# Flex Consumption Site Update Strategy and In-Flight Behavior

!!! info "Status: Planned"

## 1. Question

When a new version is deployed to a Flex Consumption function app, what happens to in-flight requests, and what is the latency impact during the deployment transition? Does the platform use blue-green, rolling, or stop-start deployment?

## 2. Why this matters

Zero-downtime deployment is critical for production workloads. Customers deploying frequently need to understand whether in-flight requests are drained gracefully, dropped, or routed to the new version mid-execution. The deployment strategy also affects cold start frequency — if all instances are replaced simultaneously, there is a "thundering herd" cold start.

## 3. Customer symptom

- "We see a burst of errors every time we deploy."
- "Some requests get 503 during deployment, even though we deploy several times a day."
- "After deployment, the first few requests are slow — feels like all instances cold-start at once."

## 4. Hypothesis

Flex Consumption uses a rolling update strategy where:

1. New instances are provisioned with the new version before old instances are drained
2. In-flight requests on old instances are allowed to complete (graceful drain with timeout)
3. There is a brief overlap period where both old and new versions serve requests
4. The latency spike during deployment correlates with the number of instances being replaced

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| SKU / Plan | Flex Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Deployment method: `az functionapp deploy`, VS Code, GitHub Actions
- Load during deployment: steady 20 RPS
- Function execution duration: 100ms, 5s, 30s (to test drain behavior)
- Instance count: always_ready=2

**Observed:**

- Request success/failure rate during deployment window
- Latency distribution before, during, and after deployment
- Instance version serving each request (custom version header)
- In-flight request completion or cancellation
- Cold start count after deployment

**Independent run definition**: Stable baseline for 5 minutes, then deploy new version, measure for 10 minutes after

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: No exclusion — deployment transition IS the measurement

**Primary metric**: Error rate during deployment window; meaningful effect threshold: any errors >0%

**Comparison method**: Directional comparison across deployment methods

## 7. Instrumentation

- Application Insights: request traces with custom `app_version` property
- Custom middleware: version identification in response headers
- Azure Monitor: `FunctionExecutionCount`, `Http5xx`
- k6 load generator: continuous requests with per-request success/failure logging

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Brief error spike (0-5 seconds) during instance replacement
- Short-lived requests (100ms) see fewer errors than long-lived requests (30s)
- `always_ready` instances may help reduce the cold-start burst after deployment
- Deployment method may affect the transition strategy

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

- Deployment slot behavior on Flex Consumption may differ from standard Consumption
- The drain timeout is platform-controlled; verify current default
- Long-running functions (>5 minutes) may be forcefully terminated during deployment

## 16. Related guide / official docs

- [Azure Functions Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [Deployment best practices - Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-best-practices)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
