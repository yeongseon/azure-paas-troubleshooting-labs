# Startup Probes Experiment

Demonstrate how startup probes prevent premature restarts for slow-starting containers on Azure Container Apps.

## Prerequisites

- Azure CLI (`az`) authenticated
- `openssl` (for random suffix generation)

## Quick Start

```bash
# Deploy with 10s startup delay (default)
./scripts/deploy.sh

# Deploy with 30s startup delay to amplify the difference
STARTUP_DELAY_SECONDS=30 ./scripts/deploy.sh
```

This deploys two Container Apps:
- **slow-starter-no-probe** — no startup probe; may restart before ready
- **slow-starter-with-probe** — startup probe configured; waits for readiness

## What to Observe

1. **Container App** > Revisions & Replicas > check restart counts
2. **Log Analytics**:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s startswith "slow-starter"
| where Log_s contains "Startup complete" or Log_s contains "waiting"
| project TimeGenerated, ContainerAppName_s, Log_s
| order by TimeGenerated asc
```

3. **System logs** for probe failures:

```kql
ContainerAppSystemLogs_CL
| where ContainerAppName_s startswith "slow-starter"
| where Reason_s contains "Unhealthy" or Reason_s contains "BackOff"
| project TimeGenerated, ContainerAppName_s, Reason_s, Log_s
| order by TimeGenerated desc
```

## Endpoints

| Path | Description |
|------|-------------|
| `/healthz` | Health check (always 200 when ready) |
| `/readyz` | Readiness check (503 until ready) |
| `/stats` | Startup delay config and uptime |

## Expected Results

| Startup Delay | Without Probe | With Probe |
|---------------|--------------|------------|
| 10s | 0-2 restarts | 0 restarts |
| 30s | 2-5 restarts | 0 restarts |
| 60s | CrashLoopBackOff | 0 restarts |

## Clean Up

```bash
az group delete --name rg-startup-probe-lab --yes --no-wait
```
