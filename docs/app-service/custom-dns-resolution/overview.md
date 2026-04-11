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

# Custom DNS and Private Name Resolution Drift

!!! info "Status: Planned"

## 1. Question

When an App Service with VNet integration uses custom DNS settings or Private DNS Zones, can DNS resolution drift (stale cache, zone link changes, or conditional forwarder misconfiguration) cause intermittent connectivity failures to private endpoints?

## 2. Why this matters

VNet-integrated App Service apps rely on DNS to resolve private endpoint FQDNs. When DNS configuration changes — zone links added/removed, forwarder rules updated, or TTL-based cache entries expire — there can be a window where some instances resolve the old (public) IP while others resolve the new (private) IP. This creates intermittent failures that are extremely difficult to diagnose because they depend on which instance handles the request and when its DNS cache refreshed.

## 3. Customer symptom

- "Connections to our database randomly fail after we added a private endpoint."
- "Some requests go to the public IP and get blocked by the firewall, others work fine."
- "The problem goes away if we restart the app, but comes back after a few hours."

## 4. Hypothesis

After modifying Private DNS Zone links or custom DNS forwarder rules for a VNet-integrated App Service:

1. DNS resolution on existing instances will continue using cached entries until TTL expires.
2. During the cache transition window, different instances may resolve different IPs for the same FQDN.
3. New instances (from scale-out or restart) will immediately use the updated DNS configuration.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | P1v3 (VNet integration required) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Private DNS Zone configuration (link/unlink to VNet)
- Custom DNS server settings
- VNet integration configuration
- Number of instances (2+)

**Observed:**

- DNS resolution results per instance (nslookup/dig output)
- Connectivity success/failure to private endpoint
- DNS TTL values and cache expiry timing
- Resolution consistency across instances

## 7. Instrumentation

- Kudu/SSH console: `nslookup`, `dig` commands from each instance
- Application Insights: dependency call success/failure with resolved IP
- Application logging: DNS resolution results with timestamps
- Azure Monitor: VNet integration status

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export RG="rg-custom-dns-resolution-lab"
export LOCATION="koreacentral"
export PLAN_NAME="plan-custom-dns-resolution"
export APP_NAME="app-custom-dns-resolution"
export VNET_NAME="vnet-custom-dns-resolution"
export INTEGRATION_SUBNET="snet-appsvc-integration"
export PE_SUBNET="snet-private-endpoint"
export STORAGE_NAME="stcustomdnsres$RANDOM"
export PRIVATE_DNS_ZONE="privatelink.blob.core.windows.net"

az group create --name "$RG" --location "$LOCATION"

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.70.0.0/16" \
  --subnet-name "$INTEGRATION_SUBNET" \
  --subnet-prefixes "10.70.1.0/24"

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$PE_SUBNET" \
  --address-prefixes "10.70.2.0/24"

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

az webapp scale --resource-group "$RG" --name "$APP_NAME" --number-of-workers 2

az webapp vnet-integration add \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --vnet "$VNET_NAME" \
  --subnet "$INTEGRATION_SUBNET"

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --allow-blob-public-access false \
  --allow-shared-key-access false \
  --default-action Deny

az network private-dns zone create --resource-group "$RG" --name "$PRIVATE_DNS_ZONE"
az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --name "link-initial" \
  --virtual-network "$VNET_NAME" \
  --registration-enabled false

STORAGE_ID=$(az storage account show --resource-group "$RG" --name "$STORAGE_NAME" --query id --output tsv)
PE_ID=$(az network private-endpoint create \
  --resource-group "$RG" \
  --name "pe-storage" \
  --vnet-name "$VNET_NAME" \
  --subnet "$PE_SUBNET" \
  --private-connection-resource-id "$STORAGE_ID" \
  --group-id blob \
  --connection-name "conn-storage" \
  --query id --output tsv)

NIC_ID=$(az network private-endpoint show --resource-group "$RG" --name "pe-storage" --query "networkInterfaces[0].id" --output tsv)
PE_IP=$(az network nic show --ids "$NIC_ID" --query "ipConfigurations[0].privateIPAddress" --output tsv)
az network private-dns record-set a add-record \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --record-set-name "$STORAGE_NAME" \
  --ipv4-address "$PE_IP"
```

### 8.2 Application Code

```python
from flask import Flask, jsonify
import os
import socket
from datetime import datetime, timezone

app = Flask(__name__)
TARGET_FQDN = os.environ.get("TARGET_FQDN")


@app.get("/dns-check")
def dns_check():
    ips = sorted({item[4][0] for item in socket.getaddrinfo(TARGET_FQDN, 443, proto=socket.IPPROTO_TCP)})
    return jsonify(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "unknown"),
            "target_fqdn": TARGET_FQDN,
            "resolved_ips": ips,
        }
    )
```

```yaml
runtime: python311
startupCommand: gunicorn --bind=0.0.0.0 --timeout 180 app:app
appSettings:
  WEBSITE_VNET_ROUTE_ALL: "1"
  TARGET_FQDN: "<storage-name>.blob.core.windows.net"
```

### 8.3 Deploy

```bash
mkdir -p app-custom-dns-resolution
cat > app-custom-dns-resolution/app.py <<'PY'
from app import app
PY

cat > app-custom-dns-resolution/requirements.txt <<'TXT'
flask==3.1.1
gunicorn==23.0.0
TXT

cat > app-custom-dns-resolution/startup.sh <<'SH'
gunicorn --bind=0.0.0.0 --timeout 180 app:app
SH

cd app-custom-dns-resolution && zip -r ../app-custom-dns-resolution.zip .

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings WEBSITE_VNET_ROUTE_ALL=1 TARGET_FQDN="$STORAGE_NAME.blob.core.windows.net" SCM_DO_BUILD_DURING_DEPLOYMENT=true

az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 180 app:app"

az webapp deploy \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src-path "app-custom-dns-resolution.zip" \
  --type zip
```

### 8.4 Test Execution

```bash
export APP_URL="https://$APP_NAME.azurewebsites.net"

# 1) Baseline: linked zone, expect private endpoint IP
for i in $(seq 1 10); do
  curl "$APP_URL/dns-check"
  sleep 5
done

# 2) Introduce drift: remove VNet link, keep app running
az network private-dns link vnet delete \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --name "link-initial" \
  --yes

# 3) Probe for mixed resolution/failures while caches expire
for i in $(seq 1 30); do
  curl "$APP_URL/dns-check"
  sleep 10
done

# 4) Re-link zone and observe transition back to private IP
az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --name "link-restored" \
  --virtual-network "$VNET_NAME" \
  --registration-enabled false

for i in $(seq 1 30); do
  curl "$APP_URL/dns-check"
  sleep 10
done
```

### 8.5 Data Collection

```bash
APP_INSIGHTS_ID=$(az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APP_NAME" \
  --query appId --output tsv)

az webapp log tail --resource-group "$RG" --name "$APP_NAME"

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "requests | where timestamp > ago(2h) | project timestamp, resultCode, success, cloud_RoleInstance, customDimensions | order by timestamp desc" \
  --output table

az monitor app-insights query \
  --app "$APP_INSIGHTS_ID" \
  --analytics-query "traces | where timestamp > ago(2h) and message has 'resolved_ips' | project timestamp, cloud_RoleInstance, message | order by timestamp asc" \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- After DNS change, existing instances continue resolving old IP for TTL duration
- New instances or restarted instances immediately resolve new IP
- Intermittent failures during the transition window correlate with instance-level DNS cache state

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

- VNet integration is required (P1v3 or higher, or Regional VNet Integration on lower SKUs)
- Private DNS Zone must be linked to the integration VNet
- DNS TTL values affect the transition window duration

## 16. Related guide / official docs

- [Azure App Service VNet integration](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration)
- [Azure Private DNS](https://learn.microsoft.com/en-us/azure/dns/private-dns-overview)
- [Name resolution for resources in Azure virtual networks](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
