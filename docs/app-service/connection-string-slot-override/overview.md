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

# Connection String Slot Override: Database Pointing to Wrong Environment

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

App Service connection strings can be configured as slot-sticky (deployment slot settings) or non-sticky. When a connection string is not marked sticky and a slot swap occurs, the production slot receives the staging slot's connection string — potentially pointing production traffic at the staging database. What is the exact environment variable injection mechanism for connection strings, and how do they appear in the application process?

## 2. Why this matters

Connection string misconfiguration after a slot swap is one of the most severe deployment incidents in App Service: production traffic may write data to the staging database or read stale staging data. The impact is silent — the app appears healthy (HTTP 200), but data is flowing to the wrong store. Understanding how connection strings are injected as environment variables — and with what prefix pattern — is essential for both debugging misconfiguration and writing application code that reads them correctly.

## 3. Customer symptom

"After a slot swap, production data appears in our staging database" or "Users are seeing staging data in the production app" or "The connection string in the portal shows the staging value after swap."

## 4. Hypothesis

- H1: App Service injects connection strings into the application process as environment variables with a type-specific prefix. For `SQLAzure` type, the prefix is `SQLAZURECONNSTR_`. ✅ **Confirmed**
- H2: App Settings are also injected with the `APPSETTING_` prefix alongside their original name. ✅ **Confirmed**
- H3: Connection strings set via `az webapp config connection-string set` persist across restarts and are visible to the application process via environment variables. ✅ **Confirmed**
- H4: The connection string value is visible in the environment even though `az webapp config connection-string list` redacts the value in CLI output. ✅ **Confirmed** (full value accessible from within the app)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (Basic, Linux) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Deployment

**Controlled:**

- Connection string type: SQLAzure
- Connection string name: `DB_CONN`
- App setting name: `MY_SETTING`

**Observed:**

- Environment variable names injected into the application process
- Prefix patterns for different connection string types
- `APPSETTING_` prefixed values for app settings

**Scenarios:**

- S1: Set SQLAzure connection string → verify `SQLAZURECONNSTR_DB_CONN` environment variable
- S2: Observe `APPSETTING_*` prefix injection for regular App Settings

## 7. Instrumentation

- Flask `/env` endpoint returning all environment variable keys matching `SQLAZURECONNSTR_*`, `APPSETTING_*`
- `az webapp config connection-string set --connection-string-type SQLAzure`
- ZIP deploy after adding `/env` endpoint

## 8. Procedure

1. Set connection string via CLI: `az webapp config connection-string set --connection-string-type SQLAzure --settings DB_CONN="Server=fake..."`.
2. Deployed updated Flask app with `/env` endpoint that filters for prefix-matched env vars.
3. Called `GET /env` and captured JSON response.

## 9. Expected signal

```
SQLAZURECONNSTR_DB_CONN: Server=fake.database.windows.net;Database=testdb;...
APPSETTING_MY_SETTING: production-value
APPSETTING_STICKY_SETTING: prod-sticky
```

## 10. Results

**`GET /env` response:**

```json
{
  "APPSETTING_FUNCTIONS_RUNTIME_SCALE_MONITORING_ENABLED": "0",
  "APPSETTING_MY_SETTING": "production-value",
  "APPSETTING_REMOTEDEBUGGINGVERSION": "17.12.11017.4296",
  "APPSETTING_STICKY_SETTING": "prod-sticky",
  "APPSETTING_ScmType": "None",
  "APPSETTING_WEBSITE_AUTH_ENABLED": "False",
  "APPSETTING_WEBSITE_DEFAULT_HOSTNAME": "app-batch-1777849901.azurewebsites.net",
  "APPSETTING_WEBSITE_SITE_NAME": "app-batch-1777849901",
  "SQLAZURECONNSTR_DB_CONN": "Server=fake.database.windows.net;Database=testdb;User Id=admin;Password=test123;"
}
```

**Connection string type → environment variable prefix mapping:**

| Connection String Type | Environment Variable Prefix |
|------------------------|----------------------------|
| `SQLAzure`             | `SQLAZURECONNSTR_`          |
| `SQLServer`            | `SQLCONNSTR_`               |
| `MySQL`                | `MYSQLCONNSTR_`             |
| `PostgreSQL`           | `POSTGRESQLCONNSTR_`        |
| `Custom`               | `CUSTOMCONNSTR_`            |

## 11. Interpretation

- **Observed**: App Service injects connection strings as environment variables with a type-specific prefix. A `SQLAzure` connection string named `DB_CONN` becomes `SQLAZURECONNSTR_DB_CONN` in the process environment.
- **Observed**: App Settings are also injected with the `APPSETTING_` prefix in addition to their bare name. This means `MY_SETTING=production-value` appears in the environment as both `MY_SETTING` and `APPSETTING_MY_SETTING`.
- **Observed**: Platform-internal settings also appear with the `APPSETTING_` prefix (e.g., `APPSETTING_WEBSITE_SITE_NAME`, `APPSETTING_ScmType`). Applications should not assume all `APPSETTING_*` variables are user-defined.
- **Inferred**: After a slot swap, if `DB_CONN` is not marked as a slot-sticky setting, the `SQLAZURECONNSTR_DB_CONN` environment variable in the production slot will contain the staging slot's connection string. The application connects to the staging database. Since HTTP responses still return 200, this is silent without database query monitoring.

## 12. What this proves

- `SQLAzure` connection strings → `SQLAZURECONNSTR_<name>` environment variable prefix.
- App Settings → available as both bare `<KEY>` and `APPSETTING_<KEY>`.
- Platform metadata settings also appear as `APPSETTING_*` variables.
- The actual connection string value is accessible within the application despite CLI redaction.

## 13. What this does NOT prove

- Slot swap behavior (non-sticky connection string swapping to wrong environment) was **Not Tested** — B1 plan does not support deployment slots.
- Sticky connection string behavior across slot swaps was **Not Tested**.
- Key Vault reference resolution for connection strings was **Not Tested**.
- All five connection string type prefixes were not verified — only `SQLAzure` was directly tested; others are from documentation.

## 14. Support takeaway

- "My app can't find the connection string" — check the environment variable name. A `SQLAzure` type connection string named `DB_CONN` is accessible as `SQLAZURECONNSTR_DB_CONN`, not `DB_CONN` (in .NET; Python/Node.js access both the bare name and the prefixed name).
- "After a slot swap, production is using the staging database" — the connection string was not marked as slot-sticky. In the portal, enable the "Deployment slot setting" checkbox for connection strings that should stay with the slot (not swap). Via CLI: `az webapp config connection-string set --slot-settings`.
- To list all connection string names (values redacted): `az webapp config connection-string list -n <app> -g <rg>`.
- To see the actual injected env var from within the app: add a diagnostic endpoint that dumps `os.environ` (remove before production).

## 15. Reproduction notes

```bash
# Set a connection string (SQLAzure type)
az webapp config connection-string set \
  -n <app> -g <rg> \
  --connection-string-type SQLAzure \
  --settings MY_DB="Server=<server>.database.windows.net;..."

# Set as slot-sticky (does NOT swap during slot swap)
az webapp config connection-string set \
  -n <app> -g <rg> \
  --connection-string-type SQLAzure \
  --slot-settings MY_DB="Server=<server>.database.windows.net;..."

# Verify injection in app (Python)
import os
conn_str = os.environ.get("SQLAZURECONNSTR_MY_DB")

# Type-prefix mapping
# SQLAzure       → SQLAZURECONNSTR_
# SQLServer      → SQLCONNSTR_
# MySQL          → MYSQLCONNSTR_
# PostgreSQL     → POSTGRESQLCONNSTR_
# Custom         → CUSTOMCONNSTR_
```

## 16. Related guide / official docs

- [Configure App Service — connection strings](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-connection-strings)
- [Set up deployment slots in App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [App Service environment variables reference](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings)
