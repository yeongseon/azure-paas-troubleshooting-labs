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

# OpenTelemetry Trace Gap: Spans Lost Between Container Apps and Application Insights

!!! info "Status: Planned"

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
