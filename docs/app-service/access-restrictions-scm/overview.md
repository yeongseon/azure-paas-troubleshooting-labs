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

!!! success "Status: Published"
    Experiment executed on 2026-05-01. Korea Central, Linux P1v3, Python 3.11. Scenarios S1, S2, S3, S5, S6 completed on real Azure infrastructure. S4 (private endpoint + access restrictions combined) not executed — VNet-internal client not available in this lab environment.

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

!!! info "Environment: Korea Central, Linux P1v3, Python 3.11, 2026-05-01"

### Baseline (no restrictions, no private endpoint)

| Endpoint | HTTP status | Notes |
|----------|-------------|-------|
| Main `/` | 200 | Public access, public IP |
| Main `/healthz` | 200 | |
| SCM `/api/settings` | 200 | Basic auth enabled |
| SCM `/api/deployments` | 200 | |
| DNS: `app.azurewebsites.net` | `20.41.66.225` | Public IP |
| DNS: `app.scm.azurewebsites.net` | `20.41.66.225` | Same public IP |
| SCM `scmIpSecurityRestrictionsUseMain` | `false` | Default — SCM rules independent |

### Scenario S1: Main restricted (bogus IP only), SCM unrestricted (`scmUsesMain=false`)

| Endpoint | HTTP status | Notes |
|----------|-------------|-------|
| Main `/` | **403** | Our workstation IP denied by main rules |
| Main `/healthz` | **403** | Same — all main paths blocked |
| SCM `/api/settings` | **200** | SCM rules independent, no SCM restriction |
| SCM `/api/deployments` | **200** | |

**Key observation**: Main site blocked, SCM/Kudu fully reachable — independent control planes confirmed **[Observed]**.

### Scenario S2: Main allows workstation IP; SCM allows only bogus IP (`scmUsesMain=false`)

| Endpoint | HTTP status | Notes |
|----------|-------------|-------|
| Main `/` | **200** | Workstation IP in main allow list |
| SCM `/api/settings` | **403** | Workstation IP not in SCM allow list |
| SCM `/api/deployments` | **403** | |

**Key observation**: Main and SCM can be independently allowed/denied by different source IP rules — they are truly separate rule sets **[Observed]**.

### Scenario S3: Private endpoint added, no access restrictions

| Endpoint | HTTP status | DNS resolution |
|----------|-------------|----------------|
| Main `/` | **403** | `20.41.66.225` (public IP — unchanged) |
| Main `/healthz` | **403** | |
| SCM `/api/settings` | **403** | |
| SCM `/api/deployments` | **403** | |

**Key observation**: Private endpoint addition alone — without any access restriction rules — caused `403` on **both** main site and SCM from the public internet **[Observed]**. DNS still resolved to the public IP; the block is enforced at the App Service layer, not via DNS. SCM/Kudu followed the same behavior as the main site when the private endpoint was the only change **[Observed]**.

### Scenario S5: Main restricted (all IPs denied), health check configured on `/healthz`

| Time | Instance state | Main `/healthz` from workstation |
|------|---------------|----------------------------------|
| T=0  | READY | 403 |
| T=3min | **READY** | 403 |
| T=5min | **READY** | 403 |

**Key observation**: Instance remained `READY` throughout — health check probe continued to succeed even though all external IPs (including our workstation) were blocked **[Observed]**. The platform health check probe bypasses access restrictions; it does not originate from a routable external IP that would be subject to the IP allow/deny rules **[Strongly Suggested]**.

### Scenario S6: Main site open, SCM restricted (bogus IP only)

| Operation | Result | Error |
|-----------|--------|-------|
| Main `/` | **200** | — |
| SCM `/api/settings` | **403** | Access restriction |
| SCM `/api/deployments` | **403** | Access restriction |
| `curl` zipdeploy via SCM API | **403** | Access restriction |
| `az webapp deploy` (zip) | **Failed** | `Status Code: 403` — Kudu warmup and deploy both blocked |

**Key observation**: SCM restriction blocked `zipdeploy`, Kudu API access, and `az webapp deploy` while the main site remained fully accessible **[Observed]**. The deployment CLI route goes through `*.scm.azurewebsites.net` — SCM reachability is a prerequisite for all zip-based deployments **[Observed]**.

## 11. Interpretation

**H1 — Main and SCM restrictions are independently configurable: CONFIRMED [Observed]**
S1 and S2 both demonstrated that `ipSecurityRestrictions` (main) and `scmIpSecurityRestrictions` (SCM) are evaluated independently when `scmIpSecurityRestrictionsUseMain=false`. A source IP blocked on main can reach SCM, and vice versa **[Observed]**.

**H2 — Private endpoint causes public 403 on both main and SCM: CONFIRMED [Observed]**
S3 showed that adding a private endpoint alone — without any explicit access restriction rules — produced `403` on both `*.azurewebsites.net` and `*.scm.azurewebsites.net` from the public internet **[Observed]**. DNS continued to resolve to the public IP; the block is not DNS-based **[Observed]**. SCM did not maintain a separate public path after the private endpoint was added in this test **[Observed]**. The underlying mechanism (whether the PE triggers an internal public-network-access block or routes differently) was not directly verified **[Unknown]**.

**H3 — Platform-originated health/warmup traffic still reached the app despite external 403: CORROBORATED [Strongly Suggested]**
S5 showed that instance state remained `READY` for at least 5 minutes after all external IPs were denied on the main site **[Observed]**. The warmup probe succeeded at the platform layer even though the same `/healthz` path returned `403` from the external workstation **[Observed]**. This is consistent with platform-originated probe traffic not traversing the IP-based restriction layer — but the probe source IP and internal routing path were not directly captured **[Strongly Suggested]**.

**H4 — SCM restrictions block zipdeploy and deployment CLI: CONFIRMED [Observed]**
S6 confirmed that SCM restriction `403` propagates to `curl /api/zipdeploy` and `az webapp deploy --type zip` **[Observed]**. The main site was unaffected — `200` throughout — while all SCM-routed operations failed **[Observed]**.

### Key discovery: Private endpoint caused public 403 on both main and SCM — VNet-internal access not verified

Adding a private endpoint (no access restriction rules set) produced `403` on both main and SCM endpoints from the public internet. DNS still resolved to the public IP — the block is not DNS-based **[Observed]**. Customers who add a private endpoint expecting only the main site to be restricted will find SCM/Kudu also becomes inaccessible from public clients **[Observed]**. This experiment did not verify access from inside the VNet (S4 not executed); whether VNet-internal clients can reach both main and SCM via the private endpoint is not confirmed **[Unknown]**.

### Key discovery: Platform warmup/health traffic reached the app despite external 403 — probe mechanism not directly observed

Instance state remained `READY` while all external IPs were denied. Platform-originated warmup traffic succeeded even though the same `/healthz` endpoint returned `403` from outside **[Observed]**. This is consistent with the probe not traversing the IP-restriction layer, but the probe source IP was not captured **[Strongly Suggested]**.

### Key discovery: SCM rules are independent by default (`scmUsesMain=false`)

When `scmIpSecurityRestrictionsUseMain=false` (default), main and SCM rules are evaluated completely independently — confirmed in S1 and S2. The behavior of `scmUsesMain=true` was not tested in this experiment; its effect is noted as a known risk but is not characterized here **[Unknown]**.

## 12. What this proves

!!! success "Evidence: S1–S3, S5–S6. Korea Central, Linux P1v3, Python 3.11, 2026-05-01"

1. **Main and SCM access restrictions are independently enforced when `scmUsesMain=false`** **[Observed]** — different source IPs can be allowed/denied on each independently; confirmed in S1 and S2
2. **A private endpoint alone caused `403` on both main and SCM from the public internet in this test** **[Observed]** — no access restriction rule was needed; DNS still resolved to the public IP; VNet-internal access was not verified (S4 not executed)
3. **DNS is not changed by private endpoint** **[Observed]** — `*.azurewebsites.net` and `*.scm.azurewebsites.net` continued to resolve to the public IP after PE addition
4. **Platform warmup/probe traffic reached the app while all external IPs were denied** **[Observed]** — instance remained healthy for ≥5 minutes; the probe source did not traverse the IP restriction layer **[Strongly Suggested]**
5. **SCM restriction blocks Kudu-based deployment paths** **[Observed]** — `curl /api/zipdeploy` and `az webapp deploy --type zip` both returned `403`; main site `200` was unaffected
6. **`az webapp deploy --type zip` uses the SCM endpoint** **[Observed]** — it is not a privileged ARM-level channel; SCM restriction applies equally to the CLI and direct curl

## 13. What this does NOT prove

- **Behavior with `scmUsesMain=true`**: This toggle was not directly tested; whether it produces the expected main-rule inheritance on SCM under all conditions (including private endpoint) is not characterized here **[Unknown]**
- **VNet-internal access after private endpoint**: S4 was not executed — whether both main and SCM are accessible from inside the VNet via the private endpoint is not confirmed **[Unknown]**
- **Behavior for Windows plans or Windows Containers**: Results are for Linux P1v3 only
- **Behavior for ASE or ILB ASE**: Different network model; access restriction semantics may differ
- **Health check probe source IP**: The probe source was not captured; the bypass is inferred from instance state remaining healthy, not from direct traffic observation **[Strongly Suggested, not directly observed]**
- **Deployment methods beyond Kudu/zipdeploy**: GitHub Actions (internal task), MSDeploy, FTP, and local git were not tested — only `az webapp deploy --type zip` and direct `curl /api/zipdeploy`
- **Whether PE mechanism is public-network-access toggle or routing change**: The exact platform mechanism that produces the 403 after PE addition was not verified

## 14. Support takeaway

!!! abstract "For support engineers"

    **When a customer reports unexpected 403 or deployment failures after a network configuration change:**

    1. **Identify which endpoint is failing first**: Main site (`*.azurewebsites.net`) or SCM/Kudu (`*.scm.azurewebsites.net`)? These are independently controlled. A `403` on deployment does not mean the app itself is blocked, and vice versa.

    2. **Check `scmIpSecurityRestrictionsUseMain`**: If `true`, SCM inherits main-site rules — restricting the main site will also restrict deployment and Kudu access. This is often set intentionally but surprises customers when deployment pipelines break after a main-site lockdown.

    3. **Private endpoint caused both main and SCM to return 403 from the public internet in this test**: Customers who add a private endpoint often expect only the main site to become private. In this experiment, `*.scm.azurewebsites.net` also returned `403` from public clients after PE addition — even without any explicit access restriction rules. If Kudu or deployment access is needed from public CI/CD after PE is added, a VNet-connected runner, jump host, or self-hosted agent in the VNet is likely required. Note: VNet-internal access was not verified in this experiment.

    4. **Platform warmup/health traffic appears to bypass IP-based access restrictions**: Instance state remained `READY` while all external IPs were denied. If instances are going unhealthy after a network hardening change, the restriction rules are unlikely to be the cause — look at the application health endpoint itself (startup failure, dependency, misconfigured path) rather than the IP rules. Note: the probe source was not directly captured; this is inferred from instance state.

    5. **Deployment failures after SCM restriction show as `403`, not `401`**: `401` means credentials were rejected; `403` means the request was rejected by the access restriction layer before credentials were evaluated. These must be distinguished — the fix for `403` is a rule change, not a credential rotation.

    6. **`az webapp deploy --type zip` goes through SCM — it is not a privileged channel**: This CLI command uses `*.scm.azurewebsites.net` and is subject to the same SCM access restrictions as a direct `curl /api/zipdeploy`. If SCM is restricted, all Kudu/zip-based deployment methods will fail. Other deployment methods (GitHub Actions internal task, MSDeploy, FTP) were not tested in this experiment.

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
