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

# App Setting Precedence: Environment Variable Override Conflicts

!!! info "Status: Planned"

## 1. Question

App Service injects app settings and connection strings as environment variables. When the same variable name is set at multiple levels (Dockerfile ENV, container entrypoint, application code default, slot override, Azure app setting), which value wins, and are there cases where the platform-injected value is unexpectedly overridden by the container?

## 2. Why this matters

Apps frequently use multi-layer configuration: defaults in code, overrides in a Dockerfile, and cloud-specific values in App Service app settings. When an app setting name collides with a Dockerfile ENV, the resolution depends on how the container is started. Developers who test locally with Docker see Dockerfile defaults, but production runs with the App Service-injected values overriding them. When the naming is inconsistent, or when a Dockerfile ENV is set to a hard-coded value the developer forgot, production may silently use the wrong configuration, causing environment-specific bugs that are hard to reproduce locally.

## 3. Customer symptom

"The app is using the wrong database URL even though we set the app setting correctly" or "The environment variable is correct in the portal but the app reads a different value" or "Configuration works in staging but the app setting seems ignored in production."

## 4. Hypothesis

- H1: App Service injects app settings as environment variables at container startup, after the Dockerfile CMD/ENTRYPOINT is called. If a Dockerfile `ENV` instruction sets the same variable, the App Service injection overrides it — the App Service value wins.
- H2: When a custom entrypoint script (`startup.sh`) exports a variable before launching the application, that export may override the App Service-injected value if the script runs as a child process that doesn't inherit the parent environment correctly.
- H3: Slot-sticky app settings are applied per-slot. When an app is swapped, the sticky settings remain with the slot. If the same variable is in both sticky (slot A) and non-sticky (slot B) app settings with different values, the post-swap value depends on which slot the code is now on.
- H4: `WEBSITE_*` and `APPSETTING_*` prefixed variables are automatically added by App Service in addition to the bare variable name. An app reading `APPSETTING_MY_VAR` will get the App Service value; an app reading `MY_VAR` should also get the same value (for app settings, not connection strings).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Custom container (Python 3.11 + custom Dockerfile) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Deployment

**Controlled:**

- Dockerfile with `ENV MY_VAR=dockerfile-value`
- App Service app setting `MY_VAR=appservice-value`
- Startup script that exports `MY_VAR=script-value`

**Observed:**

- Which value the application reads for `MY_VAR` under each configuration
- Precedence order

**Scenarios:**

- S1: Dockerfile ENV only (no app setting) → Dockerfile value
- S2: Dockerfile ENV + App Service app setting → which wins?
- S3: App setting + startup script export → which wins?
- S4: Sticky vs non-sticky app setting after slot swap

## 7. Instrumentation

- App `/env` endpoint printing `os.environ` dict
- Kudu SSH: `env | grep MY_VAR`
- Portal app settings blade to verify injected values

## 8. Procedure

_To be defined during execution._

### Sketch

1. Build a container image with `ENV MY_VAR=dockerfile-value`; deploy without App Service app setting; verify app reads `dockerfile-value`.
2. S2: Add App Service app setting `MY_VAR=appservice-value`; restart; verify which value is read.
3. S3: Modify startup command to `export MY_VAR=script-value && python app.py`; restart; check which value wins.
4. S4: Create two slots; set `MY_VAR` as non-sticky in production (value A) and sticky in staging (value B); swap; verify values post-swap.

## 9. Expected signal

- S1: App reads `dockerfile-value`; Kudu `env` shows `MY_VAR=dockerfile-value`.
- S2: App reads `appservice-value` (App Service injection overrides Dockerfile ENV).
- S3: Depends on whether the startup script is executed as a new shell (inherits App Service env and then overrides) or via `exec` (env not changed).
- S4: Non-sticky `MY_VAR` swaps with the slot (production gets staging's value); sticky `MY_VAR` stays with its slot.

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

- App Service injects app settings before the container's CMD is executed. Dockerfile ENV values are baked into the image and are overridden by the platform injection.
- Connection strings are injected with type-specific prefixes: `SQLCONNSTR_`, `MYSQLCONNSTR_`, `SQLAZURECONNSTR_`, `CUSTOMCONNSTR_`. The bare connection string name is also available.
- Use `printenv` or `os.environ` at startup to log all environment variables for debugging.

## 16. Related guide / official docs

- [App settings and connection strings in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-app-settings)
- [Environment variables for custom containers](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container#configure-environment-variables)
