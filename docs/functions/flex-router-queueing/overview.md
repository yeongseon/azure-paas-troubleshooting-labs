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

# Flex Consumption Router Queueing Before Invocation

!!! info "Status: Planned"

## 1. Question

On Azure Functions Flex Consumption, what is the latency distribution between the request arriving at the Flex router and the function code beginning execution, and how does this "router queue time" vary under different load patterns?

## 2. Why this matters

Customers on Flex Consumption observe latency that cannot be explained by their function code execution time alone. The gap between request arrival and code invocation is spent in the Flex router's internal queue — waiting for an available instance, cold-starting a new instance, or routing to a warm instance. Understanding this hidden queue time is critical for setting realistic SLO expectations and choosing between Flex Consumption and other plans.

## 3. Customer symptom

- "My function takes 50ms to execute but the end-to-end latency is 3 seconds."
- "I see inconsistent latency — some requests are fast, others have a 2-5 second delay."
- "Application Insights shows function execution is fast but the overall duration is much longer."

## 4. Hypothesis

The Flex Consumption router introduces measurable queueing latency between request receipt and function invocation. This queue time will show:

1. Bimodal distribution: near-zero for warm instances, 1-5 seconds for cold allocations
2. Increased variance under burst load patterns
3. Correlation with the `always_ready` instance count setting

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

- Load pattern: steady (10 RPS), burst (0→100 RPS), periodic (10 RPS with 5-minute gaps)
- `always_ready` instance count: 0, 1, 3
- Function complexity: minimal (return immediately) vs medium (100ms CPU work)
- Request concurrency per run

**Observed:**

- End-to-end latency (client-measured)
- Function execution duration (Application Insights)
- Router queue time (calculated: end-to-end minus execution)
- Instance allocation events

**Independent run definition**: Fresh deployment with `always_ready` instances confirmed, 5-minute stabilization, identical load profile

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: First 2 minutes of steady load; no exclusion for burst patterns (burst IS the measurement)

**Primary metric**: Router queue time p95; meaningful effect threshold: 500ms absolute or 20% relative change

**Comparison method**: Mann-Whitney U on per-run p95 queue times

## 7. Instrumentation

- Application Insights: request traces with `duration` and custom `executionDuration` property
- Custom middleware: timestamp at function entry vs request receipt
- Azure Monitor: `FunctionExecutionCount`, `ActiveInstances`
- Load testing: k6 with precise request timing

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export RG="rg-flex-router-queueing-lab"
export LOCATION="koreacentral"
export APP_NAME="func-flex-router-queueing"
export STORAGE_NAME="stflexrouterq$RANDOM"
export APP_INSIGHTS_NAME="appi-flex-router-queueing"
export LOG_WORKSPACE_NAME="law-flex-router-queueing"

az group create --name "$RG" --location "$LOCATION"

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --allow-blob-public-access false \
  --allow-shared-key-access false

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LOG_WORKSPACE_NAME" \
  --location "$LOCATION"

az monitor app-insights component create \
  --resource-group "$RG" \
  --app "$APP_INSIGHTS_NAME" \
  --location "$LOCATION" \
  --workspace "$LOG_WORKSPACE_NAME" \
  --application-type web

az functionapp create \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --storage-account "$STORAGE_NAME" \
  --flexconsumption-location "$LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4
```

### 8.2 Application Code

```python
import json
import time
from datetime import datetime, timezone
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="probe", methods=["GET"])
def probe(req: func.HttpRequest) -> func.HttpResponse:
    entry = time.perf_counter()
    work_ms = int(req.params.get("work_ms", "50"))
    time.sleep(work_ms / 1000)
    exec_ms = round((time.perf_counter() - entry) * 1000, 2)
    payload = {
        "entry_utc": datetime.now(timezone.utc).isoformat(),
        "execution_ms": exec_ms,
        "work_ms": work_ms,
    }
    return func.HttpResponse(
        body=json.dumps(payload),
        status_code=200,
        mimetype="application/json",
        headers={"x-execution-ms": str(exec_ms)},
    )
```

```yaml
experiment_matrix:
  - always_ready: 0
    profile: steady-10rps
  - always_ready: 0
    profile: burst-100rps
  - always_ready: 1
    profile: steady-10rps
  - always_ready: 3
    profile: burst-100rps
```

### 8.3 Deploy

```bash
az functionapp identity assign --resource-group "$RG" --name "$APP_NAME"

PRINCIPAL_ID=$(az functionapp identity show --resource-group "$RG" --name "$APP_NAME" --query principalId --output tsv)
STORAGE_ID=$(az storage account show --resource-group "$RG" --name "$STORAGE_NAME" --query id --output tsv)

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

az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings AzureWebJobsStorage__accountName="$STORAGE_NAME" FUNCTIONS_WORKER_RUNTIME=python

zip -r functionapp-flex-router-queueing.zip .
az functionapp deployment source config-zip \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src functionapp-flex-router-queueing.zip
```

### 8.4 Test Execution

```bash
export FUNCTION_URL="https://$APP_NAME.azurewebsites.net/api/probe"

# Scenario A: always_ready=0, steady 10 RPS for 10 minutes
for i in $(seq 1 600); do
  START_MS=$(python3 -c "import time; print(int(time.time()*1000))")
  RESP=$(curl "$FUNCTION_URL?work_ms=50")
  END_MS=$(python3 -c "import time; print(int(time.time()*1000))")
  E2E_MS=$((END_MS-START_MS))
  EXEC_MS=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('execution_ms',0))" "$RESP")
  QUEUE_MS=$(python3 -c "import sys; print(max(0, float(sys.argv[1]) - float(sys.argv[2])))" "$E2E_MS" "$EXEC_MS")
  printf "%s\t%s\t%s\n" "$E2E_MS" "$EXEC_MS" "$QUEUE_MS" >> steady-10rps.tsv
  sleep 0.1
done

# Scenario B: burst 0 -> 100 RPS, 60 seconds (repeat for always_ready=0,1,3)
for i in $(seq 1 6000); do
  START_MS=$(python3 -c "import time; print(int(time.time()*1000))")
  curl --output /dev/null "$FUNCTION_URL?work_ms=50" &
  sleep 0.01
done
wait

# Update always_ready setting between runs
az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings WEBSITE_ALWAYS_READY_INSTANCE_COUNT=1

az functionapp restart --resource-group "$RG" --name "$APP_NAME"
```

### 8.5 Data Collection

```bash
APP_INSIGHTS_ID=$(az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APP_INSIGHTS_NAME" \
  --query appId --output tsv)

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "requests | where timestamp > ago(4h) | project timestamp, duration, success, resultCode, operation_Id | order by timestamp asc" \
  --output table

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "customMetrics | where timestamp > ago(4h) and name in ('FunctionExecutionCount','ActiveInstances') | project timestamp, name, value | order by timestamp asc" \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP_NAME" \
  --metric "Requests" "FunctionExecutionCount" \
  --interval PT1M \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Router queue time is bimodal: <50ms for warm hits, 1-5s for cold allocations
- With `always_ready=0`, first requests in burst show 2-5s queue time
- With `always_ready=3`, queue time stays <200ms up to ~3× concurrency capacity
- p95 queue time is consistent across 5 runs within each configuration (±500ms)

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

- Flex Consumption instance allocation behavior may differ by region due to capacity
- `always_ready` instances take time to provision after deployment — verify they're actually running before starting the test
- Router queue time is not directly exposed as a metric; it must be calculated from timestamps

## 16. Related guide / official docs

- [Azure Functions Flex Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan)
- [Azure Functions scaling and hosting](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale)
- [azure-functions-practical-guide](https://github.com/yeongseon/azure-functions-practical-guide)
