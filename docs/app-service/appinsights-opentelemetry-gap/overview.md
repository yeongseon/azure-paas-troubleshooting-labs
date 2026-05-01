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

# OpenCensus vs Azure Monitor OpenTelemetry Distro: Telemetry Coverage Gap

!!! info "Status: Planned"

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
