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

# HTTP Concurrency Cliffs on Flex Consumption

!!! info "Status: Planned"

## 1. Question

At what HTTP concurrency level does a single Flex Consumption instance begin to degrade (increased latency, errors, or worker restarts), and is this cliff predictable and consistent across runs?

## 2. Why this matters

Flex Consumption allows configuring `http.maxConcurrentRequests` in `host.json`. Setting this too high overloads a single instance; setting it too low wastes instances. Customers need to know the practical concurrency ceiling — not the theoretical limit — so they can configure scaling triggers appropriately. The "cliff" behavior (sudden degradation rather than gradual) is particularly dangerous because monitoring may not catch it until requests are already failing.

## 3. Customer symptom

- "Everything is fine at 50 concurrent requests but at 80 it suddenly falls apart."
- "We increased maxConcurrentRequests to 200 and now we're seeing 500 errors."
- "Latency is stable until we hit some threshold, then p99 goes from 200ms to 30 seconds."

## 4. Hypothesis

Each Flex Consumption instance has a practical concurrency ceiling that depends on the function's resource consumption (CPU, memory, I/O). Beyond this ceiling:

1. Latency increases non-linearly (cliff behavior, not gradual degradation)
2. The cliff point is reproducible across runs (±10% variance)
3. The cliff point correlates with CPU saturation or memory pressure, not just request count

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

- Concurrency ramp: 10, 25, 50, 75, 100, 150, 200 concurrent requests
- Function payload: CPU-light (JSON parse), CPU-medium (image resize), I/O-bound (HTTP call)
- `maxConcurrentRequests`: 100, 200, unbounded
- Duration per concurrency level: 5 minutes steady state

**Observed:**

- Response latency distribution (p50, p95, p99) per concurrency level
- Error rate per concurrency level
- Worker restart events
- Memory and CPU consumption per instance

**Independent run definition**: Fresh deployment, single instance pinned (always_ready=1, max scale=1), identical ramp profile

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: First 2 minutes at each concurrency level

**Primary metric**: p95 latency; meaningful effect threshold: 2× increase from previous concurrency step

**Comparison method**: Per-run cliff detection; Mann-Whitney U comparing cliff-point concurrency across runs

## 7. Instrumentation

- Application Insights: request traces, performance counters
- Custom function middleware: per-request timing, concurrent request counter
- Azure Monitor: `ProcessCpuPercentage`, `ProcessMemoryMB`
- k6 load generator with step-up concurrency profile

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Latency remains stable up to a concurrency threshold, then increases sharply
- The cliff point varies by function type: CPU-light ~100-150, CPU-medium ~50-75, I/O-bound ~75-100
- Error rate transitions from 0% to >5% within a single concurrency step at the cliff
- Cliff point is consistent across 5 runs (±10 concurrent requests)

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

- Pin to a single instance using `always_ready=1` and maximum instance count=1 to isolate per-instance behavior
- Flex Consumption instance sizes may vary; check actual CPU/memory allocation
- Worker process recycling can reset the concurrency state mid-test

## 16. Related guide / official docs

- [Azure Functions Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [host.json reference - HTTP settings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-host-json#http)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
