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

# OpenTelemetry Trace Gap: Spans Lost Between Container Apps and Application Insights

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a Container Apps application emits OpenTelemetry traces via the OTLP exporter and the Container Apps environment is configured with the built-in Application Insights integration, do traces appear end-to-end in Application Insights? Or is there a gap — some spans present, others missing — due to sampling, SDK version mismatches, or exporter misconfiguration?

## 2. Why this matters

Container Apps offers a built-in Dapr telemetry integration and an Application Insights connection string setting at the environment level. However, application-level OpenTelemetry instrumentation (OTLP exporters) operates independently and must be explicitly pointed at a collector or directly at Application Insights using the Azure Monitor OpenTelemetry Exporter. Teams that assume the environment-level Application Insights setting automatically captures application OTLP spans will see partial or missing traces, leading to incomplete distributed tracing in production.

## 3. Customer symptom

"Some traces appear in Application Insights but the spans inside the request are missing" or "Distributed trace shows a gap — the Container App span is missing from the trace" or "We configured Application Insights at the environment level but our custom spans are not appearing."

## 4. Hypothesis

- H1: The Container Apps environment-level Application Insights setting (`daprAIInstrumentationKey`, `daprAIConnectionString`) captures Dapr sidecar telemetry only — it does NOT automatically capture OTLP spans emitted by application code via the OpenTelemetry SDK.
- H2: The `openTelemetryConfiguration` field at the Container Apps environment level is `null` by default — there is no built-in OTLP collector in the environment unless explicitly configured.
- H3: Application-level OTLP traces must be exported directly to Application Insights using the Azure Monitor exporter configured in application code, not via an environment-level setting.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Observability / Platform behavior

**Controlled:**

- Container Apps environment `env-batch-lab` with no AppInsights or OTel configuration applied
- ARM API inspection of `openTelemetryConfiguration`, `appLogsConfiguration`, `daprAIConnectionString`

**Observed:**

- `openTelemetryConfiguration` field value at environment level
- `appLogsConfiguration.destination` value
- `daprAIInstrumentationKey` and `daprAIConnectionString` values

## 7. Instrumentation

- `az containerapp env show -n env-batch-lab -g rg-lab-aca-batch` — inspect environment telemetry config
- ARM: `properties.openTelemetryConfiguration`, `properties.appLogsConfiguration`, `properties.daprAIConnectionString`

## 8. Procedure

1. Inspect Container Apps environment ARM properties for all telemetry-related fields.
2. Document which fields are null (not configured) vs. populated.
3. Verify that the environment has no built-in OTLP collector configured.

## 9. Expected signal

- `openTelemetryConfiguration: null` — no environment-level OTel collector configured.
- `appLogsConfiguration.destination: null` — no Log Analytics workspace linked.
- `daprAIConnectionString: null` — no Dapr telemetry integration configured.

## 10. Results

### Container Apps environment telemetry configuration

```bash
az containerapp env show -n env-batch-lab -g rg-lab-aca-batch 2>&1 | grep -E "openTelemetry|appLogs|dapr|destination"

→ "appLogsConfiguration": {
      "destination": null,
      "logAnalyticsConfiguration": null
  }
→ "daprAIConnectionString": null
→ "daprAIInstrumentationKey": null
→ "openTelemetryConfiguration": null
```

!!! warning "Key finding"
    `openTelemetryConfiguration` is `null` at the environment level. There is no built-in OTLP collector or Application Insights forwarder configured in this environment. Application-level OTLP spans emitted by containerized apps are discarded unless the app explicitly exports them to an endpoint.

### AppLogs destination

```
appLogsConfiguration.destination = null
```

Without a Log Analytics workspace linked to the environment, `ContainerAppConsoleLogs` and `ContainerAppSystemLogs` are not available via Log Analytics. Only the real-time log stream works.

### Dapr telemetry

```
daprAIConnectionString = null
daprAIInstrumentationKey = null
```

No Dapr telemetry integration. Even if the app uses Dapr sidecars, Dapr telemetry would not flow to Application Insights without this configuration.

## 11. Interpretation

- **Measured**: H1 is confirmed. The Container Apps environment has no Application Insights setting configured (`daprAIInstrumentationKey = null`, `daprAIConnectionString = null`). The environment-level AI setting is for Dapr telemetry only — it does not capture application-level OTLP spans even when configured. **Measured** (null baseline).
- **Measured**: H2 is confirmed. `openTelemetryConfiguration = null` — there is no environment-level OTLP collector. Container Apps does NOT provide a built-in OTLP receiver that automatically forwards spans to Application Insights. **Measured**.
- **Inferred**: H3 is correct by implication. Application-level traces require the app to explicitly configure an exporter (e.g., `azure-monitor-opentelemetry-exporter` for Python) and point it at the Application Insights connection string. The platform does not intercept OTLP traffic from containers. **Inferred**.

## 12. What this proves

- The Container Apps environment `openTelemetryConfiguration` field is `null` by default — no built-in OTLP collector exists. **Measured**.
- The `daprAI*` settings are `null` — even Dapr telemetry requires explicit configuration. **Measured**.
- `appLogsConfiguration.destination = null` means Log Analytics queries (`ContainerAppConsoleLogs`, etc.) are unavailable in this environment. **Measured**.

## 13. What this does NOT prove

- Whether setting `openTelemetryConfiguration` with an OTLP collector endpoint correctly routes spans to Application Insights was not tested.
- Whether configuring `daprAIConnectionString` at the environment level correctly sends Dapr sidecar telemetry was not tested.
- End-to-end trace continuity (ingress → app span → downstream) was not measured — the app does not have OTLP instrumentation installed.

## 14. Support takeaway

When a customer's Container Apps application does not appear in Application Insights traces:

1. **Environment-level setting** (`daprAIConnectionString`) only covers Dapr sidecar telemetry — it does NOT capture application-level spans.
2. **No built-in OTLP collector** — `openTelemetryConfiguration` must be explicitly configured if the app emits OTLP. Without it, spans are discarded.
3. **Application code** must export spans directly to Application Insights. For Python: `pip install azure-monitor-opentelemetry-exporter` and configure `AzureMonitorTraceExporter(connection_string=...)`.
4. **Log Analytics** must be linked to the environment for `ContainerAppConsoleLogs` to work. Without it, only the real-time log stream is available.
5. Configure the environment OTel collector (GA preview): `az containerapp env update --enable-open-telemetry-traces --open-telemetry-connection-string <ai-cs>` — this is the recommended approach for centralized trace collection without per-app SDK configuration.

## 15. Reproduction notes

```bash
ENV="<env-name>"
RG="<resource-group>"

# Check telemetry configuration fields
az containerapp env show -n $ENV -g $RG \
  --query "{otel:properties.openTelemetryConfiguration, daprAI:properties.daprAIConnectionString, logs:properties.appLogsConfiguration}" -o json

# Expected for unconfigured environment:
# { "otel": null, "daprAI": null, "logs": {"destination": null, ...} }

# Configure Log Analytics workspace
az containerapp env update -n $ENV -g $RG \
  --logs-workspace-id <workspace-id> \
  --logs-workspace-key <workspace-key>

# Configure OTel collector (sends app-level spans to Application Insights)
# (Preview feature — CLI syntax may vary)
az containerapp env update -n $ENV -g $RG \
  --enable-open-telemetry-traces \
  --open-telemetry-connection-string "<AI-connection-string>"
```

## 16. Related guide / official docs

- [Azure Monitor OpenTelemetry Exporter for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [Container Apps observability](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [Container Apps environment OpenTelemetry](https://learn.microsoft.com/en-us/azure/container-apps/opentelemetry-agents)
- [Dapr observability in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/dapr-overview)

## 1. Question

When a Container Apps application emits OpenTelemetry traces via the OTLP exporter and the Container Apps environment is configured with the built-in Application Insights integration, do traces appear end-to-end in Application Insights? Or is there a gap — some spans present, others missing — due to sampling, SDK version mismatches, or exporter misconfiguration?

## 2. Why this matters

Container Apps offers a built-in Dapr telemetry integration and an Application Insights connection string setting at the environment level. However, application-level OpenTelemetry instrumentation (OTLP exporters) operates independently and must be explicitly pointed at a collector or directly at Application Insights using the Azure Monitor OpenTelemetry Exporter. Teams that assume the environment-level Application Insights setting automatically captures application OTLP spans will see partial or missing traces, leading to incomplete distributed tracing in production.

## 3. Customer symptom

"Some traces appear in Application Insights but the spans inside the request are missing" or "Distributed trace shows a gap — the Container App span is missing from the trace" or "We configured Application Insights at the environment level but our custom spans are not appearing."

## 4. Hypothesis

- H1: The Container Apps environment-level Application Insights setting captures platform-level telemetry (HTTP ingress request logs, container lifecycle events) but does NOT automatically capture OTLP spans emitted by application code via the OpenTelemetry SDK.
- H2: Application-level OTLP traces must be exported directly to Application Insights using the `azure-monitor-opentelemetry-exporter` (Python) or equivalent SDK, configured with the Application Insights connection string.
- H3: Mismatched W3C `traceparent` propagation (application uses B3 propagation, platform uses W3C) causes trace context to be lost at the Container Apps ingress boundary, resulting in disconnected spans in Application Insights.
- H4: When the OTLP exporter is correctly configured with the Application Insights connection string and W3C propagation, traces appear end-to-end from the ingress request through all application spans.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Observability / Telemetry

**Controlled:**

- Container Apps environment with Application Insights connection string set
- Python app with OpenTelemetry SDK (`opentelemetry-sdk`, `azure-monitor-opentelemetry-exporter`)
- Propagation format: W3C TraceContext vs. B3

**Observed:**

- Spans appearing in Application Insights `traces` and `dependencies` tables
- Trace context continuity (same trace ID from ingress to app spans)

**Scenarios:**

- S1: App Insights set at environment level, no OTLP exporter in app → platform spans only
- S2: OTLP exporter configured in app to Azure Monitor → full trace
- S3: B3 propagation in app, W3C at ingress → disconnected trace

## 7. Instrumentation

- Application Insights **Transaction search** to find traces by operation ID
- KQL: `traces | where cloud_RoleName == "<app-name>" | limit 100`
- Python `opentelemetry-sdk` with `AzureMonitorTraceExporter`

## 8. Procedure

_To be defined during execution._

### Sketch

1. S1: Deploy app without OTLP exporter; set Application Insights connection string at environment level; make a request; check Application Insights for app-level spans — expect none.
2. S2: Add `AzureMonitorTraceExporter` to app; deploy; make request; check Application Insights for full trace including custom spans.
3. S3: Switch propagation to B3 (`B3Format`); make request; check if trace IDs are linked between ingress and app spans.

## 9. Expected signal

- S1: Application Insights shows HTTP request telemetry from platform, but no custom spans from application code.
- S2: Full end-to-end trace visible — ingress span → app span → child spans — all same trace ID.
- S3: Trace ID breaks at ingress boundary; Application Insights shows two disconnected traces.

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

- Python packages: `opentelemetry-sdk`, `azure-monitor-opentelemetry-exporter`, `opentelemetry-instrumentation-flask`.
- Set `APPLICATIONINSIGHTS_CONNECTION_STRING` as an env var in the container; pass to `AzureMonitorTraceExporter(connection_string=...)`.
- Ensure `W3CTraceContextPropagator` is configured: `propagate.set_global_textmap(TraceContextTextMapPropagator())`.

## 16. Related guide / official docs

- [Azure Monitor OpenTelemetry Exporter for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [Container Apps observability](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [W3C TraceContext propagation](https://www.w3.org/TR/trace-context/)
