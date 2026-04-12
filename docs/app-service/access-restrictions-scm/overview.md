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

# Access Restrictions: Main Site vs SCM / Kudu Reachability

!!! info "Status: Draft - Awaiting Execution"
    This experiment design is complete and ready for lab execution. No Azure resources were created and no live measurements are recorded on this page yet.

## 1. Question

With Azure App Service access restrictions and/or a private endpoint enabled, what remains reachable under different configurations: the main site, the SCM/Kudu endpoint, zipdeploy, health check probes, and common diagnostics surfaces?

## 2. Why this matters

Customers often combine App Service access restrictions, private endpoints, deployment automation, and health check. Failures then look inconsistent:

- the app URL is blocked but Kudu still works
- the app URL works privately but zipdeploy suddenly fails
- health check starts evicting instances after a network hardening change
- diagnostics in Kudu or log streaming become inaccessible while the site itself is reachable

Support engineers need a precise model of which control applies to which endpoint. Without that model, cases get misdiagnosed as application bugs, broken deployments, or platform outages when the actual cause is rule scope.

## 3. Customer symptom

- "We locked down the app, but `*.scm.azurewebsites.net` is still open."
- "Zip deploy started returning 403 after we changed access restrictions."
- "The app works through private endpoint, but Kudu access is inconsistent."
- "Health check started marking instances unhealthy after we enabled restrictions."
- "Portal diagnostics or Kudu console stopped working even though the app is still serving traffic."

## 4. Hypothesis

1. Access restrictions can be configured independently for the main site and the SCM site.
2. Private endpoint changes reachability for the main site hostname, but SCM behavior may differ because it uses a separate endpoint and access path.
3. Health check probes originate from a platform-controlled source that must still be permitted when access restrictions are enabled.
4. Zipdeploy and related deployment APIs use the SCM endpoint and therefore follow SCM reachability, not just main-site reachability.
5. The SCM option **Use main site rules** behaves differently from separately managed SCM rules and may expose edge cases when private endpoint and source-IP rules are combined.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | koreacentral |
| Runtime | Python 3.11 |
| OS | Linux |
| Network features | VNet integration, private endpoint |
| Access control features | Main-site restrictions, SCM restrictions, SCM use-main-site-rules toggle |
| Date tested | Awaiting execution |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Same App Service plan, region, runtime, and application package across all scenarios
- Same VNet, subnets, and private DNS zone
- Same test workstation / source IP for public-path tests
- Same health check path (`/healthz`)
- Same deployment artifact and deployment method (`zipdeploy`, optional local git)
- Same authentication method for SCM API calls (publishing credentials)

**Observed:**

- HTTP status and response body for main site endpoints
- HTTP status and response body for SCM / Kudu endpoints
- Zipdeploy success or failure and failure mode (`401`, `403`, timeout, DNS failure)
- Health check success/failure and any instance eviction or unhealthy behavior
- Access restriction hit logs and effective rule matches
- DNS resolution and connectivity behavior for public hostname vs private endpoint path
- Diagnostic surface availability: Kudu API, environment endpoint, deployment history, log stream

## 7. Instrumentation

- **Client probes**: `curl -i`, `nslookup`, `dig`, `openssl s_client` as needed
- **Azure CLI**: app configuration, access restriction changes, health check configuration, private endpoint and DNS inspection
- **SCM API**: `/api/settings`, `/api/environment`, `/api/deployments`, `/api/zipdeploy`
- **Application logging**: stdout plus request logging for `/`, `/healthz`, `/diag/request-info`
- **Access restriction evidence**: App Service access restriction logs and Activity Log for rule changes
- **Instance state**: `az webapp list-instances`
- **Deployment evidence**: zipdeploy response, deployment log, Kudu deployment record

## 8. Procedure

### 8.1 Infrastructure setup

Create one dedicated lab resource group, one Linux P1v3 plan, a VNet with separate subnets for integration and private endpoint, one App Service app, and the private DNS plumbing required for the private endpoint scenario.

```bash
export RG="rg-access-restrictions-scm-lab"
export LOCATION="koreacentral"
export PLAN_NAME="plan-ar-scm-p1v3"
export APP_NAME="app-ar-scm-$RANDOM"
export VNET_NAME="vnet-ar-scm"
export INTEGRATION_SUBNET="snet-appsvc-integration"
export PE_SUBNET="snet-appsvc-private-endpoint"
export PRIVATE_DNS_ZONE="privatelink.azurewebsites.net"
export APP_HOST="${APP_NAME}.azurewebsites.net"
export SCM_HOST="${APP_NAME}.scm.azurewebsites.net"

az group create --name "$RG" --location "$LOCATION"

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.82.0.0/16" \
  --subnet-name "$INTEGRATION_SUBNET" \
  --subnet-prefixes "10.82.1.0/24"

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$PE_SUBNET" \
  --address-prefixes "10.82.2.0/24"

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --sku P1v3 \
  --is-linux

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --name "$APP_NAME" \
  --runtime "PYTHON:3.11"

az webapp vnet-integration add \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --vnet "$VNET_NAME" \
  --subnet "$INTEGRATION_SUBNET"

APP_ID=$(az webapp show --resource-group "$RG" --name "$APP_NAME" --query id --output tsv)

az network private-endpoint create \
  --resource-group "$RG" \
  --name "pe-${APP_NAME}" \
  --location "$LOCATION" \
  --vnet-name "$VNET_NAME" \
  --subnet "$PE_SUBNET" \
  --private-connection-resource-id "$APP_ID" \
  --group-id sites \
  --connection-name "conn-${APP_NAME}"

az network private-dns zone create \
  --resource-group "$RG" \
  --name "$PRIVATE_DNS_ZONE"

az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --name "link-${VNET_NAME}" \
  --virtual-network "$VNET_NAME" \
  --registration-enabled false

PE_NIC_ID=$(az network private-endpoint show \
  --resource-group "$RG" \
  --name "pe-${APP_NAME}" \
  --query "networkInterfaces[0].id" \
  --output tsv)

PE_IP=$(az network nic show \
  --ids "$PE_NIC_ID" \
  --query "ipConfigurations[0].privateIPAddress" \
  --output tsv)

az network private-dns record-set a add-record \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --record-set-name "$APP_NAME" \
  --ipv4-address "$PE_IP"
```

### 8.2 Test application

Deploy a minimal app that exposes:

- `/` — simple success response with instance metadata
- `/healthz` — health check endpoint returning `200`
- `/diag/request-info` — headers, host, instance, and timestamp for reachability verification

Create the files and package them at the zip root:

```bash
mkdir -p app-ar-scm

cat > app-ar-scm/app.py <<'PY'
import os
import socket
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)


def instance_id():
    return os.environ.get("WEBSITE_INSTANCE_ID", socket.gethostname())


@app.get("/")
def index():
    return jsonify(
        {
            "status": "ok",
            "site": os.environ.get("WEBSITE_SITE_NAME"),
            "instance_id": instance_id(),
            "hostname": socket.gethostname(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "status": "healthy",
            "instance_id": instance_id(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    ), 200


@app.get("/diag/request-info")
def request_info():
    return jsonify(
        {
            "method": request.method,
            "path": request.path,
            "host": request.host,
            "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
            "x_original_host": request.headers.get("X-Original-Host"),
            "user_agent": request.headers.get("User-Agent"),
            "instance_id": instance_id(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
PY

cat > app-ar-scm/requirements.txt <<'TXT'
flask==3.1.1
gunicorn==23.0.0
TXT

(cd app-ar-scm && zip -r ../app-ar-scm.zip .)

az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 180 app:app"

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true WEBSITE_HEALTHCHECK_MAXPINGFAILURES=2

az webapp deploy \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src-path "app-ar-scm.zip" \
  --type zip

az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --generic-configurations '{"healthCheckPath":"/healthz"}'
```

### 8.3 Baseline capture

Record baseline behavior before any restrictions are applied.

```bash
export APP_URL="https://${APP_HOST}"
export SCM_URL="https://${SCM_HOST}"

az webapp deployment list-publishing-profiles \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --xml > publishingProfiles.xml
```

Extract publishing credentials from `publishingProfiles.xml`, then run:

```bash
export PUBLISH_USER="<publishing-user>"
export PUBLISH_PASS="<publishing-password>"

curl -i "$APP_URL/"
curl -i "$APP_URL/diag/request-info"

curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/settings"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/environment"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/deployments"
```

### 8.4 Scenario matrix

Execute all scenarios below. Revert to the baseline configuration between scenarios unless the matrix explicitly says to layer controls.

| Scenario | Main site access restrictions | SCM access restrictions | SCM uses main-site rules | Private endpoint | Primary question |
|----------|-------------------------------|-------------------------|--------------------------|------------------|------------------|
| S1 | Restricted | Unrestricted | Off | No | Can app be blocked while SCM remains reachable? |
| S2 | Restricted (rule set A) | Restricted (rule set B) | Off | No | Can main and SCM be independently allowed/denied by source IP? |
| S3 | None | None | Off | Yes | What remains reachable when only private endpoint is added? |
| S4 | Restricted | Restricted or inherit | On/Off as variant | Yes | How do private endpoint and access restrictions interact? |
| S5 | Restricted to selected sources | SCM per scenario | On/Off as variant | Optional | What source must health check use, and what breaks when it is blocked? |
| S6 | Any | Restricted | On/Off as variant | Optional | Do zipdeploy and SCM-based deployment flows fail with SCM restrictions? |

### 8.5 Common helper commands

Identify the current public test source IP and define allow/deny values:

```bash
export TEST_SOURCE_IP="<your-public-ip>/32"
export ALT_TEST_SOURCE_IP="203.0.113.10/32"
```

Reset access restrictions before each scenario:

```bash
az webapp config access-restriction remove --resource-group "$RG" --name "$APP_NAME" --rule-name "allow-test-ip" --action Allow || true
az webapp config access-restriction remove --resource-group "$RG" --name "$APP_NAME" --rule-name "allow-alt-ip" --action Allow || true
az webapp config access-restriction remove --resource-group "$RG" --name "$APP_NAME" --rule-name "deny-all-main" --action Deny || true

az webapp config access-restriction remove --resource-group "$RG" --name "$APP_NAME" --rule-name "allow-test-ip-scm" --action Allow --scm-site true || true
az webapp config access-restriction remove --resource-group "$RG" --name "$APP_NAME" --rule-name "allow-alt-ip-scm" --action Allow --scm-site true || true
az webapp config access-restriction remove --resource-group "$RG" --name "$APP_NAME" --rule-name "deny-all-scm" --action Deny --scm-site true || true
```

Inspect effective configuration:

```bash
az webapp config access-restriction show \
  --resource-group "$RG" \
  --name "$APP_NAME"
```

### 8.6 Scenario S1 — Main site restricted, SCM unrestricted

```bash
az webapp config access-restriction add \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --rule-name "allow-alt-ip" \
  --action Allow \
  --priority 100 \
  --ip-address "$ALT_TEST_SOURCE_IP"

az webapp config access-restriction set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --use-same-restrictions-for-scm-site false
```

Test from the normal workstation IP:

```bash
curl -i "$APP_URL/"
curl -i "$APP_URL/diag/request-info"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/settings"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/environment"
```

Capture whether the main site returns `403` while SCM remains reachable.

### 8.7 Scenario S2 — Both restricted with different IP rules

```bash
az webapp config access-restriction add \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --rule-name "allow-test-ip" \
  --action Allow \
  --priority 100 \
  --ip-address "$TEST_SOURCE_IP"

az webapp config access-restriction add \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --rule-name "allow-alt-ip-scm" \
  --action Allow \
  --priority 100 \
  --ip-address "$ALT_TEST_SOURCE_IP" \
  --scm-site true

az webapp config access-restriction set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --use-same-restrictions-for-scm-site false
```

From the normal workstation IP, test:

```bash
curl -i "$APP_URL/"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/settings"
```

Expected comparison point: main site allowed, SCM denied.

### 8.8 Scenario S3 — Private endpoint only, no access restrictions

Remove public access restrictions, keep private endpoint enabled, and test from both outside and inside the VNet path if available.

Public-path checks:

```bash
nslookup "$APP_HOST"
nslookup "$SCM_HOST"

curl -i "$APP_URL/"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/settings"
```

VNet-path checks from a VM or host linked to the private DNS zone:

```bash
nslookup "$APP_HOST"
curl -i "$APP_URL/"
curl -i "$APP_URL/healthz"
```

Record whether the main site resolves privately while SCM still resolves publicly or follows a different pattern.

### 8.9 Scenario S4 — Private endpoint plus access restrictions

Use a variant matrix under private endpoint:

| Variant | Main rule | SCM rule mode | Test goal |
|---------|-----------|---------------|-----------|
| S4-A | Allow only VNet/private path sources | Separate SCM rules | Determine whether private main-site path works while SCM remains public/restricted separately |
| S4-B | Allow only VNet/private path sources | Use main-site rules | Determine whether inherited SCM rules block deployment/diagnostics unexpectedly |
| S4-C | Allow test IP + private path | Separate SCM deny | Compare mixed public/private access behavior |

Representative commands:

```bash
az webapp config access-restriction set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --use-same-restrictions-for-scm-site true

az webapp config access-restriction show \
  --resource-group "$RG" \
  --name "$APP_NAME"

curl -i "$APP_URL/"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/settings"
```

### 8.10 Scenario S5 — Health check with restrictions

Objective: identify whether health check continues to succeed and, if not, whether instance health degrades because the probe source is no longer allowed.

1. Enable request logging in the test app for `/healthz`.
2. Apply restrictive main-site rules.
3. Observe whether `/healthz` requests still arrive.
4. Correlate request logs with instance health and access restriction hits.

Commands:

```bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --generic-configurations '{"healthCheckPath":"/healthz"}'

az webapp list-instances \
  --resource-group "$RG" \
  --name "$APP_NAME"

curl -i "$APP_URL/healthz"
```

Evidence to collect:

- request log entries for `/healthz`
- timestamps of failed or missing health checks
- access restriction logs showing blocked probe source, if any
- instance state changes over time

### 8.11 Scenario S6 — Deployment and diagnostics with SCM restrictions

Prepare a new zip package and test `zipdeploy` directly against SCM.

```bash
zip -r app-ar-scm-v2.zip app-ar-scm

curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" \
  -X POST \
  -H "Content-Type: application/zip" \
  --data-binary @app-ar-scm-v2.zip \
  "$SCM_URL/api/zipdeploy"

curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/deployments"
curl -i -u "$PUBLISH_USER:$PUBLISH_PASS" "$SCM_URL/api/environment"
```

Optional git deployment check:

```bash
az webapp deployment source config-local-git \
  --resource-group "$RG" \
  --name "$APP_NAME"
```

Record whether deployment and diagnostics fail whenever SCM is blocked even if the main site remains reachable.

### 8.12 Data collection sheet

For every scenario and variant, capture the following matrix.

| Scenario | Source location | Main site `/` | Main site `/healthz` | SCM `/api/settings` | SCM `/api/environment` | zipdeploy | Health check stable? | Notes |
|----------|-----------------|---------------|-----------------------|---------------------|------------------------|-----------|----------------------|-------|
| S1 | Public workstation | | | | | n/a | | |
| S2 | Public workstation | | | | | n/a | | |
| S3 | Public workstation | | | | | | | |
| S3 | VNet-connected host | | | | | | | |
| S4-A | Public workstation | | | | | | | |
| S4-A | VNet-connected host | | | | | | | |
| S4-B | Public workstation | | | | | | | |
| S4-B | VNet-connected host | | | | | | | |
| S5 | Public workstation | | | | | n/a | | |
| S6 | Public workstation | | n/a | | | | n/a | |

Record exact HTTP status, selected response headers, and whether the failure was `403`, `401`, DNS resolution failure, TCP timeout, or TLS/connectivity failure.

### 8.13 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- **Main site restrictions** should affect `https://<app>.azurewebsites.net` requests independently of SCM when SCM is configured separately.
- **SCM restrictions** should directly affect Kudu APIs, deployment APIs, and likely any tooling that depends on `https://<app>.scm.azurewebsites.net`.
- **Private endpoint** should change resolution/reachability for the main site from private-network paths, while SCM may show different DNS and reachability behavior that must be captured rather than assumed.
- **Health check** should continue only if the platform probe source is permitted by the effective rules that govern the main site path used for health probing.
- **Use main site rules for SCM** should make SCM access follow the main site rules, potentially breaking deployment and diagnostics in configurations where the app path is intentionally more restrictive than the operations path.

## 10. Results

Awaiting execution.

Populate this section with:

1. Completed scenario matrix from section 8.12
2. Sample request/response transcripts for each distinct outcome (`200`, `401`, `403`, timeout, DNS failure)
3. DNS resolution results for app and SCM hostnames from public and VNet-connected clients
4. Access restriction rule dumps per scenario
5. Health check log evidence and any instance-state changes
6. zipdeploy and deployment-history outputs under each SCM restriction mode

## 11. Interpretation

Awaiting execution. Use evidence tags when filling this section.

Suggested interpretation structure:

- **Observed**: which endpoint classes were reachable or blocked under each rule combination
- **Measured**: counts of successful vs failed probes and deployments per scenario
- **Correlated**: health degradation or deployment failure coinciding with a specific rule set
- **Inferred**: which control plane applies to each endpoint type
- **Not Proven / Unknown**: any unresolved SCM behavior under private endpoint or inherited-rule edge cases

## 12. What this proves

Awaiting execution. After running the experiment, this section should state only the supported conclusions, for example:

- whether main-site and SCM restrictions were truly independent in practice
- whether zipdeploy followed SCM reachability exactly
- whether health check failed when the effective probe source was blocked
- whether private endpoint changed only the main-site path or also affected SCM in the tested configuration

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- behavior across all App Service SKUs, regions, or Windows plans
- behavior for ASE, ILB ASE, or App Service Environment-specific networking
- behavior for every diagnostics surface in the Azure portal
- all possible health check probe source identities outside the tested region and platform generation
- behavior for deployment methods not tested here (for example, GitHub Actions task internals, MSDeploy, or custom CI runners)

## 14. Support takeaway

Planned support guidance after execution:

1. Check whether the failing operation targets the **main site** or the **SCM site**.
2. If deployment, Kudu, or log-stream access fails, inspect **SCM restrictions first**, not only main-site restrictions.
3. If private endpoint is involved, verify DNS resolution and test from both public and VNet-connected paths.
4. If health check starts failing after a network change, validate whether the effective rules still allow the probe source.
5. Treat **Use main site rules for SCM** as a deliberate design choice, not a harmless simplification.

## 15. Reproduction notes

- Use a stable public source IP for the workstation running `curl` and `zipdeploy`; otherwise results become ambiguous.
- Wait for configuration propagation after each access restriction change before testing.
- Re-test from both a public client and a VNet-connected client when private endpoint is enabled.
- Save raw HTTP transcripts; `403` from access restriction, `401` from missing credentials, and network timeouts can otherwise be confused.
- When testing health check, allow enough time for probe cycles and any unhealthy-instance transitions to appear.
- If SCM DNS or reachability differs from the main site under private endpoint, capture it carefully rather than normalizing it as expected behavior.

## 16. Related guide / official docs

- Microsoft Learn: App Service access restrictions
- Microsoft Learn: App Service private endpoints
- Microsoft Learn: App Service health check
- Microsoft Learn: Kudu and deployment credentials for App Service
- Microsoft Learn: Zip deployment for Azure App Service
- Related repository experiments:
  - `docs/app-service/health-check-eviction/overview.md`
  - `docs/app-service/custom-dns-resolution/overview.md`
  - `docs/app-service/zip-vs-container/overview.md`
