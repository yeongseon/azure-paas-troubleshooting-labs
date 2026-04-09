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

# Flex Consumption Router Queueing Before Invocation

!!! info "Status: Planned"

## 1. Question

On Azure Functions Flex Consumption, what is the latency distribution between the request arriving at the Flex router and the function code beginning execution, and how does this "router queue time" vary under different load patterns?

## 2. Why this matters

Customers on Flex Consumption observe latency that cannot be explained by their function code execution time alone. The gap between request arrival and code invocation is spent in the Flex router's internal queue — waiting for an available instance, cold-starting a new instance, or routing to a warm instance. Understanding this hidden queue time is critical for setting realistic SLO expectations and choosing between Flex Consumption and other plans.

## 3. Customer symptom

- "My function takes 50ms to execute but the end-to-end latency is 3 seconds."
- "I see inconsistent latency — some requests are fast, others have a 2-5 second delay."
- "Application Insights shows function execution is fast but the overall duration is much longer."

## 4. Hypothesis

The Flex Consumption router introduces measurable queueing latency between request receipt and function invocation. This queue time will show:

1. Bimodal distribution: near-zero for warm instances, 1-5 seconds for cold allocations
2. Increased variance under burst load patterns
3. Correlation with the `always_ready` instance count setting

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

- Load pattern: steady (10 RPS), burst (0→100 RPS), periodic (10 RPS with 5-minute gaps)
- `always_ready` instance count: 0, 1, 3
- Function complexity: minimal (return immediately) vs medium (100ms CPU work)
- Request concurrency per run

**Observed:**

- End-to-end latency (client-measured)
- Function execution duration (Application Insights)
- Router queue time (calculated: end-to-end minus execution)
- Instance allocation events

**Independent run definition**: Fresh deployment with `always_ready` instances confirmed, 5-minute stabilization, identical load profile

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: First 2 minutes of steady load; no exclusion for burst patterns (burst IS the measurement)

**Primary metric**: Router queue time p95; meaningful effect threshold: 500ms absolute or 20% relative change

**Comparison method**: Mann-Whitney U on per-run p95 queue times

## 7. Instrumentation

- Application Insights: request traces with `duration` and custom `executionDuration` property
- Custom middleware: timestamp at function entry vs request receipt
- Azure Monitor: `FunctionExecutionCount`, `ActiveInstances`
- Load testing: k6 with precise request timing

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Router queue time is bimodal: <50ms for warm hits, 1-5s for cold allocations
- With `always_ready=0`, first requests in burst show 2-5s queue time
- With `always_ready=3`, queue time stays <200ms up to ~3× concurrency capacity
- p95 queue time is consistent across 5 runs within each configuration (±500ms)

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

- Flex Consumption instance allocation behavior may differ by region due to capacity
- `always_ready` instances take time to provision after deployment — verify they're actually running before starting the test
- Router queue time is not directly exposed as a metric; it must be calculated from timestamps

## 16. Related guide / official docs

- [Azure Functions Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [Azure Functions scaling and hosting](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
