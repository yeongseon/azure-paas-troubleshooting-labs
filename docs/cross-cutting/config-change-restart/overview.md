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

# Configuration Change Restart Matrix

!!! info "Status: Draft - Awaiting Execution"
    Experiment design completed, but no Azure resources have been created and no configuration changes have been executed yet. This draft is prepared for a future controlled lab run covering both Azure App Service and Azure Container Apps.

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
| Container image | Shared test image used by both platforms |
| Restart markers | Startup timestamp, PID, hostname / replica name, revision name |
| Date tested | Not yet executed |

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

Not yet executed.

Populate this section after the lab run with:

- exact before/after identity payloads for each scenario
- App Service log excerpts showing `APP_START` and request continuity
- Container Apps revision timeline and activation state transitions
- activity-log timestamps for each configuration update
- any transient `5xx` or timeout window observed during the change
- a completed version of the per-scenario capture table

## 11. Interpretation

Pending execution.

Use evidence tags when results are available, for example:

- **Observed**: App Service app-setting changes emitted a fresh `APP_START` with a new PID.
- **Measured**: Container Apps image changes created a new revision within `N` seconds of the update command.
- **Correlated**: A short burst of `503` aligned with revision activation or worker recycle timing.
- **Inferred**: A network config update forced worker replacement even when the activity log did not explicitly say “restart.”
- **Not Proven**: A hot-update candidate did not clearly avoid recycle across all runs.
- **Unknown**: Ingress configuration behavior in Container Apps may differ by API version or environment state.

## 12. What this proves

After execution, this experiment should be able to prove only the following kinds of conclusions:

- which tested configuration changes produced a new startup identity on App Service in this environment
- which tested Container Apps changes produced a new revision versus an in-place update
- how visible those lifecycle events were in application logs, CLI state, and platform logs
- whether brief availability impact accompanied each lifecycle event under light continuous traffic

## 13. What this does NOT prove

Even after successful execution, this experiment will not by itself prove:

- behavior for every App Service SKU, Windows plan, or deployment model
- behavior for every Container Apps environment type, workload profile, or API version
- that an unobserved restart never happened outside the observation window
- that all “secret changes” behave identically across direct secret references, mounted secrets, and Dapr/component integrations
- that results from `koreacentral` generalize to all regions or future platform builds

## 14. Support takeaway

When customers ask whether a config update is “safe” or “hot,” support should verify the exact configuration surface instead of assuming all changes behave the same.

Practical guidance:

- capture an application-level startup marker before making the change
- for App Service, compare `started_at`, PID, and instance identity before and after the update
- for Container Apps, inspect the revision list first; do not rely only on request failures or replica count
- separate **scale movement** from **restart evidence**
- if the customer reports only a brief outage, continuous probing plus startup markers is usually stronger evidence than portal screenshots alone

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
