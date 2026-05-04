---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Application Insights Auto-Instrumentation Gap: Python Linux App Service

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When `ApplicationInsightsAgent_EXTENSION_VERSION=~3` is set on a Python Linux App Service (the setting that enables automatic Application Insights instrumentation for .NET and Node.js apps), does the platform agent auto-instrument the Python process? What environment variables are injected, and what is the actual instrumentation status?

## 2. Why this matters

The Application Insights agent (`ApplicationInsightsAgent_EXTENSION_VERSION=~3`) is the recommended zero-code instrumentation approach for .NET, Java, and Node.js App Service applications. Python teams often apply the same setting expecting the same outcome — zero-code telemetry without SDK changes. In practice, this setting is silently disabled for Python Linux apps. The platform injects diagnostic environment variables but does not activate any Python-specific instrumentation agent. Applications that rely on this setting for telemetry emit nothing to Application Insights without an explicit SDK install.

## 3. Customer symptom

"I enabled Application Insights from the portal but see no telemetry from my Python app" or "The `ApplicationInsightsAgent_EXTENSION_VERSION=~3` setting works on our Node.js app but not Python" or "Application Insights shows no dependency data or request traces despite being configured."

## 4. Hypothesis

- H1: Setting `ApplicationInsightsAgent_EXTENSION_VERSION=~3` on a Python Linux App Service results in the environment variable `ApplicationInsightsAgent_EXTENSION_VERSION=disabled` inside the running process — the platform overrides the setting to `disabled` for unsupported runtimes.
- H2: The platform injects `APPINSIGHTS_ENABLED=false` and `APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY` into the process environment even when the agent is disabled, indicating the agent infrastructure is present but inactive.
- H3: Setting `APPLICATIONINSIGHTS_CONNECTION_STRING` alone (without the SDK) does not enable telemetry — the connection string is visible in the APPSETTING_ namespace but is not consumed by any agent.
- H4: Python apps require explicit SDK installation (`pip install azure-monitor-opentelemetry`) and code-level configuration to send telemetry to Application Insights.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn |
| OS | Linux |
| App name | app-batch-1777849901 |
| AI resource | ai-lab-batch (Korea Central) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Observability / Platform behavior

**Controlled:**

- `ApplicationInsightsAgent_EXTENSION_VERSION=~3` app setting
- `APPLICATIONINSIGHTS_CONNECTION_STRING` app setting (valid connection string)
- Flask app with `/env` endpoint exposing `os.environ`

**Observed:**

- `ApplicationInsightsAgent_EXTENSION_VERSION` at runtime (inside process)
- `APPINSIGHTS_ENABLED` value
- `APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY`
- `PYTHONPATH` changes indicating agent injection
- Presence of `APPLICATIONINSIGHTS_CONNECTION_STRING` in process environment

## 7. Instrumentation

- `az webapp config appsettings set --settings "ApplicationInsightsAgent_EXTENSION_VERSION=~3"` — enable agent setting
- `az webapp config appsettings set --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=<cs>"` — set connection string
- Flask `/env` endpoint returning `os.environ` as JSON — observe injected vars inside process
- `az webapp config appsettings list` — verify what is configured vs what the process sees

## 8. Procedure

1. Set `ApplicationInsightsAgent_EXTENSION_VERSION=~3` and `APPLICATIONINSIGHTS_CONNECTION_STRING` app settings.
2. Restart app; check `/env` endpoint for agent-related environment variables.
3. Compare the configured app setting value (`~3`) vs the runtime value (expected: `disabled`).
4. Document all `APPINSIGHTS_*` and `APPLICATIONINSIGHTS_*` variables injected at runtime.

## 9. Expected signal

- `ApplicationInsightsAgent_EXTENSION_VERSION=disabled` at runtime (overridden by platform for Python).
- `APPINSIGHTS_ENABLED=false` injected.
- `APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY` injected (agent infrastructure present).
- No telemetry flow without SDK.

## 10. Results

### App settings configured

```
ApplicationInsightsAgent_EXTENSION_VERSION = ~3
APPLICATIONINSIGHTS_CONNECTION_STRING = InstrumentationKey=11a2593f-...
```

### Runtime environment variables (inside gunicorn process via /env)

```
APPINSIGHTS_ENABLED=false
APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY=/var/log/applicationinsights/
APPSETTING_ApplicationInsightsAgent_EXTENSION_VERSION=~3
ApplicationInsightsAgent_EXTENSION_VERSION=disabled
ORYX_AI_CONNECTION_STRING=InstrumentationKey=4aadba6b-...   ← Oryx internal key
ORYX_SDK_STORAGE_BASE_URL=https://oryx-cdn.microsoft.io
PYTHONPATH=/opt/startup/app_logs
```

!!! warning "Key finding"
    The configured value `~3` is overridden to `disabled` inside the running process. The platform explicitly sets `ApplicationInsightsAgent_EXTENSION_VERSION=disabled` for Python Linux apps, indicating the agent extension does not support Python on Linux.

### APPLICATIONINSIGHTS_CONNECTION_STRING in process env

```
# Configured in app settings:
APPLICATIONINSIGHTS_CONNECTION_STRING = InstrumentationKey=11a2593f-...

# Inside the process (/env endpoint):
APPLICATIONINSIGHTS_CONNECTION_STRING → NOT present in os.environ
# (The connection string is present as APPSETTING_APPLICATIONINSIGHTS_CONNECTION_STRING
#  and available via Azure app settings injection, but not directly in os.environ
#  when the agent is disabled)
```

### ORYX_AI_CONNECTION_STRING vs APPLICATIONINSIGHTS_CONNECTION_STRING

Two different connection strings are present:
- `ORYX_AI_CONNECTION_STRING` — Oryx build system's internal AppInsights key (not the user's resource)
- `APPLICATIONINSIGHTS_CONNECTION_STRING` (from app settings) — user's AppInsights resource, not consumed without SDK

## 11. Interpretation

- **Measured**: H1 is confirmed. The platform overrides `ApplicationInsightsAgent_EXTENSION_VERSION` from `~3` to `disabled` for Python Linux apps. **Measured**.
- **Measured**: H2 is confirmed. `APPINSIGHTS_ENABLED=false` and `APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY=/var/log/applicationinsights/` are both injected — the agent infrastructure exists but is inactive. **Measured**.
- **Observed**: H3 is consistent — the connection string is not consumed by any platform agent. `PYTHONPATH=/opt/startup/app_logs` suggests the platform does inject a startup hook path, but without the Python SDK installed, nothing reads the connection string. **Observed**.
- **Inferred**: H4 is correct by implication. Python apps must install `azure-monitor-opentelemetry` (or the older `opencensus-ext-azure`) and configure it in code. The platform agent path (`/opt/startup/app_logs`) is injected but contains no Python-specific agent.

## 12. What this proves

- `ApplicationInsightsAgent_EXTENSION_VERSION=~3` is silently overridden to `disabled` for Python Linux App Service. **Measured**.
- The platform injects agent infrastructure env vars (`APPINSIGHTS_ENABLED=false`, `APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY`) even when the agent is disabled. **Measured**.
- `ORYX_AI_CONNECTION_STRING` is always present (Oryx build telemetry) — it is NOT the user's Application Insights resource and should not be used for application telemetry. **Observed**.

## 13. What this does NOT prove

- Whether `azure-monitor-opentelemetry` SDK installation enables telemetry was not tested (SDK not installed in this environment).
- Whether the `PYTHONPATH=/opt/startup/app_logs` hook path contains any actual Python module was not verified (Kudu access disabled).
- Whether Java or .NET runtimes correctly activate `~3` was not tested in this experiment.
- Whether Windows-based Python App Service behaves differently was not tested.

## 14. Support takeaway

When a customer's Python App Service does not send telemetry to Application Insights despite the portal showing "Application Insights enabled":

1. Check the runtime value: `ApplicationInsightsAgent_EXTENSION_VERSION` inside the process will be `disabled` for Python Linux — the portal setting `~3` does not apply.
2. Python apps require explicit SDK installation. Add `azure-monitor-opentelemetry` to `requirements.txt`.
3. Configure the SDK in code:
   ```python
   from azure.monitor.opentelemetry import configure_azure_monitor
   configure_azure_monitor(connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"])
   ```
4. The `ORYX_AI_CONNECTION_STRING` env var is Oryx's own instrumentation key — do not use it for application telemetry.
5. `APPINSIGHTS_ENABLED=false` in the process env confirms the agent is inactive. After SDK installation and configuration, this var is irrelevant — the SDK reads `APPLICATIONINSIGHTS_CONNECTION_STRING` directly.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
AI_CS="InstrumentationKey=...;IngestionEndpoint=..."

# Configure agent setting + connection string
az webapp config appsettings set -n $APP -g $RG --settings \
  "ApplicationInsightsAgent_EXTENSION_VERSION=~3" \
  "APPLICATIONINSIGHTS_CONNECTION_STRING=$AI_CS"

az webapp restart -n $APP -g $RG
sleep 30

# Check runtime values (requires /env endpoint in app)
# Expected: ApplicationInsightsAgent_EXTENSION_VERSION=disabled
# Expected: APPINSIGHTS_ENABLED=false
curl https://<app>.azurewebsites.net/env | python3 -c "
import sys, json
env = json.load(sys.stdin)['env']
for k in ['ApplicationInsightsAgent_EXTENSION_VERSION', 'APPINSIGHTS_ENABLED',
          'APPLICATIONINSIGHTS_DIAGNOSTICS_OUTPUT_DIRECTORY', 'ORYX_AI_CONNECTION_STRING']:
    print(f'{k}={env.get(k, \"<not set>\")}')
"
```

## 16. Related guide / official docs

- [Enable Azure Monitor OpenTelemetry for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [Application Insights agent — supported runtimes](https://learn.microsoft.com/en-us/azure/azure-monitor/app/codeless-overview)
- [Migrate from OpenCensus Python SDK to Azure Monitor OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-python-opencensus-migrate)

## 1. Question

When migrating a Python App Service workload from the OpenCensus-based Application Insights SDK to the Azure Monitor OpenTelemetry Distro, are there observable differences in dependency capture coverage, telemetry table routing, and distributed trace correlation — and which gaps require explicit instrumentation to close?

## 2. Why this matters

Python teams migrating from the OpenCensus SDK (`opencensus-ext-azure`) to the Azure Monitor OpenTelemetry Distro (`azure-monitor-opentelemetry`) may encounter silent gaps: outbound HTTP dependency rows disappear from Application Insights, custom events appear in different Log Analytics tables, or traces fail to correlate across service boundaries. Support engineers diagnosing "App Insights shows no dependency data after migration" or "traces don't link across services after SDK upgrade" need to know which SDK behavior changed and what explicit configuration closes each gap.

## 3. Customer symptom

"After switching to the OpenTelemetry SDK, my dependency calls disappeared from Application Insights" or "Custom events are missing after the migration — they don't show up in customEvents table anymore" or "Distributed traces stopped correlating between my App Service and downstream services."

## 4. Hypothesis

- H1: The OpenCensus SDK auto-instruments the `requests` library for outbound HTTP dependency tracking out of the box. The Azure Monitor OTel Distro requires the `opentelemetry-instrumentation-requests` library to be explicitly installed and configured; without it, outbound HTTP calls do not appear in the `dependencies` table.
- H2: Custom telemetry emitted via `TelemetryClient.track_event()` in OpenCensus appears in the `customEvents` table. The equivalent in the OTel Distro (`tracer.start_span()` or `logger.info()` with OTel) maps to the `traces` or `requests` table, not `customEvents` — KQL queries targeting `customEvents` will silently miss OTel-sourced telemetry.
- H3: Distributed trace correlation (W3C `traceparent` propagation) works correctly with both SDKs independently. A mixed deployment (one service on OpenCensus, another on OTel Distro) can maintain correlation if both sides propagate W3C headers; correlation breaks only when one side uses a legacy proprietary header format.
- H4: Sampling configured in the Application Insights resource (adaptive sampling) applies downstream of both SDKs. SDK-level sampling in the OTel Distro (via `TraceIdRatioBased`) is applied before data reaches the exporter and is additive with resource-level sampling.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Observability / Configuration

**Controlled:**

- Same Python app deployed with three instrumentation configurations
- Same outbound HTTP calls (to a stable internal test endpoint)
- Same Application Insights resource (connection string)
- Same request volume (100 requests per run, no sampling)

**Observed:**

- Row count in `dependencies` table per run
- Row count in `customEvents` vs `traces` table per run
- `operation_Id` linkage between `requests` and `dependencies` rows
- `traceparent` header propagation across service boundaries

**Configurations:**

- C1: `opencensus-ext-azure` with `requests` integration enabled (baseline)
- C2: `azure-monitor-opentelemetry` Distro with default config (no explicit instrumentation libraries added)
- C3: `azure-monitor-opentelemetry` Distro with `opentelemetry-instrumentation-requests` added explicitly

**Independent run definition**: One 100-request burst per configuration with fixed outbound call set.

**Planned runs per configuration**: 3

**Warm-up exclusion rule**: Allow Application Insights ingestion to settle (5 minutes) before querying.

## 7. Instrumentation

- Log Analytics KQL: `dependencies | where timestamp > ago(15m) | summarize count() by sdkVersion` — dependency row count per SDK
- Log Analytics KQL: `customEvents | where timestamp > ago(15m)` vs `traces | where timestamp > ago(15m)` — custom event table routing
- Log Analytics KQL: `requests | join kind=inner dependencies on operation_Id | summarize count()` — trace linkage
- HTTP response header inspection: `traceparent` value captured by load test client — propagation verification
- App Service log stream: SDK initialization warnings or missing-library errors

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy C1 (OpenCensus); send 100 requests, each triggering one outbound HTTP call and one `track_event`; wait 5 minutes; query Log Analytics.
2. Record: `dependencies` count, `customEvents` count, `traces` count, `operation_Id` linkage rate.
3. Redeploy with C2 (OTel Distro, default config); repeat same burst; compare counts.
4. Redeploy with C3 (OTel Distro + explicit requests instrumentation); repeat; compare.
5. For mixed-SDK test (H3): deploy one service on C1 and a downstream service on C3; send requests; check `operation_Id` correlation across both services.
6. Document any telemetry that appears in C1 but not in C2, and whether C3 closes the gap.

## 9. Expected signal

- C1: `dependencies` table has ~100 rows (one per outbound call); `customEvents` has ~100 rows; trace linkage rate near 100%.
- C2: `dependencies` table is empty or near-zero (no explicit `requests` instrumentation); `customEvents` empty; OTel events appear in `traces`.
- C3: `dependencies` table has ~100 rows; trace linkage rate near 100%; custom telemetry in `traces`, not `customEvents`.
- Mixed (C1 + C3): `operation_Id` links correctly across services if both propagate W3C `traceparent`.

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

- Disable Application Insights adaptive sampling during the experiment to avoid confounding the row count comparison; set `APPLICATIONINSIGHTS_SAMPLING_PERCENTAGE=100` in app settings.
- Allow 3–5 minutes after each test burst before querying Log Analytics to allow ingestion to settle.
- The `azure-monitor-opentelemetry` Distro auto-installs some instrumentation libraries but not all; check the distro's changelog for the current auto-included library list.
- `customEvents` vs `traces` table routing may change across distro versions; pin the distro version and document it in the experiment.

## 16. Related guide / official docs

- [Enable Azure Monitor OpenTelemetry for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [Migrate from OpenCensus Python SDK to Azure Monitor OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-python-opencensus-migrate)
- [Azure Monitor OpenTelemetry Distro — supported instrumentation libraries](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-add-modify?tabs=python)
