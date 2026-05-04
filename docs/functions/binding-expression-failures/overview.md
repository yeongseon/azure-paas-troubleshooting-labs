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

# Binding Expression Failures and Silent Misconfiguration

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When Azure Functions binding expressions (e.g., `%SETTING_NAME%`, `{queueTrigger}`, `@Microsoft.KeyVault(...)`) are malformed or reference non-existent resources, how do the failures manifest? Are binding errors surfaced at host startup, at function registration, or only at invocation time?

## 2. Why this matters

Binding expressions in `function.json` or decorator attributes are a powerful but brittle feature. A malformed expression can:
- Prevent the entire Function App from starting (host startup failure)
- Allow the host to start but cause all invocations of that function to fail
- Silently use a default value or literal string instead of the intended value
- Create hard-to-diagnose failures when app settings referenced in bindings don't exist in the deployed environment

## 3. Customer symptom

- "The function works locally but fails in Azure — no error in the code."
- "We can see the function in the portal but it never executes."
- "The trigger stopped working after we renamed an app setting."
- "Our output binding writes to the wrong blob container — it seems to be ignoring our expression."

## 4. Hypothesis

**H1 — Missing app setting in expression causes startup failure**: If a trigger binding references `%QUEUE_NAME%` and `QUEUE_NAME` is not defined in app settings, the host fails to start or the function fails to register.

**H2 — Malformed Key Vault reference causes silent fallback**: A binding expression referencing a Key Vault setting (`%@Microsoft.KeyVault(...)%`) that fails to resolve causes the host to use a literal string rather than failing.

**H3 — Expression failure timing differs by binding type**: Trigger binding expression failures are detected at startup (trigger cannot be configured). Output binding expression failures may only occur at invocation time (when the output binding is used).

**H4 — Python v2 decorator expressions differ from function.json**: In the Python v2 programming model, binding expressions in decorators are evaluated at code load time, not at trigger time. A missing app setting causes an import error rather than a runtime error.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Functions |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (isolated worker) |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config + Failure Mode

**Controlled:**

- Expression type: `%SETTING%`, `{triggerData}`, Key Vault reference
- Setting presence: defined, undefined, wrong value
- Binding role: trigger, input binding, output binding
- Programming model: v1 (function.json) vs. v2 (decorator)

**Observed:**

- Host startup success/failure
- Function registration success/failure
- Error message text (location in logs: host, worker, or app insights)
- Invocation outcome for misconfigured binding

## 7. Instrumentation

- App Insights: traces from host (`azure-functions-host`) at startup
- Function registration events: `Loaded function: <name>` in host logs
- Invocation result: success/failure and error message

**Host startup log filter:**

```kusto
traces
| where cloud_RoleName == "func-binding-test"
| where message contains "function" or message contains "binding" or message contains "error"
| where timestamp > ago(5m)
| project timestamp, message, severityLevel
| order by timestamp asc
```

## 8. Procedure

### 8.1 Scenarios

**S1 — Missing setting in trigger**: Queue trigger references `%NONEXISTENT_QUEUE%`. Deploy without the setting. Observe host behavior.

**S2 — Missing setting in output binding**: HTTP trigger with Storage output binding referencing `%NONEXISTENT_CONTAINER%`. Host starts. First invocation attempts output. Observe error.

**S3 — Malformed expression syntax**: Define `%QUEUE_NAME` (missing closing %). Observe parsing error timing.

**S4 — Defined but wrong value**: `QUEUE_NAME=nonexistent-queue`. Trigger binding resolves but queue doesn't exist. Observe first trigger vs. startup behavior.

**S5 — Key Vault reference in binding**: Binding uses `%@Microsoft.KeyVault(VaultName=invalid;SecretName=test)%`. Observe whether host starts and what value the binding uses.

## 9. Expected signal

- **S1**: Host starts but function fails to register. No invocations. Error in host log at startup.
- **S2**: Host starts, function registers, first invocation fails with binding output error. Invocation error in App Insights.
- **S3**: Host startup error — malformed expression causes parsing failure.
- **S4**: Host starts, function registers (binding expression resolved). First invocation fails when queue doesn't exist.
- **S5**: Host starts. Binding resolves to literal KV reference string or empty string. Trigger fails at first invocation.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Binding expression behavior may differ between Consumption, Flex Consumption, and Premium plans.
- Python v2 decorator model may have different failure timing than the v1 function.json model.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Missing trigger binding setting causes startup failure | **Inferred** |
| Output binding errors occur at invocation time | **Inferred** |
| KV reference failure falls back to literal string | **Unknown** |

## 14. Related experiments

- [Isolated Worker Startup](../isolated-worker-startup/overview.md) — worker startup failure modes
- [Telemetry Auth Blackhole](../telemetry-auth-blackhole/overview.md) — silent host configuration failures

## 15. References

- [Azure Functions binding expressions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-expressions-patterns)
- [App settings in binding expressions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-expressions-patterns#binding-expressions---app-settings)

## 16. Support takeaway

For binding expression failures:

1. Distinguish failure timing: trigger binding failures are at startup (function never registers); output binding failures are at invocation (function runs but output fails).
2. A function that "never executes" despite being in the portal often indicates a trigger binding expression failure. Check host startup logs for `Error indexing method` messages.
3. Verify all app settings referenced by `%SETTING_NAME%` expressions exist in the deployed environment. Local settings file does not automatically sync to Azure.
4. For Storage Queue and Blob binding expressions referencing non-existent queues/containers, the function may register successfully but fail at first invocation — these are separate failure modes.
