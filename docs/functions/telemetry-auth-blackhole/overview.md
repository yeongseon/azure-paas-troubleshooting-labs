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

# Telemetry Auth Can Stop the Host Before Code Runs

!!! info "Status: Planned"

## 1. Question

Can a misconfigured Application Insights connection (invalid connection string, expired managed identity token, or network-blocked telemetry endpoint) prevent the Azure Functions host from starting or cause it to crash before any function code executes?

## 2. Why this matters

Telemetry is typically considered a non-critical dependency — if logging fails, the app should still work. However, the Azure Functions host initialization includes telemetry provider setup. If this setup throws an unhandled exception or blocks on authentication, the host may fail to start entirely. This creates a counterintuitive failure: a monitoring configuration change (not a code change) causes a complete outage.

## 3. Customer symptom

- "We changed the Application Insights connection string and now the function app won't start."
- "No function executions are logged — not even startup errors in Application Insights, because Application Insights itself is the problem."
- "The function worked fine yesterday. We only changed monitoring settings."

## 4. Hypothesis

When the Application Insights connection string or managed identity authentication for telemetry is misconfigured:

1. The Functions host will fail during initialization and never reach function code execution
2. No telemetry will be emitted (because the telemetry system itself is broken)
3. The only evidence will be in platform-level logs (Kudu, diagnose and solve)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| SKU / Plan | Flex Consumption, Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Application Insights connection string: valid, invalid, empty, removed
- Authentication method: connection string key, managed identity (valid/invalid)
- Network: telemetry endpoint accessible vs blocked (NSG/firewall)

**Observed:**

- Host startup success/failure
- Function invocation availability
- Platform logs (Kudu/SCM site)
- Diagnose and Solve Problems blade findings

## 7. Instrumentation

- Kudu console: host log files (`/home/LogFiles/`)
- Azure Portal: Diagnose and Solve Problems
- Azure Monitor: `FunctionExecutionCount` (expected to be zero during failure)
- External HTTP probe: function endpoint availability

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Invalid connection string: host starts but telemetry silently fails (function works)
- Invalid managed identity for AI: host may fail to start or start with degraded telemetry
- Network-blocked telemetry endpoint: host starts but telemetry calls time out (function may be slow)
- Complete removal of AI settings: host starts normally, no telemetry

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

- Behavior may differ between Consumption and Flex Consumption plans
- The Functions host version affects telemetry initialization behavior
- Check both the in-process and isolated worker models if applicable

## 16. Related guide / official docs

- [Monitor Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-monitoring)
- [Configure monitoring for Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/configure-monitoring)
- [Application Insights connection strings](https://learn.microsoft.com/en-us/azure/azure-monitor/app/connection-strings)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
