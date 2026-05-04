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

# Application Insights Connection String Injection: What App Service Injects vs. What Sends Telemetry

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When `APPLICATIONINSIGHTS_CONNECTION_STRING` is configured as an App Service application setting, does the Python gunicorn process automatically send request telemetry to Application Insights — or does the developer still need to install and initialize the Azure Monitor SDK explicitly?

## 2. Why this matters

App Service auto-instrumentation for Python is not equivalent to .NET or Java. When a customer adds the Application Insights resource via the portal's "Application Insights" blade (or manually sets the connection string as an app setting), the environment variable is injected into the gunicorn process — but unlike .NET, no agent is attached, no instrumentation happens, and no telemetry is collected. The customer sees the connection string in their environment and assumes it is working. Nothing flows to Application Insights.

## 3. Customer symptom

"I connected Application Insights to my Python App Service but there's no data" or "Live Metrics shows 0 connected instances even though my app is running" or "The connection string is set correctly but Application Insights shows nothing."

## 4. Hypothesis

- H1: Setting `APPINSIGHTS_INSTRUMENTATIONKEY` and `APPLICATIONINSIGHTS_CONNECTION_STRING` as app settings causes both values to appear in the gunicorn process environment (`os.environ`).
- H2: Despite the connection string being injected, no telemetry flows to Application Insights without explicit Azure Monitor SDK initialization in the Python application code.
- H3: App Service always injects `ORYX_AI_CONNECTION_STRING` into the Python process environment — a separate, platform-internal instrumentation key used by the Oryx build system, distinct from the user's Application Insights resource.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn |
| OS | Linux |
| App name | app-batch-1777849901 |
| Application Insights | ai-lab-batch (Korea Central) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Observability / Platform behavior

**Controlled:**

- `APPINSIGHTS_INSTRUMENTATIONKEY` and `APPLICATIONINSIGHTS_CONNECTION_STRING` set via `az webapp config appsettings set`
- No `azure-monitor-opentelemetry` or `opencensus-ext-azure` package installed in the running app
- 5 GET requests sent to the app after env injection

**Observed:**

- Presence of AI-related variables in `os.environ` via the `/env` endpoint
- Presence of platform-injected `ORYX_AI_CONNECTION_STRING`
- Telemetry row count in Application Insights after traffic generation

## 7. Instrumentation

- `az monitor app-insights component create` — create fresh AI resource
- `az webapp config appsettings set` — inject keys as app settings
- Flask `/env` endpoint — returns `os.environ` as JSON
- Application Insights portal — Live Metrics, Search (verify zero collection without SDK)

## 8. Procedure

1. Create Application Insights resource (`ai-lab-batch`, Korea Central).
2. Set `APPINSIGHTS_INSTRUMENTATIONKEY` and `APPLICATIONINSIGHTS_CONNECTION_STRING` as app settings.
3. Restart app; call `/env` endpoint to verify env injection.
4. Generate 5 GET requests.
5. Check Application Insights portal for traces/requests/dependencies.
6. Record `ORYX_AI_CONNECTION_STRING` value from `/env` output.

## 9. Expected signal

- H1 confirmed if both `APPINSIGHTS_INSTRUMENTATIONKEY` and `APPSETTING_APPINSIGHTS_INSTRUMENTATIONKEY` appear in `os.environ`.
- H2 confirmed if Application Insights portal shows zero telemetry rows after traffic.
- H3 confirmed if `ORYX_AI_CONNECTION_STRING` is present with a key different from the user's key.

## 10. Results

### Application Insights resource

```bash
az monitor app-insights component create \
  --app ai-lab-batch \
  --location koreacentral \
  --resource-group rg-lab-appservice-batch \
  --query "{key:instrumentationKey,conn:connectionString}"

→ {
    "key": "11a2593f-5b7e-418a-8385-5da5605d75f1",
    "conn": "InstrumentationKey=11a2593f-5b7e-418a-8385-5da5605d75f1;
             IngestionEndpoint=https://koreacentral-0.in.applicationinsights.azure.com/;
             LiveEndpoint=https://koreacentral.livediagnostics.monitor.azure.com/"
  }
```

### App settings applied and confirmed

```bash
az webapp config appsettings set -n app-batch-1777849901 -g rg-lab-appservice-batch \
  --settings \
  "APPINSIGHTS_INSTRUMENTATIONKEY=11a2593f-..." \
  "APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=11a2593f-..."

→ [{"name": "APPINSIGHTS_INSTRUMENTATIONKEY"}, {"name": "APPLICATIONINSIGHTS_CONNECTION_STRING"}]
```

### Environment variables in running process (after restart)

```
GET /env

Key                                          Value (truncated)
----                                         -----
APPINSIGHTS_INSTRUMENTATIONKEY               11a2593f-5b7e-418a-8385-5da5605d75f1
APPLICATIONINSIGHTS_CONNECTION_STRING        InstrumentationKey=11a2593f-...;IngestionEndpoint=https://...
APPSETTING_APPINSIGHTS_INSTRUMENTATIONKEY    11a2593f-5b7e-418a-8385-5da5605d75f1
APPSETTING_APPLICATIONINSIGHTS_CONNECTION_STRING  InstrumentationKey=11a2593f-...
ORYX_AI_CONNECTION_STRING                    InstrumentationKey=4aadba6b-30c8-42db-9b93-024d5c62b887
```

Two distinct instrumentation keys in environment:

| Variable | Key prefix | Source |
|----------|-----------|--------|
| `APPINSIGHTS_INSTRUMENTATIONKEY` | `11a2593f` | User-configured app setting |
| `ORYX_AI_CONNECTION_STRING` | `4aadba6b` | Platform-injected by Oryx |

### Application Insights portal — after 5 requests

```
Live Metrics:    0 connected instances
Search (30 min): 0 requests, 0 dependencies, 0 traces
```

## 11. Interpretation

- **Measured**: H1 is confirmed. Both `APPINSIGHTS_INSTRUMENTATIONKEY` and `APPLICATIONINSIGHTS_CONNECTION_STRING` appear in `os.environ` under both their raw names and with the `APPSETTING_` prefix. The injection works correctly. **Measured**.
- **Measured**: H2 is confirmed. Zero telemetry rows appeared in Application Insights after 5 requests. The connection string being present in the environment has no effect without SDK code. **Measured**.
- **Observed**: H3 is confirmed. `ORYX_AI_CONNECTION_STRING` (`4aadba6b-...`) is always present — this is the Oryx build platform's own internal AI resource. It is not the customer's resource and its presence does not indicate that customer telemetry is being sent. **Observed**.
- **Inferred**: App Service .NET and Java auto-instrumentation works because the platform injects an agent at startup (the `DOTNET_STARTUP_HOOKS` or Java `-javaagent` mechanism). No equivalent Python agent injection exists. Python requires explicit SDK installation and initialization.

## 12. What this proves

- `APPLICATIONINSIGHTS_CONNECTION_STRING` IS correctly injected into the Python process environment. **Measured**.
- Connection string injection alone produces no telemetry. Explicit SDK initialization is required. **Measured**.
- `ORYX_AI_CONNECTION_STRING` is always present in the Python App Service environment — it is a platform key, not the customer's. **Observed**.

## 13. What this does NOT prove

- Whether `azure-monitor-opentelemetry` with `configure_azure_monitor()` correctly reads the injected connection string and produces telemetry — not tested here.
- Whether auto-instrumentation works for .NET or Java App Service (not in scope; those platforms use agent injection).
- The AI resource's `ai-lab-batch` Live Metrics behavior after SDK is installed — not tested.

## 14. Support takeaway

When a Python App Service customer reports no data in Application Insights despite a connection string being configured:

1. Confirm the setting is stored: `az webapp config appsettings list -n <app> -g <rg> --query "[?name=='APPLICATIONINSIGHTS_CONNECTION_STRING'].value" -o tsv`
2. Confirm injection: check `/env` or Kudu SSH for `APPLICATIONINSIGHTS_CONNECTION_STRING` in the process environment.
3. If the variable is present but no data appears: the app code is missing SDK initialization. Python does not auto-instrument.
4. Fix: add `azure-monitor-opentelemetry` to `requirements.txt` and `from azure.monitor.opentelemetry import configure_azure_monitor; configure_azure_monitor()` at app startup.
5. Note: `ORYX_AI_CONNECTION_STRING` in `/env` output is a platform-internal key — customers may confuse this with their own AI resource. Always check `APPLICATIONINSIGHTS_CONNECTION_STRING` separately.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"

# Create AI resource
AI_CONN=$(az monitor app-insights component create \
  --app my-ai --location koreacentral --resource-group $RG \
  --query "connectionString" -o tsv)

# Set as app setting
az webapp config appsettings set -n $APP -g $RG \
  --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=$AI_CONN"

# Restart and verify injection
az webapp restart -n $APP -g $RG
sleep 30
curl https://<app>.azurewebsites.net/env | python3 -c "
import sys, json
env = json.load(sys.stdin)['env']
for k, v in env.items():
    if 'INSIGHT' in k.upper(): print(f'{k}={v[:50]}')
"
# Expected: APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
#           ORYX_AI_CONNECTION_STRING=InstrumentationKey=<different key>

# Generate traffic
for i in $(seq 1 5); do curl -s https://<app>.azurewebsites.net/ > /dev/null; done

# Check AI portal — expect 0 results without SDK
# To fix: add to requirements.txt:
#   azure-monitor-opentelemetry
# Add to app startup:
#   from azure.monitor.opentelemetry import configure_azure_monitor
#   configure_azure_monitor()
```

## 16. Related guide / official docs

- [Enable Azure Monitor OpenTelemetry for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [Application Insights for Python App Service](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-web-apps-python)
- [configure_azure_monitor() reference](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration?tabs=python)
