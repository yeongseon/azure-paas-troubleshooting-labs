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

# Managed Identity RBAC Propagation vs Token Cache

!!! info "Status: Planned"

## 1. Question

After assigning an RBAC role to a managed identity, how long does it take for the role to become effective across different Azure services, and how does the Azure Identity SDK token cache interact with RBAC propagation delays?

## 2. Why this matters

Customers frequently report that managed identity authentication "doesn't work" immediately after role assignment. The RBAC propagation delay (documented as "up to 10 minutes" but highly variable) combined with SDK-level token caching creates a confusing window where:

1. The role is assigned but not yet propagated → 403 errors
2. The role propagates but the SDK has cached a token without the role → continued 403s
3. Both caches expire and the new role finally takes effect → success

Understanding the actual timing distribution across services helps support engineers estimate resolution windows and avoid unnecessary troubleshooting.

## 3. Customer symptom

- "We assigned the role 15 minutes ago but still getting 403 Forbidden."
- "It works from one function app but not another, even though both have the same role."
- "If we restart the app, it starts working — but we don't want to restart in production."

## 4. Hypothesis

1. RBAC propagation delay varies by service: Storage and Key Vault propagate within 5 minutes; Service Bus and Event Hubs may take longer.
2. The Azure Identity SDK caches tokens for 24 hours by default, masking propagation completion.
3. The combination of RBAC propagation + token cache creates a worst-case delay of up to 30 minutes without restart.
4. Restarting the application clears the token cache and picks up the propagated role immediately.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service, Functions, Container Apps (all three) |
| SKU / Plan | Various |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Hybrid (Config: does it propagate? Performance: how long does it take?)

**Controlled:**

- Target services: Storage Blob, Key Vault, Service Bus, SQL Database
- Role assignments: new assignment, role change, role removal
- Token cache: default behavior vs cache disabled
- Application restart: before/after propagation

**Observed:**

- Time from role assignment to first successful authenticated call
- Token cache hit/miss behavior
- 403 error rate over time after role assignment
- Propagation time distribution across services

**Independent run definition**: Fresh role assignment (previous role fully removed and confirmed), measure time to first success

**Planned runs per configuration**: 5 per target service

**Warm-up exclusion rule**: None — propagation delay IS the measurement

**Primary metric**: Time to first successful authenticated call; meaningful effect threshold: 2 minutes absolute

**Comparison method**: Descriptive statistics per service; Mann-Whitney U for cross-service comparison

## 7. Instrumentation

- Application code: repeated authentication attempts every 30 seconds with timestamp logging
- Application Insights: dependency call traces with success/failure
- Azure Activity Log: role assignment timestamp
- Custom logging: token acquisition events, cache hits, 403/200 transitions

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-mi-rbac-propagation-lab"
export LOCATION="koreacentral"
export STORAGE_NAME="stmirbacprop$RANDOM"
export KEYVAULT_NAME="kv-mi-rbac-prop-$RANDOM"
export SB_NAMESPACE="sb-mi-rbac-prop-$RANDOM"
export SB_QUEUE="q-propagation"
export APP_PLAN="plan-mi-rbac-prop"
export WEBAPP_NAME="app-mi-rbac-prop-$RANDOM"
export FUNC_NAME="func-mi-rbac-prop-$RANDOM"
export ACA_ENV_NAME="cae-mi-rbac-prop"
export ACA_NAME="ca-mi-rbac-prop"
export LAW_NAME="law-mi-rbac-prop"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-shared-key-access false \
  --allow-blob-public-access false

az keyvault create \
  --resource-group "$RG" \
  --name "$KEYVAULT_NAME" \
  --location "$LOCATION" \
  --enable-rbac-authorization true

az keyvault secret set \
  --vault-name "$KEYVAULT_NAME" \
  --name "propagation-sample" \
  --value "rbac-ready"

az servicebus namespace create \
  --resource-group "$RG" \
  --name "$SB_NAMESPACE" \
  --location "$LOCATION" \
  --sku Standard

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$SB_NAMESPACE" \
  --name "$SB_QUEUE"

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --location "$LOCATION"
```

### 8.2 Application Code

```python
import json
import os
from datetime import datetime, timezone

from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient
from azure.servicebus import ServiceBusClient

credential = ManagedIdentityCredential()


def probe_access():
    now = datetime.now(timezone.utc).isoformat()
    result = {"timestamp_utc": now, "keyvault": "fail", "storage": "fail", "servicebus": "fail"}
    try:
        kv = SecretClient(vault_url=os.environ["KEYVAULT_URI"], credential=credential)
        kv.get_secret("propagation-sample")
        result["keyvault"] = "success"
    except Exception as ex:
        result["keyvault_error"] = str(ex)
    try:
        blob = BlobServiceClient(account_url=os.environ["BLOB_URL"], credential=credential)
        blob.get_service_properties()
        result["storage"] = "success"
    except Exception as ex:
        result["storage_error"] = str(ex)
    try:
        sb = ServiceBusClient(fully_qualified_namespace=os.environ["SB_FQDN"], credential=credential)
        with sb.get_queue_sender(os.environ["SB_QUEUE"]) as sender:
            sender.send_messages("probe")
        result["servicebus"] = "success"
    except Exception as ex:
        result["servicebus_error"] = str(ex)
    return json.dumps(result)
```

```yaml
env:
  KEYVAULT_URI: https://<keyvault-name>.vault.azure.net/
  BLOB_URL: https://<storage-name>.blob.core.windows.net/
  SB_FQDN: <namespace>.servicebus.windows.net
  SB_QUEUE: q-propagation
```

### 8.3 Deploy

```bash
az appservice plan create \
  --resource-group "$RG" \
  --name "$APP_PLAN" \
  --location "$LOCATION" \
  --sku B1 \
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
  --location "$LOCATION"

az containerapp create \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --environment "$ACA_ENV_NAME" \
  --image "mcr.microsoft.com/k8se/quickstart:latest" \
  --ingress external \
  --target-port 80

for APP_NAME in "$WEBAPP_NAME" "$FUNC_NAME"; do
  az webapp identity assign --resource-group "$RG" --name "$APP_NAME" || true
  az functionapp identity assign --resource-group "$RG" --name "$APP_NAME" || true
done

az containerapp identity assign \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --system-assigned
```

### 8.4 Test Execution

```bash
WEBAPP_PRINCIPAL_ID=$(az webapp identity show --resource-group "$RG" --name "$WEBAPP_NAME" --query principalId --output tsv)
FUNC_PRINCIPAL_ID=$(az functionapp identity show --resource-group "$RG" --name "$FUNC_NAME" --query principalId --output tsv)
ACA_PRINCIPAL_ID=$(az containerapp identity show --resource-group "$RG" --name "$ACA_NAME" --query principalId --output tsv)

KV_ID=$(az keyvault show --resource-group "$RG" --name "$KEYVAULT_NAME" --query id --output tsv)
STORAGE_ID=$(az storage account show --resource-group "$RG" --name "$STORAGE_NAME" --query id --output tsv)
SB_ID=$(az servicebus namespace show --resource-group "$RG" --name "$SB_NAMESPACE" --query id --output tsv)

# 1) Start probe loop from each workload before role assignment (expect 403)
# Web App endpoint: https://$WEBAPP_NAME.azurewebsites.net/probe
# Function endpoint: https://$FUNC_NAME.azurewebsites.net/api/probe
# Container App endpoint: use FQDN from az containerapp show

# 2) Assign RBAC roles at T0
for PID in "$WEBAPP_PRINCIPAL_ID" "$FUNC_PRINCIPAL_ID" "$ACA_PRINCIPAL_ID"; do
  az role assignment create --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope "$KV_ID"
  az role assignment create --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" --scope "$STORAGE_ID"
  az role assignment create --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal --role "Azure Service Bus Data Sender" --scope "$SB_ID"
done

# 3) Poll every 30 seconds and record first success timestamp per service
for i in $(seq 1 60); do
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  curl --silent "https://$WEBAPP_NAME.azurewebsites.net/probe"
  curl --silent "https://$FUNC_NAME.azurewebsites.net/api/probe"
  sleep 30
done

# 4) Without restart, continue polling to detect token cache delay
for i in $(seq 1 20); do
  curl --silent "https://$WEBAPP_NAME.azurewebsites.net/probe"
  curl --silent "https://$FUNC_NAME.azurewebsites.net/api/probe"
  sleep 30
done

# 5) Restart workloads and compare immediate post-restart behavior
az webapp restart --resource-group "$RG" --name "$WEBAPP_NAME"
az functionapp restart --resource-group "$RG" --name "$FUNC_NAME"
az containerapp revision restart \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --revision "$(az containerapp revision list --resource-group "$RG" --name "$ACA_NAME" --query "[?properties.active].name | [0]" --output tsv)"

# 6) Repeat full assignment/poll cycle 5 runs per target service
```

### 8.5 Data Collection

```bash
az role assignment list \
  --resource-group "$RG" \
  --scope "$KV_ID" \
  --output table

az monitor activity-log list \
  --resource-group "$RG" \
  --status Succeeded \
  --max-events 200 \
  --output table

az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$WEBAPP_NAME" \
  --metric "Http4xx" "Http5xx" "Requests" \
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
  --workspace "$(az monitor log-analytics workspace show --resource-group "$RG" --workspace-name "$LAW_NAME" --query customerId --output tsv)" \
  --analytics-query "AppTraces | where TimeGenerated > ago(6h) | where Message has_any ('403','success','token') | project TimeGenerated, AppRoleName, Message | order by TimeGenerated asc" \
  --output table
```

### 8.6 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Storage Blob: propagation in 2-5 minutes
- Key Vault: propagation in 2-5 minutes
- Service Bus: propagation in 5-10 minutes
- SQL Database: propagation in 5-15 minutes
- Token cache extends apparent delay by up to 5-10 minutes beyond propagation
- Restart eliminates cache-related delay

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

- RBAC propagation timing is not guaranteed and may vary by region and load
- System-assigned vs user-assigned managed identity may have different propagation characteristics
- Ensure previous role assignments are fully removed before testing new assignments
- Token cache behavior depends on the Azure Identity SDK version

## 16. Related guide / official docs

- [What is Azure RBAC?](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)
- [Troubleshoot Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting)
- [Managed identities for Azure resources](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Azure Identity client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme)
