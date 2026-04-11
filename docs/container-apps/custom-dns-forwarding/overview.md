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

# Custom DNS Forwarding Failure in Container Apps Environment

!!! info "Status: Planned"

## 1. Question

When a Container Apps environment is configured with custom DNS servers and those servers are unreachable or misconfigured, what is the failure behavior for the application's outbound DNS resolution?

## 2. Why this matters

Container Apps environments in VNet can be configured with custom DNS servers for private name resolution. If the custom DNS is unreachable (firewall, routing, or server failure), all DNS resolution fails — including resolution of public endpoints that the app needs to function. This creates a total outage from a DNS infrastructure issue, not an application issue. The failure is especially confusing because the app starts successfully (DNS isn't needed at container start) but fails on the first outbound call.

## 3. Customer symptom

- "All outbound HTTP calls fail with `Name or service not known` after VNet configuration change."
- "The app worked fine until we changed the DNS server in the VNet."
- "Public APIs are unreachable from our Container App, but the container itself starts fine."

## 4. Hypothesis

When custom DNS servers configured for the Container Apps environment VNet are unreachable:

1. Container starts successfully (DNS not required at boot)
2. All outbound DNS queries fail, including for public FQDNs
3. The failure manifests as connection errors in the application, not as platform errors
4. There is no automatic fallback to Azure Default DNS (168.63.129.16)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption (VNet-injected) |
| Region | Korea Central |
| Runtime | Python 3.11 (custom container) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- VNet DNS configuration: Azure Default, custom DNS (reachable), custom DNS (unreachable)
- DNS server scenarios: wrong IP, correct IP but port blocked, intermittent availability
- Resolution targets: private endpoint FQDN, public FQDN (e.g., microsoft.com)

**Observed:**

- DNS resolution success/failure per target
- Outbound HTTP request success/failure
- Container startup behavior
- System-level DNS resolver behavior (`/etc/resolv.conf`)

## 7. Instrumentation

- Container console: `nslookup`, `dig`, `cat /etc/resolv.conf`
- Application logging: DNS resolution timing and results
- Application Insights: dependency call failures
- Azure Monitor: container restart events

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-custom-dns-forwarding-lab"
export LOCATION="koreacentral"
export VNET_NAME="vnet-custom-dns-forwarding"
export ACA_SUBNET_NAME="snet-aca-infra"
export DNS_SUBNET_NAME="snet-dns"
export ACA_ENV_NAME="cae-custom-dns-forwarding"
export ACA_NAME="ca-custom-dns-forwarding"
export LAW_NAME="law-custom-dns-forwarding"
export ACR_NAME="acrcustomdns$RANDOM"
export DNS_VM_NAME="vm-custom-dns"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --location "$LOCATION" \
  --address-prefixes "10.70.0.0/16" \
  --subnet-name "$ACA_SUBNET_NAME" \
  --subnet-prefixes "10.70.0.0/23"

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET_NAME" \
  --name "$DNS_SUBNET_NAME" \
  --address-prefixes "10.70.2.0/24"

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

az vm create \
  --resource-group "$RG" \
  --name "$DNS_VM_NAME" \
  --image Ubuntu2204 \
  --admin-username azureuser \
  --generate-ssh-keys \
  --vnet-name "$VNET_NAME" \
  --subnet "$DNS_SUBNET_NAME" \
  --private-ip-address "10.70.2.4"
```

### 8.2 Application Code

```python
from flask import Flask, jsonify
import os
import socket
import subprocess
from datetime import datetime, timezone

app = Flask(__name__)
TARGET_FQDN = os.getenv("TARGET_FQDN", "microsoft.com")


@app.get("/dns-check")
def dns_check():
    resolved = []
    error = None
    try:
        resolved = sorted({item[4][0] for item in socket.getaddrinfo(TARGET_FQDN, 443)})
    except Exception as ex:
        error = str(ex)

    resolv_conf = subprocess.getoutput("cat /etc/resolv.conf")
    return jsonify(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target": TARGET_FQDN,
            "resolved_ips": resolved,
            "error": error,
            "resolv_conf": resolv_conf,
        }
    )
```

```yaml
name: dns-forwarding-test
ingress:
  external: true
  targetPort: 8000
env:
  - name: TARGET_FQDN
    value: microsoft.com
```

### 8.3 Deploy

```bash
mkdir -p app-custom-dns-forwarding

cat > app-custom-dns-forwarding/app.py <<'PY'
# paste Python from section 8.2
PY

cat > app-custom-dns-forwarding/requirements.txt <<'TXT'
flask==3.1.1
gunicorn==23.0.0
TXT

cat > app-custom-dns-forwarding/Dockerfile <<'DOCKER'
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
  --image dns-forwarding-test:v1 \
  --file app-custom-dns-forwarding/Dockerfile \
  app-custom-dns-forwarding

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query customerId --output tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query primarySharedKey --output tsv)

az containerapp env create \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --location "$LOCATION" \
  --infrastructure-subnet-resource-id "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$VNET_NAME/subnets/$ACA_SUBNET_NAME" \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY"

az containerapp create \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --environment "$ACA_ENV_NAME" \
  --image "$ACR_NAME.azurecr.io/dns-forwarding-test:v1" \
  --target-port 8000 \
  --ingress external \
  --registry-server "$ACR_NAME.azurecr.io" \
  --min-replicas 1 \
  --max-replicas 1 \
  --env-vars TARGET_FQDN="microsoft.com"
```

### 8.4 Test Execution

```bash
APP_FQDN=$(az containerapp show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --query properties.configuration.ingress.fqdn --output tsv)

export APP_URL="https://$APP_FQDN/dns-check"

# 1) Baseline with Azure default DNS (no custom DNS server)
for i in $(seq 1 10); do
  curl --silent "$APP_URL"
  sleep 5
done

# 2) Configure VNet custom DNS to unreachable server
az network vnet update \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --dns-servers "10.70.2.250"

# 3) Restart revision to pick up DNS path behavior
az containerapp revision restart \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --revision "$(az containerapp revision list --resource-group "$RG" --name "$ACA_NAME" --query "[?properties.active].name | [0]" --output tsv)"

# 4) Probe resolution failures for public FQDN
for i in $(seq 1 24); do
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  curl --silent "$APP_URL"
  sleep 10
done

# 5) Optional: configure reachable DNS server on VM and retest
az network vnet update \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --dns-servers "10.70.2.4"

for i in $(seq 1 24); do
  curl --silent "$APP_URL"
  sleep 10
done

# 6) Restore Azure default DNS and verify recovery
az network vnet update \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --dns-servers ""

for i in $(seq 1 10); do
  curl --silent "$APP_URL"
  sleep 5
done
```

### 8.5 Data Collection

```bash
az containerapp logs show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --follow false

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.App/containerApps/$ACA_NAME" \
  --metric "Requests" "ResponseTime" \
  --interval PT1M \
  --aggregation Average Maximum Total \
  --output table

az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(4h) | where ContainerAppName_s == '$ACA_NAME' | where Log_s has_any ('Name or service not known','Temporary failure in name resolution','resolv.conf') | project TimeGenerated, RevisionName_s, Log_s | order by TimeGenerated desc" \
  --output table

az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "ContainerAppSystemLogs_CL | where TimeGenerated > ago(4h) | where ContainerAppName_s == '$ACA_NAME' | project TimeGenerated, Reason_s, Log_s | order by TimeGenerated desc" \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Container starts successfully regardless of DNS server reachability
- First outbound DNS query fails immediately (unreachable) or times out (blocked port)
- All subsequent outbound HTTP calls fail with name resolution errors
- `/etc/resolv.conf` shows the custom DNS server configured in the VNet
- No fallback to Azure Default DNS

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

- VNet injection is required for custom DNS
- DNS changes propagate through VNet settings, not container configuration
- The container environment inherits DNS from the VNet; there's no container-level DNS override

## 16. Related guide / official docs

- [Networking in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Provide a custom DNS for your Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/environment-custom-dns)
- [Name resolution for resources in Azure virtual networks](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
