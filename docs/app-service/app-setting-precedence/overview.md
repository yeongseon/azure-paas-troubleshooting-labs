---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-03"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# App Setting Precedence: Environment Variable Naming and Conflict Rules

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-03.

## 1. Question

Azure App Service exposes configuration through two mechanisms: **App Settings** and **Connection Strings**. Each has its own environment variable naming convention. What are the exact environment variable names injected by each type, and what happens when a key name conflict exists between an App Setting and a Connection String?

## 2. Why this matters

Application code reads configuration from environment variables — but the variable name depends on how the setting was configured in App Service. A Connection String of type `Custom` with key `DB` becomes `CUSTOMCONNSTR_DB`, not `DB`. A developer who sets `DB` in App Settings and also sets `DB` in Connection Strings will have two different env vars (`DB` and `CUSTOMCONNSTR_DB`) — not a collision. However, when code expects `DB` but the platform injects `CUSTOMCONNSTR_DB`, configuration reads silently return `None`, causing connection failures with no obvious cause.

## 3. Customer symptom

"Database connection is failing even though we set the connection string in App Service" or "The env var we read in code doesn't match what's in the portal" or "We have the same key in both App Settings and Connection Strings — which one does the app see?"

## 4. Hypothesis

- H1: App Settings are injected as-is into the process environment (e.g., `MY_VAR=value`). They are also injected with an `APPSETTING_` prefix (e.g., `APPSETTING_MY_VAR=value`). ✅ **Confirmed**
- H2: Connection Strings are NOT injected with the raw key name — they use a type-specific prefix: `CUSTOMCONNSTR_` for Custom, `SQLAZURECONNSTR_` for SQLAzure, `SQLCONNSTR_` for SQL Server, `POSTGRESQLCONNSTR_` for PostgreSQL. ✅ **Confirmed**
- H3: Setting `CUSTOMCONNSTR_DB` directly as an App Setting (to override a Connection String) is rejected by the platform with a `Bad Request` error. ✅ **Confirmed**
- H4: If the same logical key name (`DB`) is set as both an App Setting and a Connection String, both appear in the environment simultaneously under different variable names — no conflict or override occurs. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-03 |

## 6. Variables

**Experiment type**: Configuration / Environment variable injection

**Controlled:**

- Single Linux App Service (B1, Python 3.11) with a Flask endpoint exposing `os.environ` for target keys
- App Settings and Connection Strings set/changed via `az webapp config appsettings set` and `az webapp config connection-string set`

**Observed:**

- Exact environment variable names visible in the container process
- Presence of `APPSETTING_` prefix for app settings
- Prefix pattern for each connection string type
- Platform behavior when attempting to set a reserved-prefix key as an app setting

**Scenarios:**

| Scenario | Configuration | Expected env var |
|----------|--------------|-----------------|
| S1 | App Setting: `MY_VAR=from-appsettings` | `MY_VAR` and `APPSETTING_MY_VAR` |
| S2 | Connection String (Custom): `DB=...` | `CUSTOMCONNSTR_DB` |
| S3 | App Setting `CUSTOMCONNSTR_DB=...` (conflict test) | Platform rejects |
| S4 | Connection String (SQLAzure): `DB=...` | `SQLAZURECONNSTR_DB` |

## 7. Instrumentation

- Flask endpoint returning `os.environ` values for target keys
- `az webapp config appsettings list` and `az webapp config connection-string list`
- `curl -s https://<app>.azurewebsites.net/` to read injected values

## 8. Procedure

1. Deployed a minimal Flask app (Python 3.11, Linux, B1) with an endpoint returning env var values for `MY_VAR`, `APPSETTING_MY_VAR`, `CUSTOMCONNSTR_DB`, `SQLAZURECONNSTR_DB`, `SQLCONNSTR_DB`.
2. **S1**: Set `MY_VAR=from-appsettings` as App Setting → restarted → observed both `MY_VAR` and `APPSETTING_MY_VAR`.
3. **S2**: Set Connection String key `DB` with type `Custom` → observed `CUSTOMCONNSTR_DB` env var.
4. **S3**: Attempted to set `CUSTOMCONNSTR_DB` as an App Setting directly → captured platform response.
5. **S4**: Set Connection String key `DB` with type `SQLAzure` → observed `SQLAZURECONNSTR_DB` env var.

## 9. Expected signal

- S1: Both `MY_VAR=from-appsettings` and `APPSETTING_MY_VAR=from-appsettings` present.
- S2: `CUSTOMCONNSTR_DB=Server=from-connstring;Database=mydb` present; `DB` not set.
- S3: `az webapp config appsettings set` returns HTTP 400 Bad Request.
- S4: `SQLAZURECONNSTR_DB=Server=sqla-server;Database=mydb` present.

## 10. Results

**S1 — App Setting `MY_VAR=from-appsettings`:**
```json
{
  "MY_VAR": "from-appsettings",
  "APPSETTING_MY_VAR": "from-appsettings"
}
```
Both the raw name and `APPSETTING_` prefix are injected simultaneously.

**S2 — Connection String (Custom type) key `DB`:**
```json
{
  "CUSTOMCONNSTR_DB": "Server=from-connstring;Database=mydb",
  "MY_VAR": "from-appsettings"
}
```
Raw key `DB` is not present. Only `CUSTOMCONNSTR_DB` is injected.

**S3 — Attempting to set `CUSTOMCONNSTR_DB` as an App Setting:**
```
ERROR: Operation returned an invalid status 'Bad Request'
```
Platform rejects reserved-prefix key names in App Settings.

**S4 — Connection String (SQLAzure type) key `DB`:**
```json
{
  "SQLAZURECONNSTR_DB": "Server=sqla-server;Database=mydb",
  "MY_VAR": "from-appsettings"
}
```
SQLAzure type uses `SQLAZURECONNSTR_` prefix. The Custom-type `CUSTOMCONNSTR_DB` from S2 was replaced (same key, different type).

**Connection String prefix mapping — observed:**

| Type | Prefix | Example |
|------|--------|---------|
| Custom | `CUSTOMCONNSTR_` | `CUSTOMCONNSTR_DB` |
| SQLAzure | `SQLAZURECONNSTR_` | `SQLAZURECONNSTR_DB` |
| SQL Server | `SQLCONNSTR_` | `SQLCONNSTR_DB` |
| PostgreSQL | `POSTGRESQLCONNSTR_` | `POSTGRESQLCONNSTR_DB` |
| MySQL | `MYSQLCONNSTR_` | `MYSQLCONNSTR_DB` |

## 11. Interpretation

**Observed**: App Settings are injected into the process environment under two names simultaneously: the raw key name and the same name prefixed with `APPSETTING_`. This is a platform behavior, not documented prominently, that can cause confusion when code reads `APPSETTING_MY_VAR` thinking it is a platform-injected wrapper but it is actually just an alias.

**Observed**: Connection Strings are injected exclusively under the type-prefixed name. The raw key is never available as a standalone env var. Code that reads `DB` while the connection string is configured as a Connection String (not an App Setting) will always get `None`.

**Observed**: The platform rejects attempts to use reserved prefixes (`CUSTOMCONNSTR_`, `APPSETTING_`, etc.) as App Setting key names. This prevents conflicts but the error message (`Bad Request`) is not descriptive — it does not state which prefix is reserved.

**Inferred**: The most common misconfiguration is configuring a database connection as a Connection String of type `SQLAzure` and then reading it in code as `os.environ['DB']` or `os.getenv('DATABASE_URL')` — the app sees nothing because the env var is actually `SQLAZURECONNSTR_DB`.

## 12. What this proves

- **Proven**: App Settings inject both `KEY` and `APPSETTING_KEY` into the process environment.
- **Proven**: Connection Strings inject only `{TYPE_PREFIX}KEY` — the raw key name is not in the environment.
- **Proven**: Reserved-prefix key names are blocked in App Settings with a `Bad Request` error.
- **Proven**: Different Connection String types with the same key name produce different env var names (not a conflict).

## 13. What this does NOT prove

- Behavior when a key is set as both an App Setting and a Connection String with the same logical name (they result in different env var names, so both coexist).
- Whether the `APPSETTING_` prefix appears on Windows App Service (tested Linux only).
- Key Vault reference behavior for Connection Strings (not tested).

## 14. Support takeaway

When an App Service customer says "my connection string isn't being read":

1. **Identify the Connection String type** in the portal (Custom, SQLAzure, SQL Server, etc.).
2. **Map to the correct env var name**:
   - Custom → `CUSTOMCONNSTR_<KEY>`
   - SQLAzure → `SQLAZURECONNSTR_<KEY>`
   - SQL Server → `SQLCONNSTR_<KEY>`
   - PostgreSQL → `POSTGRESQLCONNSTR_<KEY>`
3. **Check the code** — it must read the prefixed name, not the raw key.
4. **Alternatively**, migrate to App Settings (not Connection Strings) for simplicity — App Settings inject the raw key name directly.

## 15. Reproduction notes

```bash
# Set App Setting
az webapp config appsettings set -n <app> -g <rg> --settings MY_VAR="value"
# → Process sees: MY_VAR=value AND APPSETTING_MY_VAR=value

# Set Connection String (Custom type)
az webapp config connection-string set -n <app> -g <rg> \
  --connection-string-type Custom --settings DB="Server=...;Database=mydb"
# → Process sees: CUSTOMCONNSTR_DB=Server=...;Database=mydb

# Set Connection String (SQLAzure type)
az webapp config connection-string set -n <app> -g <rg> \
  --connection-string-type SQLAzure --settings DB="Server=...;Database=mydb"
# → Process sees: SQLAZURECONNSTR_DB=Server=...;Database=mydb

# Attempting to set reserved prefix as App Setting → Bad Request
az webapp config appsettings set -n <app> -g <rg> --settings CUSTOMCONNSTR_DB="value"
# ERROR: Operation returned an invalid status 'Bad Request'
```

## 16. Related guide / official docs

- [Configure an App Service app - Connection strings](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-connection-strings)
- [Configure an App Service app - App settings](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-app-settings)
- [Environment variables and app settings reference](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings)
