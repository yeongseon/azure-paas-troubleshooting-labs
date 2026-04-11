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

# Flex Consumption Site Update Strategy and In-Flight Behavior

!!! info "Status: Planned"

## 1. Question

When a new version is deployed to a Flex Consumption function app, what happens to in-flight requests, and what is the latency impact during the deployment transition? Does the platform use blue-green, rolling, or stop-start deployment?

## 2. Why this matters

Zero-downtime deployment is critical for production workloads. Customers deploying frequently need to understand whether in-flight requests are drained gracefully, dropped, or routed to the new version mid-execution. The deployment strategy also affects cold start frequency — if all instances are replaced simultaneously, there is a "thundering herd" cold start.

## 3. Customer symptom

- "We see a burst of errors every time we deploy."
- "Some requests get 503 during deployment, even though we deploy several times a day."
- "After deployment, the first few requests are slow — feels like all instances cold-start at once."

## 4. Hypothesis

Flex Consumption uses a rolling update strategy where:

1. New instances are provisioned with the new version before old instances are drained
2. In-flight requests on old instances are allowed to complete (graceful drain with timeout)
3. There is a brief overlap period where both old and new versions serve requests
4. The latency spike during deployment correlates with the number of instances being replaced

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

- Deployment method: `az functionapp deploy`, VS Code, GitHub Actions
- Load during deployment: steady 20 RPS
- Function execution duration: 100ms, 5s, 30s (to test drain behavior)
- Instance count: always_ready=2

**Observed:**

- Request success/failure rate during deployment window
- Latency distribution before, during, and after deployment
- Instance version serving each request (custom version header)
- In-flight request completion or cancellation
- Cold start count after deployment

**Independent run definition**: Stable baseline for 5 minutes, then deploy new version, measure for 10 minutes after

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: No exclusion — deployment transition IS the measurement

**Primary metric**: Error rate during deployment window; meaningful effect threshold: any errors >0%

**Comparison method**: Directional comparison across deployment methods

## 7. Instrumentation

- Application Insights: request traces with custom `app_version` property
- Custom middleware: version identification in response headers
- Azure Monitor: `FunctionExecutionCount`, `Http5xx`
- k6 load generator: continuous requests with per-request success/failure logging

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-flex-site-update-strategy-lab"
export LOCATION="koreacentral"
export APP_NAME="func-flex-site-update-$RANDOM"
export STORAGE_NAME="stflexupdate$RANDOM"
export APP_INSIGHTS_NAME="appi-flex-site-update-strategy"
export LOG_WORKSPACE_NAME="law-flex-site-update-strategy"

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
  --name "$APP_NAME" \
  --storage-account "$STORAGE_NAME" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --flexconsumption-location "$LOCATION"

az functionapp identity assign --resource-group "$RG" --name "$APP_NAME"

PRINCIPAL_ID=$(az functionapp identity show \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --query principalId --output tsv)

STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Queue Data Contributor" \
  --scope "$STORAGE_ID"
```

### 8.2 Application Code

```python
import json
import os
import time
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
APP_VERSION = os.getenv("APP_VERSION", "v1")


@app.route(route="work", methods=["GET"])
def work(req: func.HttpRequest) -> func.HttpResponse:
    sleep_seconds = int(req.params.get("sleep", "1"))
    started = time.perf_counter()
    time.sleep(sleep_seconds)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    body = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "sleep_seconds": sleep_seconds,
        "elapsed_ms": elapsed,
    }
    return func.HttpResponse(
        json.dumps(body),
        status_code=200,
        mimetype="application/json",
        headers={"x-app-version": APP_VERSION, "x-elapsed-ms": str(elapsed)},
    )
```

```yaml
profiles:
  - name: short
    sleep: 1
  - name: medium
    sleep: 5
  - name: long
    sleep: 30
```

### 8.3 Deploy

```bash
mkdir -p app-flex-site-update

cat > app-flex-site-update/function_app.py <<'PY'
# paste Python from section 8.2
PY

cat > app-flex-site-update/host.json <<'JSON'
{
  "version": "2.0"
}
JSON

cat > app-flex-site-update/requirements.txt <<'TXT'
azure-functions
TXT

az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings \
    AzureWebJobsStorage__accountName="$STORAGE_NAME" \
    FUNCTIONS_WORKER_RUNTIME="python" \
    APP_VERSION="v1"

(cd app-flex-site-update && zip -r ../app-flex-site-update-v1.zip .)

az functionapp deployment source config-zip \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src app-flex-site-update-v1.zip

az functionapp restart --resource-group "$RG" --name "$APP_NAME"
```

### 8.4 Test Execution

```bash
export FUNCTION_URL="https://$APP_NAME.azurewebsites.net/api/work"

cat > k6-deploy-transition.js <<'JS'
import http from "k6/http";
import { check, sleep } from "k6";

const target = __ENV.TARGET;
const sleepSec = __ENV.SLEEP || "1";

export const options = {
  vus: 20,
  duration: "20m",
};

export default function () {
  const res = http.get(`${target}?sleep=${sleepSec}`);
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(0.05);
}
JS

# 1) Start baseline load (run this in a separate terminal)
k6 run --env TARGET="$FUNCTION_URL" --env SLEEP="1" k6-deploy-transition.js

# 2) Wait 5 minutes for stable baseline
sleep 300

# 3) Deploy version v2 during active load
az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings APP_VERSION="v2"

(cd app-flex-site-update && zip -r ../app-flex-site-update-v2.zip .)
az functionapp deploy \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src-path app-flex-site-update-v2.zip \
  --type zip

# 4) Observe overlap window and version transition
for i in $(seq 1 120); do
  curl --silent "$FUNCTION_URL?sleep=1"
  sleep 5
done

# 5) Repeat with medium and long in-flight requests
k6 run --env TARGET="$FUNCTION_URL" --env SLEEP="5" k6-deploy-transition.js
k6 run --env TARGET="$FUNCTION_URL" --env SLEEP="30" k6-deploy-transition.js

# 6) Repeat complete cycle for 5 independent runs
for run in 1 2 3 4 5; do
  az functionapp restart --resource-group "$RG" --name "$APP_NAME"
  sleep 180
  k6 run --env TARGET="$FUNCTION_URL" --env SLEEP="5" k6-deploy-transition.js \
    --summary-export "summary-run-${run}.json"
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
  --analytics-query "requests | where timestamp > ago(6h) | where name has '/api/work' | summarize total=count(), failed=countif(success == false), p50=percentile(duration,50), p95=percentile(duration,95), p99=percentile(duration,99) by bin(timestamp, 1m) | order by timestamp asc" \
  --output table

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "requests | where timestamp > ago(6h) | where name has '/api/work' | extend appVersion=tostring(customDimensions['app_version']) | summarize count() by appVersion, bin(timestamp, 1m) | order by timestamp asc" \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP_NAME" \
  --metric "Requests" "Http5xx" "FunctionExecutionCount" \
  --interval PT1M \
  --aggregation Total \
  --output table

az functionapp log tail --resource-group "$RG" --name "$APP_NAME"
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Brief error spike (0-5 seconds) during instance replacement
- Short-lived requests (100ms) see fewer errors than long-lived requests (30s)
- `always_ready` instances may help reduce the cold-start burst after deployment
- Deployment method may affect the transition strategy

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

- Deployment slot behavior on Flex Consumption may differ from standard Consumption
- The drain timeout is platform-controlled; verify current default
- Long-running functions (>5 minutes) may be forcefully terminated during deployment

## 16. Related guide / official docs

- [Azure Functions Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [Deployment best practices - Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-best-practices)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
