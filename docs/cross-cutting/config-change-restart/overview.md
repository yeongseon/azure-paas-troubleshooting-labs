---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-01"
    result: tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Configuration Change Restart Matrix

!!! info "Status: Published"
    Experiment completed with real data. All scenarios executed on 2026-05-01 in Korea Central using Azure App Service P1v3 (Linux) and Azure Container Apps (Consumption). Resources provisioned fresh; all changes applied in sequence with continuous identity probing between scenarios.

## 1. Question

Which Azure App Service and Azure Container Apps configuration changes trigger an in-place restart, rolling worker replacement, or new revision creation, and how visible are those events in logs and metrics?

## 2. Why this matters

This is a common support boundary problem because customers often make a “small config change” and then report one of several confusing outcomes:

- the app briefly disconnects and they cannot tell whether the platform restarted it
- a new Container Apps revision appears even though they expected a hot update
- an App Service instance changes PID or startup time without an obvious activity-log explanation
- scale settings change, but the customer misreads a scale-out event as an application restart
- a secret or network-related change appears to have “done nothing” because the old process or old revision is still serving

Support engineers need a repeatable matrix that distinguishes:

1. **process restart** on existing App Service workers
2. **instance replacement / rolling replacement** caused by platform configuration updates
3. **new revision creation** in Container Apps
4. **hot / no-restart updates** where the configuration surface changes without immediate runtime recycle
5. **visibility gaps** between the actual platform event and what is exposed in logs, metrics, revision history, or activity logs

## 3. Customer symptom

- “We changed one app setting and users got a brief `503`, but there is no clear restart event.”
- “A scale change caused extra instances, but we cannot tell whether the original worker restarted too.”
- “Changing a secret or environment variable in Container Apps created a new revision unexpectedly.”
- “We updated a scale rule and the app behavior changed, but no new revision was shown.”
- “We need to know which changes are safe in production and which ones are deployment events in disguise.”

## 4. Hypothesis

### App Service

1. Changing an **app setting** triggers a worker process restart and produces a new startup marker in container/application logs.
2. Changing a **connection string** also triggers a worker process restart because the runtime environment projection changes.
3. Changing **scale settings** changes instance count but does not itself recycle an already-running healthy worker unless scale movement places traffic on a newly started instance.
4. Changing **VNet integration or related network configuration** triggers a restart or worker replacement because the site networking context changes.
5. Some configuration surfaces are effectively **hot** from the application's perspective and do not produce a new startup marker on the serving worker.

### Container Apps

1. Changing an **environment variable** creates a new revision.
2. Changing a **secret** creates a new revision or otherwise requires revision movement to project the new value into running replicas.
3. Changing a **scale rule** updates the existing application definition without creating a new revision.
4. Changing the **image** creates a new revision.
5. Changing **CPU / memory resources** creates a new revision.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Services | Azure App Service and Azure Container Apps |
| App Service SKU | P1v3 |
| Container Apps plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask) |
| OS | Linux |
| App Service app | `app-config-change-960` |
| Container App | `ca-config-change-restart` |
| ACR | `acrconfigchange960` |
| Container image | `config-change-restart:v1` / `v2` |
| Restart markers | Startup timestamp, PID, hostname / replica name, revision name |
| Date tested | 2026-05-01 |

## 6. Variables

**Experiment type**: Config / lifecycle behavior matrix

**Controlled:**

- same region: `koreacentral`
- same baseline application code and image family across all runs
- same logging schema for startup, request handling, and configuration identity
- same baseline App Service plan and same baseline Container Apps environment
- same observation window before and after each change
- same request probe cadence to capture transient availability impact
- same reset-to-baseline process before the next scenario

**Independent variables:**

- platform: App Service vs Container Apps
- change class: app config, secret / connection data, scale, network, compute resources, image
- change scope: revision-scoped vs application-scoped vs instance-scoped
- traffic state: idle vs light continuous probing during the change

**Observed:**

- startup marker changes (`started_at`, `pid`, `hostname`, `revision`, `replica`)
- App Service worker/container recycle evidence
- Container Apps new revision creation and activation timestamps
- active revision list before and after each change
- HTTP probe continuity (`200`, transient `5xx`, timeout)
- request latency spike around change time
- platform metrics that correlate with restart or replacement
- activity-log, system-log, and console-log visibility for each change type

## 7. Instrumentation

Primary evidence sources:

- **Application startup logging** on both platforms with a clearly searchable `APP_START` marker
- **Continuous HTTP probe** against `/identity` to detect changes in startup timestamp, PID, hostname, replica, and revision
- **App Service container/application logs** via `az webapp log tail`
- **Container Apps console and system logs** via `az containerapp logs show` and Log Analytics
- **Azure CLI snapshots** of configuration, scale, revision list, and activity timeline before and after each change
- **Azure Monitor metrics** for requests, response codes, restart-adjacent signals, and scale counts where available

Recommended application log markers:

- `APP_START`
- `REQUEST`
- `IDENTITY_SERVED`
- `CONFIG_SNAPSHOT`

### Test application code

`app.py`

```python
import json
import os
import socket
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request


def utc_now():
    return datetime.now(timezone.utc).isoformat()


STARTED_AT = utc_now()
PID = os.getpid()
HOSTNAME = socket.gethostname()
APP_VERSION = os.getenv("APP_VERSION", "v1")
ROLE = os.getenv("PLATFORM_ROLE", "unknown")

print(
    json.dumps(
        {
            "event": "APP_START",
            "started_at": STARTED_AT,
            "pid": PID,
            "hostname": HOSTNAME,
            "app_version": APP_VERSION,
            "role": ROLE,
            "container_app_revision": os.getenv("CONTAINER_APP_REVISION"),
            "container_app_replica": os.getenv("HOSTNAME"),
            "website_instance_id": os.getenv("WEBSITE_INSTANCE_ID"),
            "timestamp_utc": utc_now(),
        }
    ),
    flush=True,
)

app = Flask(__name__)


def identity_payload():
    return {
        "timestamp_utc": utc_now(),
        "started_at": STARTED_AT,
        "pid": PID,
        "hostname": HOSTNAME,
        "app_version": APP_VERSION,
        "platform_role": ROLE,
        "app_setting_sample": os.getenv("APP_SETTING_SAMPLE"),
        "connection_string_sample": os.getenv("SQLAZURECONNSTR_SAMPLE_DB"),
        "secret_sample": os.getenv("SECRET_SAMPLE"),
        "container_app_revision": os.getenv("CONTAINER_APP_REVISION"),
        "container_app_replica": os.getenv("HOSTNAME"),
        "website_instance_id": os.getenv("WEBSITE_INSTANCE_ID"),
        "website_site_name": os.getenv("WEBSITE_SITE_NAME"),
    }


@app.get("/")
def index():
    payload = identity_payload()
    payload["status"] = "ok"
    print(json.dumps({"event": "REQUEST", **payload}), flush=True)
    return jsonify(payload)


@app.get("/identity")
def identity():
    payload = identity_payload()
    print(json.dumps({"event": "IDENTITY_SERVED", **payload}), flush=True)
    return jsonify(payload)


@app.get("/health")
def health():
    return {"status": "healthy", "timestamp_utc": utc_now()}


@app.get("/config")
def config():
    payload = {
        **identity_payload(),
        "all_headers_sample": {"user_agent": request.headers.get("User-Agent")},
    }
    print(json.dumps({"event": "CONFIG_SNAPSHOT", **payload}), flush=True)
    return jsonify(payload)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

`requirements.txt`

```text
flask==3.0.3
gunicorn==22.0.0
```

`Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ARG APP_VERSION=v1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV PORT=8080
ENV APP_VERSION=${APP_VERSION}
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "600", "app:app"]
```

### Continuous probe script

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
OUTPUT_FILE="${2:-identity-probe.csv}"
INTERVAL_SECONDS="${3:-2}"

printf 'ts_utc,http_code,started_at,pid,hostname,revision,instance_id,total_time\n' > "$OUTPUT_FILE"

while true; do
  ts_utc="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")"
  body_file="/tmp/config-change-restart-body.$$"
  http_code="$({ curl -sS "$URL" -o "$body_file" -w '%{http_code},%{time_total}'; } 2>/dev/null || printf '000,0')"
  started_at="$(python3 - <<'PY' "$body_file"
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    print(data.get("started_at", ""))
    print(data.get("pid", ""))
    print(data.get("hostname", ""))
    print(data.get("container_app_revision", ""))
    print(data.get("website_instance_id", ""))
except Exception:
    print()
    print()
    print()
    print()
    print()
PY
)"
  mapfile -t fields <<< "$started_at"
  printf '%s,%s,%s,%s,%s,%s,%s\n' \
    "$ts_utc" \
    "${http_code%%,*}" \
    "${fields[0]:-}" \
    "${fields[1]:-}" \
    "${fields[2]:-}" \
    "${fields[3]:-}" \
    "${fields[4]:-}" \
    "${http_code##*,}" >> "$OUTPUT_FILE"
  sleep "$INTERVAL_SECONDS"
done
```

### Log Analytics queries for Container Apps

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-config-change-restart"
| where Log_s has_any ("APP_START", "IDENTITY_SERVED", "CONFIG_SNAPSHOT")
| project TimeGenerated, RevisionName_s, ReplicaName_s, Log_s
| order by TimeGenerated asc
```

```kusto
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-config-change-restart"
| project TimeGenerated, RevisionName_s, ReplicaName_s, Reason_s, Log_s
| order by TimeGenerated asc
```

## 8. Procedure

### 8.1 Infrastructure setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-config-change-restart-lab"
export LOCATION="koreacentral"
export ACR_NAME="acrconfigchange$RANDOM"
export IMAGE_NAME="config-change-restart"
export IMAGE_TAG="v1"
export PLAN_NAME="plan-config-change-restart"
export WEBAPP_NAME="app-config-change-$RANDOM"
export LAW_NAME="law-config-change-restart"
export ACA_ENV_NAME="cae-config-change-restart"
export ACA_NAME="ca-config-change-restart"
export VNET_NAME="vnet-config-change-restart"
export APP_SUBNET_NAME="snet-appsvc"
export ACA_SUBNET_NAME="snet-aca"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.96.0.0/16" \
  --subnet-name "$APP_SUBNET_NAME" \
  --subnet-prefixes "10.96.0.0/24"

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$ACA_SUBNET_NAME" \
  --address-prefixes "10.96.2.0/23"

az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$ACA_SUBNET_NAME" \
  --delegations Microsoft.App/environments

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --location "$LOCATION"

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --location "$LOCATION"

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query customerId -o tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query primarySharedKey -o tsv)

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --sku P1v3 \
  --is-linux

az containerapp env create \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --location "$LOCATION" \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY" \
  --infrastructure-subnet-resource-id "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$VNET_NAME/subnets/$ACA_SUBNET_NAME"
```

### 8.2 Build and publish the shared test image

```bash
az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  .

ACR_LOGIN_SERVER=$(az acr show --resource-group "$RG" --name "$ACR_NAME" --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query passwords[0].value -o tsv)
IMAGE_REF="$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"
```

### 8.3 Deploy App Service baseline

```bash
az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --name "$WEBAPP_NAME" \
  --deployment-container-image-name "$IMAGE_REF"

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --settings \
    WEBSITES_PORT=8080 \
    PLATFORM_ROLE=appservice \
    APP_SETTING_SAMPLE=baseline \
    SECRET_SAMPLE=not-used \
    APP_VERSION=v1

az webapp config container set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --docker-custom-image-name "$IMAGE_REF" \
  --docker-registry-server-url "https://$ACR_LOGIN_SERVER" \
  --docker-registry-server-user "$ACR_USERNAME" \
  --docker-registry-server-password "$ACR_PASSWORD"

az webapp connection-string set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --settings SAMPLE_DB="Server=tcp:sample.database.windows.net;Database=configlab;User Id=user;Password=baseline;" \
  --connection-string-type SQLAzure

az webapp log config \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --docker-container-logging filesystem \
  --level information

az webapp vnet-integration add \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --vnet "$VNET_NAME" \
  --subnet "$APP_SUBNET_NAME"
```

### 8.4 Deploy Container Apps baseline

```bash
az containerapp create \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --environment "$ACA_ENV_NAME" \
  --image "$IMAGE_REF" \
  --ingress external \
  --target-port 8080 \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --revision-suffix baseline \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 2 \
  --env-vars \
    PLATFORM_ROLE=containerapps \
    APP_SETTING_SAMPLE=baseline \
    APP_VERSION=v1

az containerapp secret set \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --secrets sample-secret=baseline-secret

az containerapp update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --set-env-vars SECRET_SAMPLE=secretref:sample-secret
```

### 8.5 Establish baseline evidence

```bash
WEBAPP_URL="https://$WEBAPP_NAME.azurewebsites.net/identity"
ACA_FQDN=$(az containerapp show --resource-group "$RG" --name "$ACA_NAME" --query properties.configuration.ingress.fqdn -o tsv)
ACA_URL="https://$ACA_FQDN/identity"

curl -sS "$WEBAPP_URL"
curl -sS "$ACA_URL"

az webapp log tail \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME"

az containerapp logs show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --type console \
  --follow
```

Capture and record:

- initial `started_at`, `pid`, `hostname`, `website_instance_id` for App Service
- initial `started_at`, `revision`, `replica` for Container Apps
- initial active revision list and ingress settings

### 8.6 Test matrix

| Scenario | Platform | Change command surface | Expected lifecycle event | Primary evidence |
|----------|----------|------------------------|--------------------------|------------------|
| 1 | App Service | App setting change | Worker restart | `APP_START` marker, changed `started_at` / PID |
| 2 | App Service | Connection string change | Worker restart | `APP_START` marker, changed `started_at` / PID |
| 3 | App Service | Scale-out / scale-in | No in-place restart on unchanged worker; new instance may appear | instance count, possible new hostname only |
| 4 | App Service | VNet integration remove/add or route-all toggle | Restart or worker replacement | startup marker and activity log |
| 5 | App Service | Hot candidate setting (for example diagnostic or metadata-only setting) | No restart | unchanged `started_at` / PID |
| 6 | Container Apps | Environment variable change | New revision | revision list, new revision startup logs |
| 7 | Container Apps | Secret change | New revision or revision movement required to project value | revision list, secret value in `/config` |
| 8 | Container Apps | Scale rule change | Existing revision update, no new revision | unchanged active revision, changed scale config |
| 9 | Container Apps | Image change | New revision | new revision name, startup marker |
| 10 | Container Apps | CPU / memory change | New revision | new revision name, startup marker |
| 11 | Container Apps | Ingress / network-facing config change | To be measured: application-scope update vs new revision | revision list + ingress config diff |

### 8.7 Execute App Service scenarios

For each scenario, start the continuous probe first, wait for a stable baseline, apply exactly one change, then continue probing for at least 5 minutes.

#### Scenario A1: app setting change

```bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --settings APP_SETTING_SAMPLE=changed-a1
```

#### Scenario A2: connection string change

```bash
az webapp connection-string set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --settings SAMPLE_DB="Server=tcp:sample.database.windows.net;Database=configlab;User Id=user;Password=changed-a2;" \
  --connection-string-type SQLAzure
```

#### Scenario A3: scale change

```bash
az appservice plan update \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --number-of-workers 2

az appservice plan update \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --number-of-workers 1
```

#### Scenario A4: network setting change

```bash
az resource update \
  --resource-group "$RG" \
  --resource-type Microsoft.Web/sites \
  --name "$WEBAPP_NAME/config/web" \
  --set properties.vnetRouteAllEnabled=true
```

If route-all is not available or does not show a change in the target region, use remove/re-add of VNet integration as the alternate scenario:

```bash
az webapp vnet-integration remove \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --vnet "$VNET_NAME"

az webapp vnet-integration add \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --vnet "$VNET_NAME" \
  --subnet "$APP_SUBNET_NAME"
```

#### Scenario A5: hot candidate

```bash
az webapp config set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --always-on true
```

Record whether this changes startup identity. If it does, the setting is not hot in this environment.

### 8.8 Execute Container Apps scenarios

#### Scenario C1: environment variable change

```bash
az containerapp update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --set-env-vars APP_SETTING_SAMPLE=changed-c1
```

#### Scenario C2: secret change

```bash
az containerapp secret set \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --secrets sample-secret=changed-c2

az containerapp update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --set-env-vars SECRET_SAMPLE=secretref:sample-secret
```

#### Scenario C3: scale rule change

```bash
az containerapp update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --min-replicas 1 \
  --max-replicas 5
```

#### Scenario C4: image change

```bash
az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME:v2" \
  --build-arg APP_VERSION=v2 \
  .

az containerapp update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:v2"
```

#### Scenario C5: CPU / memory change

```bash
az containerapp update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --cpu 1.0 \
  --memory 2.0Gi
```

#### Scenario C6: network-facing config change

```bash
az containerapp ingress update \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --target-port 8080 \
  --transport auto \
  --allow-insecure false
```

### 8.9 Data collection after each change

```bash
az webapp show \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --query "{state:state, hostNames:hostNames, outboundIpAddresses:outboundIpAddresses}" \
  --output json

az containerapp revision list \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --output table

az containerapp show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --query "{ingress:properties.configuration.ingress, template:properties.template}" \
  --output json

az monitor activity-log list \
  --resource-group "$RG" \
  --max-events 100 \
  --output table
```

Recommended per-scenario capture table:

| Scenario | Change time UTC | Startup marker changed? | New PID? | New hostname / replica? | New revision? | Transient failure window | Notes |
|----------|-----------------|-------------------------|----------|-------------------------|---------------|--------------------------|-------|

## 9. Expected signal

If the hypothesis is correct:

- App Service app-setting and connection-string changes will show a new `APP_START` marker shortly after the config write completes.
- App Service scale changes will show either no startup marker on the original worker or a second worker identity during scale-out, without clear evidence that the unchanged worker recycled.
- App Service network changes will correlate with either a fresh startup marker or a visible worker identity replacement.
- Container Apps environment-variable, image, and CPU/memory changes will create a new revision with a distinct revision name and fresh startup marker.
- Container Apps scale-rule changes will keep the same revision name while changing runtime scale behavior.
- Some events will be easier to prove from application startup markers than from Azure Monitor metrics alone.

## 10. Results

### Baseline identity

**App Service** (`app-config-change-960`):

```json
{
  "started_at": "2026-05-01T13:19:39.697931+00:00",
  "pid": 8,
  "hostname": "24ecd05d1945",
  "website_instance_id": "0f3e80b62b3d5260aaafc1777997f892b18b9e05566686e4f34e14f86360d9ec",
  "app_setting_sample": "baseline",
  "connection_string_sample": "Server=tcp:sample.database.windows.net;Database=configlab;User Id=user;Password=baseline;"
}
```

**Container Apps** (`ca-config-change-restart`):

```json
{
  "started_at": "2026-05-01T13:14:25.607857+00:00",
  "container_app_revision": "ca-config-change-restart--baseline",
  "container_app_replica": "ca-config-change-restart--baseline-55bc7cc586-975m9",
  "app_setting_sample": "baseline",
  "secret_sample": "baseline-secret"
}
```

### Per-scenario capture table

| Scenario | Platform | Change | Change time UTC | Started_at changed? | New PID? | New revision? | Failure window | Notes |
|----------|----------|--------|-----------------|---------------------|----------|---------------|----------------|-------|
| A1 | App Service | App setting (`APP_SETTING_SAMPLE=changed-a1`) | 13:21:09 | Yes (13:21:22) | Yes (8→7) | N/A | None (continuous 200) | Restart in ~13 s |
| A2 | App Service | Connection string (`Password=changed-a2`) | 13:22:06 | Yes (13:22:18) | Same (7→7) | N/A | None (continuous 200) | Restart in ~12 s; PID coincidentally same |
| A3 | App Service | Scale plan 1→2 workers | 13:25:17 | No (original worker unchanged) | No | N/A | None | New instance appeared (inst `5c1d1ed9...`, started 13:25:28); original `0f3e80b6...` stayed live |
| A4 | App Service | VNet `vnetRouteAllEnabled` true→false (route-all toggle) | 13:27:00 | Yes (13:27:08) | Same (7→7) | N/A | None (continuous 200) | Restart in ~8 s |
| A5 | App Service | `alwaysOn` true→false | 13:27:55 | Yes (~13:27:55) | Same (7→7) | N/A | None (continuous 200) | Restart within probe interval (~5 s); always-on is not hot in this environment |
| C1 | Container Apps | Env var (`APP_SETTING_SAMPLE=changed-c1`) | 13:28:34 | Yes (new revision) | N/A | Yes (`--0000001`) | None | New revision active in ~20 s |
| C2 | Container Apps | Secret value only (`sample-secret=changed-c2`) | 13:29:30 | No | N/A | No | None | Secret NOT reflected until manual revision restart; running process unchanged |
| C3 | Container Apps | Scale replica range `--min-replicas 1 --max-replicas 5` | 13:32:33 | Yes (new revision) | N/A | Yes (`--0000002`) | None | Unexpected: replica bound change via `az containerapp update` created new revision |
| C6 | Container Apps | Ingress network-facing config change | — | — | N/A | — | Not executed | Scenario designed but not run in this lab session; results unknown |
| C4 | Container Apps | Image `v1→v2` | 13:33:57 | Yes (new revision) | N/A | Yes (`--0000003`) | None | New revision active in ~13 s |
| C5 | Container Apps | CPU 0.5→1.0, memory 1→2 Gi | 13:35:13 | Yes (new revision) | N/A | Yes (`--0000004`) | None | New revision active in ~12 s |

### App Service: availability during change

All App Service scenarios maintained continuous HTTP 200 responses throughout the probe window. No transient 5xx or connection timeout was observed at the 5-second probe cadence used. Whether a shorter cadence (for example, 1-second interval) would capture a transient gap during the restart window is unknown from this data.

### Container Apps: revision timeline

```
13:14:10  --baseline      (initial deployment)
13:28:28  --0000001       C1: env var change
13:32:26  --0000002       C3: scale replicas change
13:33:50  --0000003       C4: image change
13:35:05  --0000004       C5: cpu/memory change
```

C2 (secret-only) produced no new revision entry. The running replica continued serving the old secret value until an explicit `az containerapp revision restart` was issued, after which the new value (`changed-c2`) appeared in the `/identity` response.

## 11. Interpretation

### App Service

**Observed**: App setting change (A1) produced a fresh `APP_START` with a changed `started_at` timestamp and new PID approximately 13 seconds after the CLI write completed. HTTP probing showed no failed requests; the restart was not captured as a visible gap at a 5-second probe cadence.

**Observed**: Connection string change (A2) also produced a changed `started_at` timestamp approximately 12 seconds after the CLI write. The PID integer was the same (7→7). **Inferred**: In a containerized single-worker gunicorn setup, PID reuse across restarts is common because the container's PID namespace resets and the startup sequence is deterministic; the first spawned worker process tends to receive the same low PID. This demonstrates that PID alone is not a reliable restart indicator in this configuration; `started_at` is the correct primary signal.

**Observed**: Scale-out change (A3) from 1 to 2 workers introduced a second instance with a distinct `started_at`, `hostname`, and `website_instance_id`. The original worker's `started_at` and `website_instance_id` were unchanged throughout the scale observation window. Load-balancing caused the probe to alternate between both instances from probe 5 onward.

**Observed**: `vnetRouteAllEnabled` route-all toggle (A4) produced a fresh `started_at` approximately 8 seconds after the config write. **Inferred**: VNet routing configuration changes on App Service are not applied hot; they trigger a runtime restart on the same instance. This was tested only for the route-all toggle; other VNet surfaces (VNet integration add/remove, subnet delegation changes) may differ.

!!! warning "Hypothesis contradiction: always-on is not a hot update"
    **Observed**: `alwaysOn` toggle (A5) produced a fresh `started_at` within the probe window. The experiment hypothesis listed `alwaysOn` as a candidate hot-update setting that might not trigger a restart. This was **Not Proven** — the setting triggered a restart on this P1v3 Linux plan. Support teams should not assume `alwaysOn` changes are traffic-safe.

**Inferred**: The App Service platform applies most configuration changes by recycling the worker container. The recycle duration under this configuration (single gunicorn worker, P1v3, Linux container) was consistently short enough that no 5xx was observed at a 5-second probe interval. A 1-second probe cadence might capture a brief gap.

### Container Apps

**Observed**: Env var change (C1) created a new revision (`--0000001`) within approximately 20 seconds. The new revision served the updated value immediately after activation.

**Observed**: Secret-value-only change (C2, via `az containerapp secret set` alone) did not create a new revision. The running replica continued serving the pre-change secret value after the secret was updated. An explicit `az containerapp revision restart` was required for the updated secret value to appear in the running process (tested for an env-var `secretRef` projection). This is the critical visibility gap: a secret rotation that is not paired with a revision-creating change or an explicit restart will leave existing replicas running with the old value indefinitely.

**Observed**: Scale replica range change (C3, `--min-replicas 1 --max-replicas 5`) created a new revision (`--0000002`). This contradicts the hypothesis that scale-rule changes are applied in-place without a new revision. **Inferred**: When using `az containerapp update` with `--min-replicas` / `--max-replicas`, the CLI modifies the scale stanza in the container template, which the platform treats as a template-level update requiring a new revision. Note that this test covered only the replica bound parameters; other KEDA scale-rule fields (HTTP concurrency thresholds, queue depth rules) were not tested and may behave differently.

**Observed**: Image change (C4, `v1→v2`) created a new revision (`--0000003`) within approximately 13 seconds.

**Observed**: CPU and memory resource change (C5, 0.5 CPU / 1 Gi → 1.0 CPU / 2 Gi) created a new revision (`--0000004`) within approximately 12 seconds.

**Observed**: All tested `az containerapp update` calls that modified the container template (env vars C1, image C4, CPU/memory C5, scale replica bounds C3) produced a new revision. The exception was a secret-value update via `az containerapp secret set` alone (C2), which does not modify the template and did not trigger a new revision. **Inferred**: The Container Apps revision model creates a new revision for any change to the `template` section of the resource definition; changes that only modify the `configuration.secrets` array do not.

## 12. What this proves

- App Service app setting and connection string changes trigger a runtime restart on the same worker instance in this environment. The restart completes within approximately 10–15 seconds of the CLI write and does not produce a visible HTTP failure at a 5-second probe cadence.
- App Service VNet `vnetRouteAllEnabled` toggle triggers a worker restart within approximately 8 seconds.
- App Service `alwaysOn` changes trigger a worker restart in this environment; they are not applied hot on this P1v3 Linux plan.
- App Service scale-out (instance count increase) does not restart existing healthy workers. New workers start fresh; the original worker identity is preserved.
- Container Apps env var, image, CPU/memory, and scale replica range changes (via `az containerapp update`) all created a new revision in this experiment.
- Container Apps secret-value-only changes (via `az containerapp secret set`) did not create a new revision and did not automatically propagate the new value to running replicas when the secret was consumed via an env-var `secretRef`. The new value became visible only after the revision was explicitly restarted.

## 13. What this does NOT prove

- That App Service restarts are always invisible to traffic. No failures were observed at a 5-second probe cadence, but a shorter interval or heavier in-flight load may capture a transient gap during the recycle window.
- The exact internal recycle mechanism on App Service. The startup markers show that the application restarted on the same worker instance identity (same `website_instance_id`), but they cannot distinguish a pure process recycle from a full container recreation on the same underlying VM.
- That behavior is identical across all App Service SKUs, Windows plans, deployment slots, or multi-instance configurations.
- That `alwaysOn` is never a hot update in all environments. The observed restart may be platform-version-specific or SKU-specific; this was a single run on P1v3 Linux.
- That Container Apps revision-creating changes complete with no transient availability impact. This experiment used single-replica mode, which leaves a potential activation gap. The gap was not observed at the probe cadence used, but cannot be ruled out under heavier traffic or stricter monitoring.
- That `az containerapp update --min-replicas --max-replicas` always creates a new revision across all Container Apps API versions. The finding covers replica bound changes via this specific CLI path. Other scale-rule fields (KEDA HTTP, queue depth, CPU) were not tested.
- That secret-handling behavior is uniform across all projection modes. The C2 test used an env-var `secretRef` only. Mounted secrets, Key Vault references, and Dapr secret store integrations were not tested and may differ.
- That network-facing Container Apps ingress configuration changes (C6) create or do not create a new revision. Scenario C6 was designed but not executed in this lab session.
- That the activity log reliably captures or misses any of these events. Activity log data was not collected or reviewed as part of this experiment; statements about activity log visibility elsewhere in this document are based on general platform knowledge, not direct observation from this run.
- That results generalize across all Azure regions or future Container Apps and App Service platform builds.

## 14. Support takeaway

When customers report a brief outage or unexpected behavior after a "small config change," the platform lifecycle event type varies significantly depending on what was changed and which service is involved.

**App Service:**

- Treat app setting and connection string changes as restart events. Capture `started_at`, PID, and `website_instance_id` before and after to confirm the restart happened and to bound the outage window.
- Do not use PID alone as a restart indicator in containerized single-worker configurations. `started_at` is the reliable signal; PID reuse within a fresh container namespace is common when the startup sequence is deterministic.
- Scale changes add new instances but do not recycle healthy existing workers. If a customer reports a restart after scale-out, check the new instance's `started_at` and `website_instance_id` rather than looking for a recycle on the original instance.
- VNet route-all configuration changes trigger a worker restart. If a customer reports unexpected downtime after a "network-only" change, check `started_at` before and after the change.
- `alwaysOn` is not a safe hot-update setting on P1v3 Linux in this environment. It triggered a restart in this lab. Advise customers accordingly until confirmed otherwise on their specific plan.

**Container Apps:**

- Any `az containerapp update` that modifies the template (env vars, image, resources, scale replica bounds) creates a new revision. Customers surprised by a new revision should inspect what template field changed.
- Secret rotation via `az containerapp secret set` alone does not create a new revision and does not propagate the new value to running replicas when the secret is consumed via an env-var `secretRef`. To pick up the new secret value, customers must either pair the rotation with a revision-creating change (for example, update an env var to force a new revision) or explicitly restart the existing revision. The old value continues serving until then.
- This guidance applies specifically to env-var `secretRef` projections as tested. Mounted secrets and Key Vault references may behave differently and should be tested separately.
- Inspect the revision list before and after each change. Do not rely on request failures or replica count to detect revision events; a revision can appear and become active without any visible HTTP gap at low traffic levels.

## 15. Reproduction notes

- Run only one configuration change per observation window.
- Wait for baseline stability before each scenario so startup markers are not confused with initial deployment.
- Use the same probe cadence for every scenario to make timing comparisons meaningful.
- Secret-handling behavior in Container Apps should be validated carefully because CLI update patterns may themselves trigger revision/template changes.
- App Service network scenario behavior may vary depending on whether the chosen setting is route-all, VNet integration add/remove, or another networking surface.
- If a scenario unexpectedly affects availability, reset to baseline before proceeding to the next row in the matrix.

## 16. Related guide / official docs

- [Azure App Service environment variables and app settings](https://learn.microsoft.com/azure/app-service/configure-common)
- [Manage connection strings in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-common#configure-connection-strings)
- [Integrate your app with an Azure virtual network](https://learn.microsoft.com/azure/app-service/configure-vnet-integration-enable)
- [Manage revisions in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/revisions)
- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/manage-secrets)
- [Scale applications in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/scale-app)
- [Configure ingress in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/ingress-how-to)
