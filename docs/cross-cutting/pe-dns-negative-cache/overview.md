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

# Private Endpoint Cutover and DNS Negative Caching

!!! info "Status: Planned"

## 1. Question

When enabling a private endpoint for an Azure service and updating DNS to resolve to the private IP, how does DNS negative caching affect the transition period, and can it cause extended outages beyond the expected DNS TTL?

## 2. Why this matters

Private endpoint migrations are high-risk operations. The expected flow is: create private endpoint → update DNS → traffic flows to private IP. But DNS negative caching (caching of NXDOMAIN or failed lookups) can cause problems:

- If the private DNS zone is created but the link to the VNet is delayed, clients may cache the negative result
- If the DNS query returns NXDOMAIN during the transition window, that negative response gets cached
- The negative cache TTL may be longer than the positive TTL, extending the outage

## 3. Customer symptom

- "We created the private endpoint and DNS zone, but resolution still shows the public IP after 30 minutes."
- "Some instances resolve the private IP, others still resolve the public IP."
- "After restart, everything works — but without restart, the old resolution persists for hours."

## 4. Hypothesis

1. DNS negative caching (NXDOMAIN caching) in the VNet resolver causes extended resolution failures during private endpoint cutover.
2. The negative cache TTL (SOA minimum) can be 5-60 minutes, independent of the A record TTL.
3. If the private DNS zone link is created after the first DNS query, the negative cache prevents the client from seeing the new private IP until the negative cache expires.
4. Different Azure compute services (App Service, Functions, Container Apps) handle DNS cache differently, leading to inconsistent behavior across services.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service, Functions, Container Apps (all three) |
| SKU / Plan | Various (VNet-integrated) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Hybrid (Config: does resolution switch? Performance: how long does it take?)

**Controlled:**

- Private endpoint target: Storage Account, SQL Database
- DNS configuration sequence: zone first vs link first vs simultaneous
- VNet DNS: Azure Default (168.63.129.16) vs custom DNS forwarder
- Client compute: App Service, Functions, Container Apps

**Observed:**

- DNS resolution result (public IP vs private IP) over time per client
- Negative cache duration
- Time from DNS change to consistent private resolution across all instances
- Connectivity success/failure to private endpoint during transition

**Independent run definition**: Clean VNet with no prior DNS cache, fresh deployment, create private endpoint and DNS zone with specified sequencing

**Planned runs per configuration**: 3 (minimum; this is expensive to set up)

**Warm-up exclusion rule**: None — the transition IS the measurement

**Primary metric**: Time from DNS zone link to consistent private IP resolution; meaningful effect threshold: >5 minutes

**Comparison method**: Descriptive statistics per sequencing strategy

## 7. Instrumentation

- Application code: DNS resolution polling every 30 seconds with resolved IP logging
- `nslookup`/`dig` from Kudu/console: direct DNS queries with TTL inspection
- Application Insights: dependency calls with resolved endpoint IP
- Azure Monitor: Private DNS Zone query logs

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-pe-dns-negative-cache-lab"
export LOCATION="koreacentral"
export VNET_NAME="vnet-pe-dns-negative-cache"
export APP_SUBNET_NAME="snet-appsvc"
export FUNC_SUBNET_NAME="snet-functions"
export ACA_SUBNET_NAME="snet-containerapps"
export PE_SUBNET_NAME="snet-private-endpoint"
export STORAGE_NAME="stpednscache$RANDOM"
export APP_PLAN="plan-pe-dns-negative-cache"
export WEBAPP_NAME="app-pe-dns-cache-$RANDOM"
export FUNC_NAME="func-pe-dns-cache-$RANDOM"
export ACA_ENV_NAME="cae-pe-dns-cache"
export ACA_NAME="ca-pe-dns-cache"
export PRIVATE_DNS_ZONE="privatelink.blob.core.windows.net"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.90.0.0/16" \
  --subnet-name "$APP_SUBNET_NAME" \
  --subnet-prefixes "10.90.0.0/24"

az network vnet subnet create --resource-group "$RG" --vnet-name "$VNET_NAME" --name "$FUNC_SUBNET_NAME" --address-prefixes "10.90.1.0/24"
az network vnet subnet create --resource-group "$RG" --vnet-name "$VNET_NAME" --name "$ACA_SUBNET_NAME" --address-prefixes "10.90.2.0/23"
az network vnet subnet create --resource-group "$RG" --vnet-name "$VNET_NAME" --name "$PE_SUBNET_NAME" --address-prefixes "10.90.4.0/24"

az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$ACA_SUBNET_NAME" \
  --delegations "Microsoft.App/environments"

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-shared-key-access false \
  --allow-blob-public-access false
```

### 8.2 Application Code

```python
import json
import os
import socket
from datetime import datetime, timezone

from flask import Flask

app = Flask(__name__)
TARGET = os.getenv("TARGET_FQDN")


@app.get("/dns-probe")
def dns_probe():
    ips = []
    error = None
    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(TARGET, 443)})
    except Exception as ex:
        error = str(ex)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "resolved_ips": ips,
        "error": error,
    }
```

```yaml
env:
  TARGET_FQDN: <storage-name>.blob.core.windows.net
probes:
  intervalSeconds: 30
```

### 8.3 Deploy

```bash
az appservice plan create \
  --resource-group "$RG" \
  --name "$APP_PLAN" \
  --location "$LOCATION" \
  --sku P1v3 \
  --is-linux

az webapp create \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --plan "$APP_PLAN" \
  --runtime "PYTHON|3.11"

az functionapp create \
  --resource-group "$RG" \
  --name "$FUNC_NAME" \
  --storage-account "$STORAGE_NAME" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --flexconsumption-location "$LOCATION"

az containerapp env create \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --location "$LOCATION" \
  --infrastructure-subnet-resource-id "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$VNET_NAME/subnets/$ACA_SUBNET_NAME"

az containerapp create \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --environment "$ACA_ENV_NAME" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --ingress external \
  --target-port 80

az webapp vnet-integration add \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --vnet "$VNET_NAME" \
  --subnet "$APP_SUBNET_NAME"

az functionapp vnet-integration add \
  --resource-group "$RG" \
  --name "$FUNC_NAME" \
  --vnet "$VNET_NAME" \
  --subnet "$FUNC_SUBNET_NAME"
```

### 8.4 Test Execution

```bash
export TARGET_FQDN="$STORAGE_NAME.blob.core.windows.net"

# 1) Baseline: public endpoint resolution before private endpoint creation
for i in $(seq 1 10); do
  nslookup "$TARGET_FQDN"
  sleep 10
done

# 2) Create private endpoint first, but delay private DNS zone link (induce NXDOMAIN window)
az network private-endpoint create \
  --resource-group "$RG" \
  --name "pe-storage" \
  --location "$LOCATION" \
  --subnet "$PE_SUBNET_NAME" \
  --vnet-name "$VNET_NAME" \
  --private-connection-resource-id "$(az storage account show --resource-group "$RG" --name "$STORAGE_NAME" --query id --output tsv)" \
  --group-id blob \
  --connection-name "pe-storage-conn"

az network private-dns zone create \
  --resource-group "$RG" \
  --name "$PRIVATE_DNS_ZONE"

# 3) Query during unlinked-zone window to trigger potential negative caching
for i in $(seq 1 20); do
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  nslookup "$TARGET_FQDN" || true
  sleep 15
done

# 4) Link zone to VNet and create zone group
az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --name "link-pe-dns-cache" \
  --virtual-network "$VNET_NAME" \
  --registration-enabled false

az network private-endpoint dns-zone-group create \
  --resource-group "$RG" \
  --endpoint-name "pe-storage" \
  --name "default" \
  --private-dns-zone "$PRIVATE_DNS_ZONE" \
  --zone-name "zonegroup-storage"

# 5) Poll every 30 seconds from each client compute and track first private IP response
for i in $(seq 1 60); do
  nslookup "$TARGET_FQDN" || true
  curl --silent "https://$WEBAPP_NAME.azurewebsites.net/dns-probe" || true
  curl --silent "https://$FUNC_NAME.azurewebsites.net/api/dns-probe" || true
  sleep 30
done

# 6) Restart clients and compare cache-cleared behavior
az webapp restart --resource-group "$RG" --name "$WEBAPP_NAME"
az functionapp restart --resource-group "$RG" --name "$FUNC_NAME"
az containerapp revision restart \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --revision "$(az containerapp revision list --resource-group "$RG" --name "$ACA_NAME" --query "[?properties.active].name | [0]" --output tsv)"
```

### 8.5 Data Collection

```bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "pe-storage" \
  --query "customDnsConfigs" \
  --output table

az network private-dns record-set a list \
  --resource-group "$RG" \
  --zone-name "$PRIVATE_DNS_ZONE" \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$WEBAPP_NAME" \
  --metric "Http5xx" "Requests" \
  --interval PT1M \
  --aggregation Total \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$FUNC_NAME" \
  --metric "FunctionExecutionCount" "FunctionExecutionUnits" \
  --interval PT1M \
  --aggregation Total \
  --output table

az monitor log-analytics query \
  --workspace "$(az monitor log-analytics workspace list --resource-group "$RG" --query "[0].customerId" --output tsv)" \
  --analytics-query "AppTraces | where TimeGenerated > ago(6h) | where Message has_any ('NXDOMAIN','Temporary failure','resolved_ips') | project TimeGenerated, AppRoleName, Message | order by TimeGenerated asc" \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Zone-first deployment: brief NXDOMAIN period until A record is created → negative cache delays resolution by 5-30 minutes
- Simultaneous deployment: minimal negative cache impact, switch happens within positive TTL
- Custom DNS forwarder: additional caching layer adds 0-15 minutes delay
- Restart of compute service clears DNS cache and immediately resolves new IP

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

- DNS negative cache behavior depends on the VNet resolver implementation, which may change across regions
- Private DNS Zone link propagation has its own delay independent of DNS TTL
- Testing requires VNet integration on all compute services
- Clean up DNS zones and links completely between test runs to avoid cache contamination

## 16. Related guide / official docs

- [Azure Private Endpoint DNS configuration](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns)
- [Azure Private DNS zones](https://learn.microsoft.com/en-us/azure/dns/private-dns-overview)
- [What is Azure Private Link?](https://learn.microsoft.com/en-us/azure/private-link/private-link-overview)
- [Name resolution for resources in Azure virtual networks](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
