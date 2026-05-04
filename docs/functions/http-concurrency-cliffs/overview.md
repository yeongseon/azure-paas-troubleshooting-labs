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

# HTTP Concurrency Cliffs on Flex Consumption

!!! warning "Status: Draft - Blocked"
    Execution blocked: Flex Consumption plan creation blocked by Azure Policy.

## 1. Question

At what HTTP concurrency level does a single Flex Consumption instance begin to degrade (increased latency, errors, or worker restarts), and is this cliff predictable and consistent across runs?

## 2. Why this matters

Flex Consumption allows configuring `http.maxConcurrentRequests` in `host.json`. Setting this too high overloads a single instance; setting it too low wastes instances. Customers need to know the practical concurrency ceiling — not the theoretical limit — so they can configure scaling triggers appropriately. The "cliff" behavior (sudden degradation rather than gradual) is particularly dangerous because monitoring may not catch it until requests are already failing.

## 3. Customer symptom

- "Everything is fine at 50 concurrent requests but at 80 it suddenly falls apart."
- "We increased maxConcurrentRequests to 200 and now we're seeing 500 errors."
- "Latency is stable until we hit some threshold, then p99 goes from 200ms to 30 seconds."

## 4. Hypothesis

Each Flex Consumption instance has a practical concurrency ceiling that depends on the function's resource consumption (CPU, memory, I/O). Beyond this ceiling:

1. Latency increases non-linearly (cliff behavior, not gradual degradation)
2. The cliff point is reproducible across runs (±10% variance)
3. The cliff point correlates with CPU saturation or memory pressure, not just request count

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

- Concurrency ramp: 10, 25, 50, 75, 100, 150, 200 concurrent requests
- Function payload: CPU-light (JSON parse), CPU-medium (image resize), I/O-bound (HTTP call)
- `maxConcurrentRequests`: 100, 200, unbounded
- Duration per concurrency level: 5 minutes steady state

**Observed:**

- Response latency distribution (p50, p95, p99) per concurrency level
- Error rate per concurrency level
- Worker restart events
- Memory and CPU consumption per instance

**Independent run definition**: Fresh deployment, single instance pinned (always_ready=1, max scale=1), identical ramp profile

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: First 2 minutes at each concurrency level

**Primary metric**: p95 latency; meaningful effect threshold: 2× increase from previous concurrency step

**Comparison method**: Per-run cliff detection; Mann-Whitney U comparing cliff-point concurrency across runs

## 7. Instrumentation

- Application Insights: request traces, performance counters
- Custom function middleware: per-request timing, concurrent request counter
- Azure Monitor: `ProcessCpuPercentage`, `ProcessMemoryMB`
- k6 load generator with step-up concurrency profile

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-http-concurrency-cliffs-lab"
export LOCATION="koreacentral"
export APP_NAME="func-http-concurrency-cliffs-$RANDOM"
export STORAGE_NAME="sthttpcliff$RANDOM"
export APP_INSIGHTS_NAME="appi-http-concurrency-cliffs"
export LOG_WORKSPACE_NAME="law-http-concurrency-cliffs"

az account set --subscription "$SUBSCRIPTION_ID"

az group create --name "$RG" --location "$LOCATION"

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --allow-shared-key-access false \
  --min-tls-version TLS1_2

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LOG_WORKSPACE_NAME" \
  --location "$LOCATION"

az monitor app-insights component create \
  --resource-group "$RG" \
  --app "$APP_INSIGHTS_NAME" \
  --workspace "$LOG_WORKSPACE_NAME" \
  --location "$LOCATION" \
  --application-type web

az functionapp create \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --storage-account "$STORAGE_NAME" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --flexconsumption-location "$LOCATION"

az functionapp identity assign \
  --resource-group "$RG" \
  --name "$APP_NAME"

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
import threading
import time
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
active_requests = 0
lock = threading.Lock()


@app.route(route="probe", methods=["GET"])
def probe(req: func.HttpRequest) -> func.HttpResponse:
    global active_requests
    mode = req.params.get("mode", "cpu-light")
    started = time.perf_counter()

    with lock:
        active_requests += 1
        current_concurrency = active_requests

    try:
        if mode == "cpu-medium":
            end = time.perf_counter() + 0.2
            x = 0
            while time.perf_counter() < end:
                x += 1
        elif mode == "io-bound":
            time.sleep(0.2)
        else:
            payload = json.loads('{"hello":"world","n":1}')
            _ = payload.get("hello")

        exec_ms = round((time.perf_counter() - started) * 1000, 2)
        body = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "execution_ms": exec_ms,
            "observed_concurrency": current_concurrency,
        }
        return func.HttpResponse(
            body=json.dumps(body),
            status_code=200,
            mimetype="application/json",
            headers={
                "x-execution-ms": str(exec_ms),
                "x-observed-concurrency": str(current_concurrency),
            },
        )
    finally:
        with lock:
            active_requests -= 1
```

```yaml
version: "2.0"
logging:
  applicationInsights:
    samplingSettings:
      isEnabled: true
      excludedTypes: Request
extensions:
  http:
    routePrefix: "api"
    maxConcurrentRequests: 100
    maxOutstandingRequests: 200
functionTimeout: "00:10:00"
```

### 8.3 Deploy

```bash
mkdir -p app-http-concurrency-cliffs

cat > app-http-concurrency-cliffs/function_app.py <<'PY'
# paste Python from section 8.2
PY

cat > app-http-concurrency-cliffs/host.json <<'JSON'
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "extensions": {
    "http": {
      "routePrefix": "api",
      "maxConcurrentRequests": 100,
      "maxOutstandingRequests": 200
    }
  },
  "functionTimeout": "00:10:00"
}
JSON

cat > app-http-concurrency-cliffs/requirements.txt <<'TXT'
azure-functions
TXT

az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings \
    AzureWebJobsStorage__accountName="$STORAGE_NAME" \
    FUNCTIONS_EXTENSION_VERSION="~4" \
    FUNCTIONS_WORKER_RUNTIME="python"

(cd app-http-concurrency-cliffs && zip -r ../app-http-concurrency-cliffs.zip .)

az functionapp deployment source config-zip \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src app-http-concurrency-cliffs.zip

az functionapp restart --resource-group "$RG" --name "$APP_NAME"
```

### 8.4 Test Execution

```bash
export FUNCTION_URL="https://$APP_NAME.azurewebsites.net/api/probe"

cat > k6-cliff.js <<'JS'
import http from "k6/http";
import { check, sleep } from "k6";

const mode = __ENV.MODE || "cpu-light";
const target = __ENV.TARGET;

export const options = {
  scenarios: {
    stepped: {
      executor: "ramping-vus",
      startVUs: 10,
      stages: [
        { duration: "5m", target: 10 },
        { duration: "5m", target: 25 },
        { duration: "5m", target: 50 },
        { duration: "5m", target: 75 },
        { duration: "5m", target: 100 },
        { duration: "5m", target: 150 },
        { duration: "5m", target: 200 }
      ]
    }
  }
};

export default function () {
  const res = http.get(`${target}?mode=${mode}`);
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(0.1);
}
JS

# 1) Run cpu-light profile with maxConcurrentRequests=100
k6 run --env TARGET="$FUNCTION_URL" --env MODE="cpu-light" k6-cliff.js

# 2) Run cpu-medium profile
k6 run --env TARGET="$FUNCTION_URL" --env MODE="cpu-medium" k6-cliff.js

# 3) Run io-bound profile
k6 run --env TARGET="$FUNCTION_URL" --env MODE="io-bound" k6-cliff.js

# 4) Raise host HTTP concurrency and repeat matrix
cat > app-http-concurrency-cliffs/host.json <<'JSON'
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": "api",
      "maxConcurrentRequests": 200,
      "maxOutstandingRequests": 400
    }
  }
}
JSON

(cd app-http-concurrency-cliffs && zip -r ../app-http-concurrency-cliffs.zip .)
az functionapp deployment source config-zip \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src app-http-concurrency-cliffs.zip

k6 run --env TARGET="$FUNCTION_URL" --env MODE="cpu-light" k6-cliff.js

# 5) For reproducibility, execute each profile 5 times and keep raw outputs
for run in 1 2 3 4 5; do
  k6 run --env TARGET="$FUNCTION_URL" --env MODE="cpu-medium" k6-cliff.js \
    --summary-export "summary-cpu-medium-run${run}.json"
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
  --analytics-query "requests | where timestamp > ago(8h) | where name has '/api/probe' | summarize p50=percentile(duration,50), p95=percentile(duration,95), p99=percentile(duration,99), errors=countif(success == false) by bin(timestamp, 5m) | order by timestamp asc" \
  --output table

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "traces | where timestamp > ago(8h) | where customDimensions has 'observed_concurrency' | project timestamp, message, customDimensions | order by timestamp asc" \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP_NAME" \
  --metric "Requests" "Http5xx" "AverageResponseTime" \
  --interval PT1M \
  --aggregation Average Maximum Total \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP_NAME" \
  --metric "CpuPercentage" "MemoryWorkingSet" \
  --interval PT1M \
  --aggregation Average Maximum \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Latency remains stable up to a concurrency threshold, then increases sharply
- The cliff point varies by function type: CPU-light ~100-150, CPU-medium ~50-75, I/O-bound ~75-100
- Error rate transitions from 0% to >5% within a single concurrency step at the cliff
- Cliff point is consistent across 5 runs (±10 concurrent requests)

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

- Pin to a single instance using `always_ready=1` and maximum instance count=1 to isolate per-instance behavior
- Flex Consumption instance sizes may vary; check actual CPU/memory allocation
- Worker process recycling can reset the concurrency state mid-test

## 16. Related guide / official docs

- [Azure Functions Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [host.json reference - HTTP settings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-host-json#http)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
