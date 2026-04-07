# Cold Start Experiment

Measure Azure Functions cold-start latency with a configurable initialization delay.

## Prerequisites

- Azure CLI (`az`) authenticated
- Azure Functions Core Tools (`func`)
- Python 3.9+

## Deploy

```bash
# Create resources
RG="rg-cold-start-lab"
FUNC_NAME="coldstartlab$(openssl rand -hex 4)"
STORAGE="coldstartstore$(openssl rand -hex 4)"
LOCATION="koreacentral"

az group create --name $RG --location $LOCATION

az storage account create --name $STORAGE --resource-group $RG \
    --location $LOCATION --sku Standard_LRS

az functionapp create --name $FUNC_NAME --resource-group $RG \
    --storage-account $STORAGE --consumption-plan-location $LOCATION \
    --runtime python --runtime-version 3.11 \
    --functions-version 4 --os-type Linux

# Set init delay (simulate heavy initialization)
az functionapp config appsettings set --name $FUNC_NAME --resource-group $RG \
    --settings INIT_DELAY_SECONDS=5

# Deploy function code
cd app && func azure functionapp publish $FUNC_NAME --python
```

## Measure Cold Starts

```bash
# Default: 3 rounds, 600s idle wait between rounds
python scripts/measure-cold-start.py \
    --function-url "https://${FUNC_NAME}.azurewebsites.net/api/ping"

# Quick test with shorter idle wait (may not trigger true cold start)
python scripts/measure-cold-start.py \
    --function-url "https://${FUNC_NAME}.azurewebsites.net/api/ping" \
    --rounds 2 --idle-wait 300
```

## Expected Results

| Scenario | Warm Latency | Cold Latency |
|----------|-------------|-------------|
| No init delay | ~50-200 ms | ~1-3 s |
| 5s init delay | ~50-200 ms | ~6-8 s |
| 10s init delay | ~50-200 ms | ~11-15 s |

Cold-start latency includes: instance allocation + runtime init + app init delay.

## What to Observe

1. **Application Insights** > Live Metrics during warm/cold transitions
2. **Function App** > Monitor > Invocations tab for duration spikes
3. Compare `uptime_seconds` in response — values < 5s indicate a fresh instance

## Clean Up

```bash
az group delete --name rg-cold-start-lab --yes --no-wait
```
