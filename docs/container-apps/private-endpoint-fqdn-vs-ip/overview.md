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

# Private Endpoint: FQDN vs IP Access

!!! info "Status: Planned"

## 1. Question

What are the behavioral differences when accessing a Container App via private endpoint FQDN versus direct IP address, and what breaks when bypassing DNS resolution?

## 2. Why this matters

Customers using private endpoints sometimes attempt to access Container Apps by IP address directly, bypassing the private DNS zone. This can fail due to TLS certificate validation (the certificate is issued for the FQDN, not the IP), SNI routing requirements, or ingress layer behavior that depends on the host header matching a configured domain. Support engineers need to explain why FQDN access works but IP access fails.

## 3. Customer symptom

"App works via FQDN but fails via IP address" or "Private endpoint connection intermittently fails" or "TLS handshake fails when connecting by IP."

## 4. Hypothesis

For a Container App behind a private endpoint, FQDN-based access through private DNS will consistently succeed, while direct IP access will fail or produce different TLS/routing outcomes unless both host header and SNI are explicitly aligned to the app domain; even then, certificate validation remains domain-bound rather than IP-bound.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption environment with VNet |
| Region | Korea Central |
| Runtime | Containerized HTTP app |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Private endpoint configuration
- Private DNS zone configuration
- Access method (FQDN, IP, IP + host header, IP + SNI)
- TLS verification mode (enabled, disabled)

**Observed:**

- TLS handshake success/failure and certificate presented
- HTTP response status and error message
- Ingress routing behavior
- DNS resolution path

## 7. Instrumentation

- `curl` (with/without host header and certificate validation)
- `openssl s_client` (explicit SNI and certificate inspection)
- DNS tools (`nslookup`, `dig`) for private zone resolution checks
- Container Apps logs (ingress/request and revision-level logs)
- Azure Monitor logs for networking and connection diagnostics

## 8. Procedure


### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-pe-fqdn-vs-ip-lab"
export LOCATION="koreacentral"
export VNET_NAME="vnet-pe-fqdn-vs-ip"
export ACA_SUBNET_NAME="snet-aca-infra"
export PE_SUBNET_NAME="snet-private-endpoint"
export VM_SUBNET_NAME="snet-jumpbox"
export ACA_ENV_NAME="cae-pe-fqdn-vs-ip"
export ACA_NAME="ca-pe-fqdn-vs-ip"
export LAW_NAME="law-pe-fqdn-vs-ip"
export ACR_NAME="acrpefqdnvsip$RANDOM"
export VM_NAME="vm-jumpbox"
export PRIVATE_DNS_ZONE="privatelink.koreacentral.azurecontainerapps.io"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

# VNet with 3 subnets: ACA infra, private endpoint, jumpbox VM
az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.80.0.0/16" \
  --subnet-name "$ACA_SUBNET_NAME" \
  --subnet-prefixes "10.80.0.0/23"

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$PE_SUBNET_NAME" \
  --address-prefixes "10.80.2.0/24"

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$VM_SUBNET_NAME" \
  --address-prefixes "10.80.3.0/24"

az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$ACA_SUBNET_NAME" \
  --delegations "Microsoft.App/environments"

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --location "$LOCATION" \
  --sku Basic

# Jumpbox VM inside VNet (used to test private endpoint access)
az vm create \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --image Ubuntu2204 \
  --admin-username azureuser \
  --generate-ssh-keys \
  --vnet-name "$VNET_NAME" \
  --subnet "$VM_SUBNET_NAME" \
  --size Standard_B1s
```

### 8.2 Application Code

```python
from flask import Flask, jsonify
import os
import socket
from datetime import datetime, timezone

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
    })


@app.get("/headers")
def headers():
    from flask import request
    return jsonify({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "host_header": request.host,
        "remote_addr": request.remote_addr,
        "headers": dict(request.headers),
    })
```

!!! note "Design notes"
    The `/health` endpoint confirms the app is reachable. The `/headers` endpoint
    reveals what host header and client IP the ingress forwards — critical for
    understanding how FQDN vs IP routing behaves at the Container Apps ingress layer.

### 8.3 Deploy

```bash
mkdir -p app-pe-fqdn-vs-ip

cat > app-pe-fqdn-vs-ip/app.py <<'PY'
# paste Python from section 8.2
PY

cat > app-pe-fqdn-vs-ip/requirements.txt <<'TXT'
flask==3.1.1
gunicorn==23.0.0
TXT

cat > app-pe-fqdn-vs-ip/Dockerfile <<'DOCKER'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
DOCKER

az acr build \
  --registry "$ACR_NAME" \
  --image pe-fqdn-vs-ip:v1 \
  --file app-pe-fqdn-vs-ip/Dockerfile \
  app-pe-fqdn-vs-ip

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query customerId --output tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query primarySharedKey --output tsv)

# Create internal-only Container Apps environment (private endpoint requires internal ingress)
az containerapp env create \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --location "$LOCATION" \
  --infrastructure-subnet-resource-id "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$VNET_NAME/subnets/$ACA_SUBNET_NAME" \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY" \
  --internal-only

az containerapp create \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --environment "$ACA_ENV_NAME" \
  --image "$ACR_NAME.azurecr.io/pe-fqdn-vs-ip:v1" \
  --target-port 8000 \
  --ingress external \
  --registry-server "$ACR_NAME.azurecr.io" \
  --min-replicas 1 \
  --max-replicas 1

# Get environment default domain and static IP
ENV_DEFAULT_DOMAIN=$(az containerapp env show \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --query properties.defaultDomain --output tsv)

ENV_STATIC_IP=$(az containerapp env show \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --query properties.staticIp --output tsv)

APP_FQDN=$(az containerapp show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --query properties.configuration.ingress.fqdn --output tsv)

echo "Default domain: $ENV_DEFAULT_DOMAIN"
echo "Static IP: $ENV_STATIC_IP"
echo "App FQDN: $APP_FQDN"

# Set up Private DNS zone for internal environment
az network private-dns zone create \
  --resource-group "$RG" \
  --name "$ENV_DEFAULT_DOMAIN"

az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$ENV_DEFAULT_DOMAIN" \
  --name "link-pe-fqdn-vs-ip" \
  --virtual-network "$VNET_NAME" \
  --registration-enabled false

az network private-dns record-set a add-record \
  --resource-group "$RG" \
  --zone-name "$ENV_DEFAULT_DOMAIN" \
  --record-set-name "*" \
  --ipv4-address "$ENV_STATIC_IP"
```

### 8.4 Test Execution

All tests run from the jumpbox VM inside the VNet.

```bash
# SSH into jumpbox
az ssh vm \
  --resource-group "$RG" \
  --name "$VM_NAME"

# Install test tools on jumpbox
sudo apt-get update && sudo apt-get install -y curl dnsutils openssl jq

# Set variables inside VM
export APP_FQDN="<paste APP_FQDN from deploy step>"
export STATIC_IP="<paste ENV_STATIC_IP from deploy step>"

# ── Test 1: FQDN access (expected: success) ──
echo "=== Test 1: FQDN access ==="
for i in $(seq 1 5); do
  echo "--- Run $i ---"
  nslookup "$APP_FQDN"
  curl --silent --max-time 10 "https://$APP_FQDN/health" | jq .
  curl --silent --max-time 10 "https://$APP_FQDN/headers" | jq .
  echo ""
  sleep 3
done

# ── Test 2: Direct IP access, no host header (expected: TLS or routing failure) ──
echo "=== Test 2: Direct IP, no host header ==="
for i in $(seq 1 5); do
  echo "--- Run $i ---"
  curl --verbose --max-time 10 "https://$STATIC_IP/health" 2>&1
  echo ""
  sleep 3
done

# ── Test 3: Direct IP with -k (skip TLS verify), no host header ──
echo "=== Test 3: Direct IP, skip TLS, no host header ==="
for i in $(seq 1 5); do
  echo "--- Run $i ---"
  curl --silent --insecure --max-time 10 "https://$STATIC_IP/health" 2>&1
  echo ""
  sleep 3
done

# ── Test 4: Direct IP with host header (expected: may work if SNI matched) ──
echo "=== Test 4: Direct IP + host header ==="
for i in $(seq 1 5); do
  echo "--- Run $i ---"
  curl --verbose --max-time 10 \
    --resolve "$APP_FQDN:443:$STATIC_IP" \
    "https://$APP_FQDN/health" 2>&1
  echo ""
  sleep 3
done

# ── Test 5: Direct IP with host header, skip TLS ──
echo "=== Test 5: Direct IP + host header + skip TLS ==="
for i in $(seq 1 5); do
  echo "--- Run $i ---"
  curl --silent --insecure --max-time 10 \
    -H "Host: $APP_FQDN" \
    "https://$STATIC_IP/health" 2>&1
  echo ""
  sleep 3
done

# ── Test 6: openssl s_client — certificate inspection ──
echo "=== Test 6a: TLS cert via FQDN ==="
echo | openssl s_client -connect "$APP_FQDN:443" -servername "$APP_FQDN" 2>/dev/null | openssl x509 -noout -subject -issuer -dates

echo "=== Test 6b: TLS cert via IP (no SNI) ==="
echo | openssl s_client -connect "$STATIC_IP:443" 2>/dev/null | openssl x509 -noout -subject -issuer -dates

echo "=== Test 6c: TLS cert via IP (with SNI) ==="
echo | openssl s_client -connect "$STATIC_IP:443" -servername "$APP_FQDN" 2>/dev/null | openssl x509 -noout -subject -issuer -dates

# ── Test 7: HTTP (port 80) direct IP access ──
echo "=== Test 7: HTTP direct IP (port 80) ==="
curl --verbose --max-time 10 "http://$STATIC_IP/health" 2>&1
curl --verbose --max-time 10 -H "Host: $APP_FQDN" "http://$STATIC_IP/health" 2>&1
```

### 8.5 Data Collection

```bash
# From local machine (outside jumpbox)
az containerapp logs show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --follow false

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query customerId --output tsv)

az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(2h) | where ContainerAppName_s == '$ACA_NAME' | project TimeGenerated, RevisionName_s, Log_s | order by TimeGenerated desc" \
  --output table

az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "ContainerAppSystemLogs_CL | where TimeGenerated > ago(2h) | where ContainerAppName_s == '$ACA_NAME' | project TimeGenerated, Reason_s, Log_s | order by TimeGenerated desc" \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- FQDN access via private DNS resolves to the private endpoint and succeeds with expected certificate/domain alignment.
- Direct IP access without matching SNI/host header fails TLS validation or returns ingress/domain errors.
- Direct IP access may only partially work when host header/SNI are forced, but behavior remains distinct from normal FQDN path and does not invalidate domain-bound certificate requirements.
- Failure category is repeatable by access pattern and explains customer reports where FQDN works while IP fails.

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

- Validate private DNS first (`privatelink` FQDN resolution) before testing direct IP variants.
- Record TLS handshake output and HTTP response together for each access pattern.
- Keep one variable change per request path (host header or SNI) to isolate failure causes.
- Run each case with TLS verification both enabled and explicitly disabled to separate certificate versus routing failures.
- Capture the exact endpoint string used (`https://fqdn` vs `https://ip`) in every test artifact.

## 16. Related guide / official docs

- [Microsoft Learn: Container Apps networking](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
- [azure-networking-practical-guide](https://github.com/yeongseon/azure-networking-practical-guide)
