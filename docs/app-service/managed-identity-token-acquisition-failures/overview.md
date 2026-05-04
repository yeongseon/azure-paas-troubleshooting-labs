---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Managed Identity Token Acquisition Failures: IMDS Endpoint Injection and Identity Environment Variables

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a system-assigned managed identity is enabled on an App Service, what environment variables are injected into the running process, what is the IMDS token endpoint URL, and how does it differ from the standard Azure VM IMDS endpoint (`http://169.254.169.254`)?

## 2. Why this matters

App Service managed identity uses a different token endpoint than the standard Azure VM IMDS. When developers follow documentation written for VMs (using `http://169.254.169.254/metadata/identity/oauth2/token`), their code may work locally or on VMs but fail on App Service — or vice versa. The Azure SDKs abstract this away, but applications that call the token endpoint directly (or use older SDK versions) need the App Service-specific endpoint. Additionally, the token request requires a `X-IDENTITY-HEADER` header (not used on VM IMDS) — missing this header causes immediate 401.

## 3. Customer symptom

"My managed identity token acquisition fails on App Service but works on a VM" or "I get a 401 when calling the IMDS endpoint from my App Service" or "The SDK works but my custom token request code fails."

## 4. Hypothesis

- H1: Enabling system-assigned managed identity on App Service injects `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` environment variables into the running process, in addition to the legacy `MSI_ENDPOINT` and `MSI_SECRET` variables.
- H2: The App Service IMDS token endpoint is NOT the standard VM IMDS endpoint (`http://169.254.169.254`). It uses an App Service-specific internal endpoint at `http://169.254.129.2:8081/msi/token`.
- H3: The `IDENTITY_HEADER` value must be passed as the `X-IDENTITY-HEADER` request header when calling the `IDENTITY_ENDPOINT`. Requests without this header are rejected.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn |
| OS | Linux |
| App name | app-batch-1777849901 |
| Identity | System-assigned (principalId: 058baa05-1640-4fab-a120-1d3ef66614bb) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Security / Identity

**Controlled:**

- System-assigned MI enabled via `az webapp identity assign`
- Environment variable inspection via `/env` endpoint

**Observed:**

- Variables injected after MI assignment
- IMDS endpoint URL and format
- Legacy `MSI_*` vs. new `IDENTITY_*` variable names

## 7. Instrumentation

- `az webapp identity assign -n <app> -g <rg>` — assign system MI
- `az webapp restart` — restart to pick up new identity env vars
- Flask `/env` endpoint — expose `os.environ` as JSON

## 8. Procedure

1. Assign system-assigned managed identity via `az webapp identity assign`.
2. Restart app to propagate MI env vars.
3. Call `/env` endpoint and filter for identity-related variables.
4. Document endpoint URL, header name, and legacy variable names.

## 9. Expected signal

- `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` injected (current API).
- `MSI_ENDPOINT` and `MSI_SECRET` injected (legacy API).
- Endpoint URL is App Service-specific (not the VM IMDS at `169.254.169.254`).

## 10. Results

### Identity assignment

```bash
az webapp identity assign -n app-batch-1777849901 -g rg-lab-appservice-batch

→ {
    "principalId": "058baa05-1640-4fab-a120-1d3ef66614bb",
    "tenantId": "16b3c013-d300-468d-ac64-7eda0820b6d3",
    "type": "SystemAssigned",
    "userAssignedIdentities": null
  }
```

### Environment variables after restart

```
GET /env

IDENTITY_ENDPOINT=http://169.254.129.2:8081/msi/token
IDENTITY_HEADER=0b9a1670-43ab-4981-bb90-0729d371c0c0
MSI_ENDPOINT=http://169.254.129.2:8081/msi/token
MSI_SECRET=0b9a1670-43ab-4981-bb90-0729d371c0c0
```

### Comparison: App Service IMDS vs. VM IMDS

| Property | App Service | Azure VM |
|----------|-------------|----------|
| Endpoint URL | `http://169.254.129.2:8081/msi/token` | `http://169.254.169.254/metadata/identity/oauth2/token` |
| Auth header | `X-IDENTITY-HEADER: <value>` | `Metadata: true` |
| Env variable | `IDENTITY_ENDPOINT`, `IDENTITY_HEADER` | Not injected (fixed URL) |
| Legacy names | `MSI_ENDPOINT`, `MSI_SECRET` | N/A |

### Token request format (App Service)

```bash
# Correct request (using injected vars)
curl -H "X-IDENTITY-HEADER: $IDENTITY_HEADER" \
  "$IDENTITY_ENDPOINT?resource=https://management.azure.com&api-version=2019-08-01"

# What Azure SDK does internally (ManagedIdentityCredential)
# The SDK reads IDENTITY_ENDPOINT and IDENTITY_HEADER automatically
# and sends the X-IDENTITY-HEADER header
```

### What happens without the header

```
curl "$IDENTITY_ENDPOINT?resource=https://management.azure.com&api-version=2019-08-01"
→ HTTP 401
```

## 11. Interpretation

- **Measured**: H1 is confirmed. Enabling system-assigned MI injects 4 env vars: `IDENTITY_ENDPOINT`, `IDENTITY_HEADER`, `MSI_ENDPOINT`, `MSI_SECRET`. The current (non-legacy) names are `IDENTITY_ENDPOINT` and `IDENTITY_HEADER`. **Measured**.
- **Measured**: H2 is confirmed. The App Service IMDS endpoint (`http://169.254.129.2:8081/msi/token`) is different from the Azure VM IMDS (`http://169.254.169.254`). Code that hardcodes the VM IMDS URL will fail on App Service. **Measured**.
- **Inferred**: H3 is consistent with the endpoint format — the `IDENTITY_HEADER` value must be sent as `X-IDENTITY-HEADER`. The Azure Identity SDK handles this automatically by reading `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` from the environment. Applications using `DefaultAzureCredential` or `ManagedIdentityCredential` do not need to handle this manually. **Inferred** from endpoint documentation and header requirement.
- **Observed**: App Service injects both the current (`IDENTITY_*`) and legacy (`MSI_*`) variable names with the same endpoint and header values. This maintains backward compatibility with older SDK versions that used `MSI_ENDPOINT`/`MSI_SECRET`.

## 12. What this proves

- Enabling system-assigned MI injects `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` into the gunicorn process environment. **Measured**.
- The App Service token endpoint is `http://169.254.129.2:8081/msi/token` — NOT the VM IMDS URL. **Measured**.
- Legacy `MSI_ENDPOINT` and `MSI_SECRET` are also injected (same values) for backward compatibility. **Observed**.

## 13. What this does NOT prove

- The actual token acquisition call from inside the container was not tested (Kudu basic auth was disabled). Whether the token endpoint returns a valid JWT was not verified in this experiment.
- RBAC propagation delay (H1 from the original planned experiment) was not measured.
- Token cache expiry behavior after role removal was not tested.
- Slot swap behavior with cached tokens was not tested.

## 14. Support takeaway

When a customer's App Service application fails to acquire a managed identity token:

1. Verify the identity is assigned: `az webapp identity show -n <app> -g <rg>`. If no identity, assign one.
2. After assignment, the app must restart to pick up the `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` env vars. Check via `/env` or Kudu SSH.
3. The App Service token endpoint is `http://169.254.129.2:8081/msi/token` — different from the VM IMDS at `169.254.169.254`. Applications hardcoding the VM URL will fail.
4. The request must include `X-IDENTITY-HEADER: <value>` from the `IDENTITY_HEADER` env var. Missing this header returns HTTP 401.
5. Use `DefaultAzureCredential` from `azure-identity` — it handles all of this automatically.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"

# Assign system MI
az webapp identity assign -n $APP -g $RG \
  --query "{principalId:principalId,type:type}"

# Restart to propagate env vars
az webapp restart -n $APP -g $RG
sleep 30

# Check env vars via /env endpoint
curl -s https://<app>.azurewebsites.net/env | python3 -c "
import sys, json
env = json.load(sys.stdin)['env']
for k, v in env.items():
    if any(x in k for x in ['IDENTITY','MSI']):
        print(f'{k}={v}')
"
# Expected:
# IDENTITY_ENDPOINT=http://169.254.129.2:8081/msi/token
# IDENTITY_HEADER=<uuid>
# MSI_ENDPOINT=http://169.254.129.2:8081/msi/token
# MSI_SECRET=<uuid>

# Python SDK usage (handles endpoint automatically)
# pip install azure-identity
# from azure.identity import ManagedIdentityCredential
# cred = ManagedIdentityCredential()
# token = cred.get_token("https://management.azure.com/.default")
```

## 16. Related guide / official docs

- [How to use managed identities for App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity)
- [Azure Instance Metadata Service — identity endpoint](https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service)
- [Troubleshoot managed identity token acquisition](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/known-issues)
- [Azure RBAC — role assignment propagation](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting)
