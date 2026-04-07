# Memory Pressure Experiment

Reproduce memory pressure on Azure App Service (Linux) by deploying Flask apps that allocate a configurable block of memory at startup.

## Prerequisites

- Azure CLI (`az`) authenticated
- Python 3.9+
- `zip` command available

## Quick Start

```bash
# Deploy 2 apps, each allocating 100 MB
./scripts/deploy.sh

# Deploy with custom settings
ALLOC_MB=200 APP_COUNT=3 PLAN_SKU=B1 ./scripts/deploy.sh
```

## Generate Load

```bash
python scripts/traffic-gen.py --base-url https://memlabapp-1.azurewebsites.net \
    --duration 300 --concurrency 10
```

## What to Observe

1. **Azure Portal** > App Service Plan > Metrics > Memory Percentage
2. **Diagnose and Solve Problems** > Memory Usage detector
3. **Log Analytics** (if connected):

```kql
AppServicePlatformLogs
| where TimeGenerated > ago(30m)
| where Level == "Warning" or Level == "Error"
| project TimeGenerated, Level, Message
| order by TimeGenerated desc
```

## Expected Results

| ALLOC_MB | App Count | B1 (1.75 GB) Behavior |
|----------|-----------|----------------------|
| 100      | 2         | Stable (~12% each)   |
| 300      | 2         | Elevated (~35% each) |
| 500      | 2         | OOM restarts likely  |

## Clean Up

```bash
az group delete --name rg-memory-pressure-lab --yes --no-wait
```
