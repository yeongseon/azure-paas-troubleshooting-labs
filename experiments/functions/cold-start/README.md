# Cold Start Experiment

Measure Azure Functions cold-start latency breakdown across host startup, package restore, framework initialization, and application code execution phases.

## Prerequisites

- Azure CLI (`az`) authenticated
- Azure Functions Core Tools (`func`)
- Python 3.11

## Experiment Design

This experiment deploys **one Function App per configuration** to isolate startup behavior. Each app varies along two axes:

| Axis | Values |
|------|--------|
| **Dependency profile** | `minimal` (1 package), `moderate` (10 packages), `heavy` (33 packages) |
| **Init profile** | `fast` (no delay), `slow` (2-second artificial delay at module level) |

Two hosting plans are tested: **Consumption** and **Flex Consumption**.

## Application Code

`app/function_app.py` contains the instrumented Function App with cold-start trace markers. The app emits structured markers at each startup phase boundary:

1. `coldstart.test.begin` — first line of user code execution
2. `coldstart.imports.begin` / `coldstart.imports.end` — heavy import window
3. `coldstart.appinit.begin` / `coldstart.appinit.end` — global singleton construction + optional delay
4. `coldstart.handler.begin` / `coldstart.handler.end` — first request handler

## Dependency Profiles

- `app/requirements.txt` — minimal (azure-functions only)
- `app/requirements-moderate.txt` — moderate (+ requests, pandas, numpy, etc.)
- `app/requirements-heavy.txt` — heavy (+ scipy, scikit-learn, matplotlib, etc.)

Copy the desired profile to `requirements.txt` before deploying each configuration.

## Deploy

```bash
RG="rg-func-coldstart-lab"
LOC="koreacentral"
STG="stcoldstartkc01"
APPINSIGHTS="appi-func-coldstart-kc"

az group create --name "$RG" --location "$LOC"

az storage account create \
  --name "$STG" \
  --resource-group "$RG" \
  --location "$LOC" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-shared-key-access false

az monitor app-insights component create \
  --app "$APPINSIGHTS" \
  --location "$LOC" \
  --resource-group "$RG" \
  --application-type web

# Consumption example: minimal + fast
az functionapp create \
  --name func-cold-py-min-fast-cons \
  --resource-group "$RG" \
  --storage-account "$STG" \
  --consumption-plan-location "$LOC" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --assign-identity [system] \
  --app-insights "$APPINSIGHTS"

# Configure managed identity storage access
SUB_ID=$(az account show --query id --output tsv)
STG_ID=$(az storage account show --name "$STG" --resource-group "$RG" --query id --output tsv)
PRINCIPAL_ID=$(az functionapp identity show --name func-cold-py-min-fast-cons --resource-group "$RG" --query principalId --output tsv)

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Owner" \
  --scope "$STG_ID"

az functionapp config appsettings set \
  --name func-cold-py-min-fast-cons \
  --resource-group "$RG" \
  --settings \
    AzureWebJobsStorage__accountName="$STG" \
    AzureWebJobsStorage__credential=managedidentity \
    DEPENDENCY_PROFILE="minimal" \
    INIT_PROFILE="fast" \
    PLAN_TYPE="consumption" \
    APPLICATIONINSIGHTS_SAMPLING_PERCENTAGE=100

# Deploy
cd app && func azure functionapp publish func-cold-py-min-fast-cons --python
```

## Measure Cold Starts

```bash
# Default: 10 rounds, 900s idle wait between rounds
python scripts/measure-cold-start.py \
    --function-url "https://func-cold-py-min-fast-cons.azurewebsites.net/api/coldstart" \
    --rounds 10 --idle-wait 900

# Quick validation with fewer rounds
python scripts/measure-cold-start.py \
    --function-url "https://func-cold-py-min-fast-cons.azurewebsites.net/api/coldstart" \
    --rounds 3 --idle-wait 600
```

## Expected Results

| Profile | Plan | Typical Cold Start |
|---------|------|--------------------|
| Minimal / Fast | Consumption | ~1.5-1.9 s |
| Minimal / Fast | Flex Consumption | ~1.1-1.4 s |
| Heavy / Fast | Consumption | ~8.0-8.6 s |
| Heavy / Fast | Flex Consumption | ~6.0-6.5 s |
| Heavy / Slow | Consumption | ~10.5-11.2 s |
| Heavy / Slow | Flex Consumption | ~8.4-8.5 s |

## What to Observe

1. **Application Insights traces** — look for `coldstart.*` markers to reconstruct phase durations
2. **Request duration** — compare cold vs warm request duration via Application Insights
3. **`uptime_seconds`** in response — values < 5s indicate a fresh instance
4. **Phase breakdown** — use KQL Query 3 from the experiment doc to derive per-phase milliseconds

## Clean Up

```bash
az group delete --name rg-func-coldstart-lab --yes --no-wait
```
