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

# App Setting and Environment Variable Limits

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

What are the enforced limits on App Service app settings — in count, individual value length, and total size — and how are limit violations reported? Do violations cause silent truncation or explicit errors?

## 2. Why this matters

App settings are the primary configuration surface for App Service apps. Applications that use feature flags, multi-tenant configuration, or inject configuration via deployment pipelines can accumulate many settings over time. Support cases arise when:

- Configuration deployments fail silently in ARM/Bicep
- An app setting value is truncated without error, causing cryptic application failures
- The ARM API accepts a setting update but the running app does not see the expected value
- A Key Vault reference in an app setting fails to resolve and falls back to the literal string

Understanding the exact limits and failure modes prevents misdiagnosis of configuration-related application failures.

## 3. Customer symptom

- "We added a new app setting but the application is still using the old value."
- "Our ARM deployment succeeded but the setting didn't take effect."
- "The application reads an empty string for a setting we definitely set."
- "We can't add more than X settings — the portal returns an error."

## 4. Hypothesis

**H1 — Total count limit**: App Service enforces a maximum number of app settings (likely 100 or 1000). Exceeding this limit causes the ARM API to return a 400 or 409 error.

**H2 — Value length limit**: Individual app setting values have a maximum length. Values exceeding the limit are either rejected or silently truncated.

**H3 — Key Vault reference fallback**: A malformed Key Vault reference (wrong vault name, wrong secret name) causes the running app to receive the literal reference string rather than the resolved secret value.

**H4 — Slot-specific limits**: Slot settings (marked as "sticky") count toward the same total limit as regular settings, not a separate limit.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Linux |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Number of app settings added incrementally
- Size of individual app setting values (1 byte to 100KB)
- Key Vault reference format (valid vs. malformed)
- Slot-sticky vs. non-sticky settings

**Observed:**

- ARM API response codes when adding settings
- Environment variable values as seen by the running application
- Azure Activity Log entries on failed setting updates
- App Service error logs for Key Vault reference resolution failures

## 7. Instrumentation

- Python endpoint: `GET /env/{key}` returning `os.environ.get(key, "<NOT_SET>")`
- ARM/CLI: `az webapp config appsettings set` return code and error message
- Activity Log: ARM operation success/failure for `Microsoft.Web/sites/config/write`
- App Service Logs: Key Vault reference resolution events

**Key KQL query:**

```kusto
AzureActivity
| where ResourceProviderName == "MICROSOFT.WEB"
| where OperationName contains "config"
| where ActivityStatus == "Failed"
| project TimeGenerated, Caller, OperationName, Properties
| order by TimeGenerated desc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az group create --name rg-appsetting-limits --location koreacentral
az appservice plan create --name plan-appsetting --resource-group rg-appsetting-limits --sku B1 --is-linux
az webapp create --name app-appsetting-limits --resource-group rg-appsetting-limits --plan plan-appsetting --runtime "PYTHON:3.11"
```

### 8.2 Scenarios

**S1 — Count limit**: Add settings in batches of 50 using the ARM API until an error is returned. Document the exact limit and the error response.

**S2 — Value size limit**: Set a single setting to progressively larger values (1KB, 10KB, 50KB, 100KB). After each update, read the value back via the application endpoint. Document at what size the API rejects or truncates.

**S3 — Key Vault reference (valid)**: Create a Key Vault secret, grant the app's system-assigned managed identity `Key Vault Secrets User`. Set an app setting to `@Microsoft.KeyVault(VaultName=<name>;SecretName=<name>)`. Verify the app reads the resolved secret value.

**S4 — Key Vault reference (malformed)**: Set an app setting to a malformed reference (`@Microsoft.KeyVault(VaultName=nonexistent;SecretName=test)`). Verify whether the app sees the literal reference string or an empty value. Check App Service Logs for the error.

**S5 — Slot sticky settings**: Mark 20 settings as slot-sticky. Verify they count toward the same total limit.

## 9. Expected signal

- **S1**: ARM API returns HTTP 400 with a documented maximum count error around 1000 settings.
- **S2**: Values over a documented limit (likely 16KB or 32KB) are rejected with HTTP 400.
- **S3**: App reads the resolved secret value without seeing the reference syntax.
- **S4**: App reads the literal reference string; Activity Log shows Key Vault access failure.
- **S5**: Slot-sticky settings count toward the same total limit.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- ARM API limits may differ between the Azure Portal (which may apply its own client-side limits) and direct ARM calls.
- Key Vault reference resolution depends on network path — VNet-integrated apps with private endpoints have different resolution paths than public apps.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| App settings have a count limit | **Strongly Suggested** (documented in some Azure docs) |
| Malformed KV reference shows literal string | **Inferred** (consistent with observed support cases) |
| Value length limit exists | **Unknown** (not tested) |

## 14. Related experiments

- [Key Vault Reference Resolution](../zip-vs-container/overview.md) — Key Vault reference lifecycle
- [App Setting Precedence](../zip-vs-container/overview.md) — setting precedence and override order

## 15. References

- [App Service app settings documentation](https://learn.microsoft.com/en-us/azure/app-service/configure-common)
- [Key Vault references in App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references)

## 16. Support takeaway

When a customer reports app setting changes not taking effect:

1. Check Activity Log for failed ARM writes to the `config` resource.
2. Verify the total setting count — if approaching the limit, new settings may be silently rejected.
3. For Key Vault references, check App Service Logs for resolution failures. A malformed reference causes the app to read the literal reference string, not an empty value.
4. After updating settings via ARM, allow up to 30 seconds for the new values to propagate to the running worker process.
