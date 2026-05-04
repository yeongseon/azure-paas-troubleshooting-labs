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

!!! warning "Status: Draft - Blocked"
    Execution blocked: Flex Consumption plan creation blocked by Azure Policy.

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

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-telemetry-auth-blackhole-lab"
export LOCATION="koreacentral"
export FLEX_APP_NAME="func-telemetry-flex-$RANDOM"
export CONS_APP_NAME="func-telemetry-cons-$RANDOM"
export STORAGE_NAME="stteleauth$RANDOM"
export APP_INSIGHTS_NAME="appi-telemetry-auth-blackhole"
export LOG_WORKSPACE_NAME="law-telemetry-auth-blackhole"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-shared-key-access false \
  --allow-blob-public-access false

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LOG_WORKSPACE_NAME" \
  --location "$LOCATION"

az monitor app-insights component create \
  --resource-group "$RG" \
  --app "$APP_INSIGHTS_NAME" \
  --workspace "$LOG_WORKSPACE_NAME" \
  --application-type web \
  --location "$LOCATION"

az functionapp create \
  --resource-group "$RG" \
  --name "$FLEX_APP_NAME" \
  --storage-account "$STORAGE_NAME" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --flexconsumption-location "$LOCATION"

az functionapp plan create \
  --resource-group "$RG" \
  --name "plan-telemetry-consumption" \
  --location "$LOCATION" \
  --sku Y1 \
  --is-linux

az functionapp create \
  --resource-group "$RG" \
  --name "$CONS_APP_NAME" \
  --plan "plan-telemetry-consumption" \
  --storage-account "$STORAGE_NAME" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4
```

### 8.2 Application Code

```python
import json
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}),
        mimetype="application/json",
        status_code=200,
    )
```

```yaml
scenarios:
  - name: valid-connection-string
  - name: invalid-connection-string
  - name: empty-connection-string
  - name: managed-identity-auth-without-role
```

### 8.3 Deploy

```bash
mkdir -p app-telemetry-auth-blackhole

cat > app-telemetry-auth-blackhole/function_app.py <<'PY'
# paste Python from section 8.2
PY

cat > app-telemetry-auth-blackhole/host.json <<'JSON'
{
  "version": "2.0"
}
JSON

cat > app-telemetry-auth-blackhole/requirements.txt <<'TXT'
azure-functions
TXT

CONNECTION_STRING=$(az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APP_INSIGHTS_NAME" \
  --query connectionString --output tsv)

for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az functionapp identity assign --resource-group "$RG" --name "$APP_NAME"

  az functionapp config appsettings set \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --settings \
      AzureWebJobsStorage__accountName="$STORAGE_NAME" \
      FUNCTIONS_WORKER_RUNTIME="python" \
      APPLICATIONINSIGHTS_CONNECTION_STRING="$CONNECTION_STRING"

  (cd app-telemetry-auth-blackhole && zip -r ../app-telemetry-auth-blackhole.zip .)
  az functionapp deployment source config-zip \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --src app-telemetry-auth-blackhole.zip
done
```

### 8.4 Test Execution

```bash
export FLEX_URL="https://$FLEX_APP_NAME.azurewebsites.net/api/health"
export CONS_URL="https://$CONS_APP_NAME.azurewebsites.net/api/health"

# 1) Baseline with valid telemetry settings
curl --fail "$FLEX_URL"
curl --fail "$CONS_URL"

# 2) Invalid connection string scenario
for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az functionapp config appsettings set \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --settings APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://invalid.monitor.azure.com/"
  az functionapp restart --resource-group "$RG" --name "$APP_NAME"
done

for i in $(seq 1 20); do
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  curl --silent --show-error "$FLEX_URL" || true
  curl --silent --show-error "$CONS_URL" || true
  sleep 10
done

# 3) Empty connection string scenario
for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az functionapp config appsettings set \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --settings APPLICATIONINSIGHTS_CONNECTION_STRING=""
  az functionapp restart --resource-group "$RG" --name "$APP_NAME"
done

for i in $(seq 1 20); do
  curl --silent --show-error "$FLEX_URL" || true
  curl --silent --show-error "$CONS_URL" || true
  sleep 10
done

# 4) Managed identity telemetry auth without required role
for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az functionapp config appsettings set \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --settings \
      APPLICATIONINSIGHTS_CONNECTION_STRING="$CONNECTION_STRING" \
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING="Authorization=AAD"
  az functionapp restart --resource-group "$RG" --name "$APP_NAME"
done

for i in $(seq 1 20); do
  curl --silent --show-error "$FLEX_URL" || true
  curl --silent --show-error "$CONS_URL" || true
  sleep 10
done

# 5) Restore baseline and validate recovery
for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az functionapp config appsettings delete \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --setting-names APPLICATIONINSIGHTS_AUTHENTICATION_STRING
  az functionapp config appsettings set \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --settings APPLICATIONINSIGHTS_CONNECTION_STRING="$CONNECTION_STRING"
  az functionapp restart --resource-group "$RG" --name "$APP_NAME"
done
```

### 8.5 Data Collection

```bash
APP_INSIGHTS_ID=$(az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APP_INSIGHTS_NAME" \
  --query appId --output tsv)

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "requests | where timestamp > ago(6h) | where cloud_RoleName in ('$FLEX_APP_NAME','$CONS_APP_NAME') | summarize total=count(), failed=countif(success == false), p95=percentile(duration,95) by cloud_RoleName, bin(timestamp, 5m) | order by timestamp asc" \
  --output table

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "traces | where timestamp > ago(6h) | where message has_any ('Application Insights','Telemetry','Host') | project timestamp, cloud_RoleName, severityLevel, message | order by timestamp desc" \
  --output table

for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az monitor metrics list \
    --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP_NAME" \
    --metric "FunctionExecutionCount" "Http5xx" \
    --interval PT1M \
    --aggregation Total \
    --output table
done

for APP_NAME in "$FLEX_APP_NAME" "$CONS_APP_NAME"; do
  az functionapp log tail --resource-group "$RG" --name "$APP_NAME"
done
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

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
