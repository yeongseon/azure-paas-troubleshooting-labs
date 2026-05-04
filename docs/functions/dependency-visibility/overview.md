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

# Outbound Dependency Visibility Limitations

!!! warning "Status: Draft - Blocked"
    Execution blocked: Flex Consumption plan creation blocked by Azure Policy.

## 1. Question

What can and cannot be observed about outbound dependency calls through Application Insights and platform telemetry in Azure Functions?

## 2. Why this matters

When a Function App experiences slow responses, support engineers need to determine whether the bottleneck is in the function code or in a downstream dependency (database, API, storage). Application Insights auto-collects some dependency telemetry, but the coverage has gaps — certain HTTP clients, non-HTTP protocols, and custom SDK calls may not be tracked. Understanding these gaps prevents false conclusions about dependency behavior.

## 3. Customer symptom

"I see slow responses but can't tell which dependency is causing it" or "App Insights shows no dependency calls but my function definitely calls external services."

## 4. Hypothesis

Application Insights will provide uneven outbound dependency visibility across protocol and client choices: common instrumented HTTP stacks will appear automatically, while some SDK/direct TCP paths will require explicit instrumentation to maintain complete and correlated dependency traces.

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

- Dependency types (HTTP, SDK, direct TCP)
- HTTP client libraries (requests, aiohttp, httpx, urllib)
- Application Insights SDK configuration

**Observed:**

- Which dependency calls appear in App Insights automatically
- Which require manual instrumentation
- Correlation ID propagation across dependencies
- Missing or broken distributed traces

**Independent run definition**: One clean deployment state with fixed dependency call matrix and one full telemetry capture cycle.

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: Exclude first invocation burst after cold start; evaluate steady invocation windows only.

**Primary metric and meaningful-effect threshold**: Dependency visibility coverage ratio (captured calls / expected calls); meaningful effect is >=20% absolute coverage change.

**Comparison method**: Per-run coverage comparison with bootstrap confidence interval and directional consistency check.

## 7. Instrumentation

- Application Insights requests, dependencies, traces, and operation ID fields
- Custom telemetry around expected dependency call counts and protocol labels
- Function host logs for invocation boundaries and exception context
- Synthetic call harness that invokes each dependency pattern with deterministic sequence IDs
- KQL queries validating dependency presence, correlation, and latency attributes

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- HTTP clients with built-in telemetry hooks show higher automatic dependency visibility than unsupported/custom paths.
- Direct TCP and selected SDK paths show missing dependency rows unless manual tracking is added.
- Manual instrumentation improves coverage and correlation completeness for previously missing paths.
- Coverage differences are repeatable across runs for each client/protocol configuration.

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

- Keep dependency endpoints stable and low-latency so visibility gaps are not confused with transient failures.
- Add deterministic request IDs in payload/logs to reconcile expected vs. observed dependency entries.
- Run each client/protocol combination separately before mixed-mode runs.
- Ensure sampling configuration is fixed across runs to avoid artificial visibility changes.

## 16. Related guide / official docs

- [Microsoft Learn: Application Insights dependency tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-dependencies)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
- [azure-monitoring-practical-guide](https://github.com/yeongseon/azure-monitoring-practical-guide)
