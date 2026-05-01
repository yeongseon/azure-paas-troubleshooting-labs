# Container Apps Health Probe Lab

Reusable Flask + gunicorn lab assets for Container Apps health probe experiments #27-#31.

## What this lab covers

- Dependency-coupled readiness only
- Dependency-coupled readiness during outage toggles
- Dependency-coupled liveness + readiness
- Slow dependency timeout behavior
- Intermittent dependency failure behavior

The same image is reused for both the main app and the dependency app.

## Files

- `app/app.py` — unified Flask app for probe, traffic, and dependency simulation endpoints
- `app/Dockerfile` — Python 3.11 container image
- `scripts/deploy-dependency-coupled.sh` — deploys experiment #27 baseline topology

## Prerequisites

- Azure CLI authenticated
- Container Apps extension installed
- `openssl`

## Quick start

```bash
cd experiments/container-apps/health-probe-lab
chmod +x scripts/deploy-dependency-coupled.sh
./scripts/deploy-dependency-coupled.sh
```

Optional overrides:

```bash
RESOURCE_GROUP=rg-health-probe-lab-alt \
ENV_NAME=cae-health-probe-lab-alt \
ACR_NAME=acrhealthprobeabc123 \
./scripts/deploy-dependency-coupled.sh
```

## Dependency toggles

The dependency app is `ca-dependency` and uses the same image with `APP_MODE=dependency`.

Set unhealthy:

```bash
az containerapp update -n ca-dependency -g rg-health-probe-lab \
  --set-env-vars APP_NAME=ca-dependency APP_MODE=dependency DEPENDENCY_HEALTHY=false DEPENDENCY_DELAY_MS=0 DEPENDENCY_FAIL_RATE=0
```

Set slow dependency:

```bash
az containerapp update -n ca-dependency -g rg-health-probe-lab \
  --set-env-vars APP_NAME=ca-dependency APP_MODE=dependency DEPENDENCY_HEALTHY=true DEPENDENCY_DELAY_MS=2000 DEPENDENCY_FAIL_RATE=0
```

Set intermittent failures:

```bash
az containerapp update -n ca-dependency -g rg-health-probe-lab \
  --set-env-vars APP_NAME=ca-dependency APP_MODE=dependency DEPENDENCY_HEALTHY=true DEPENDENCY_DELAY_MS=0 DEPENDENCY_FAIL_RATE=50
```

Restore healthy:

```bash
az containerapp update -n ca-dependency -g rg-health-probe-lab \
  --set-env-vars APP_NAME=ca-dependency APP_MODE=dependency DEPENDENCY_HEALTHY=true DEPENDENCY_DELAY_MS=0 DEPENDENCY_FAIL_RATE=0
```

## Main endpoints

- `/startup` — startup probe endpoint
- `/live` — liveness probe endpoint
- `/ready` — readiness probe endpoint
- `/healthz` — local health endpoint
- `/dependency/health` — executes dependency check from the main app
- `/health` — dependency health endpoint when `APP_MODE=dependency`
- `/delay?seconds=N` — delayed response
- `/cpu?seconds=N` — CPU saturation helper
- `/status?code=N` — custom response status

## Clean up

```bash
az group delete --name rg-health-probe-lab --yes --no-wait
```

## Related experiment docs

- `docs/container-apps/...` experiment pages for #27-#31
- `../startup-probes/README.md` for the earlier startup-probe-only reference lab
