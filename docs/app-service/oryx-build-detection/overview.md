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

# Oryx Build Detection Mismatch on Code Deploy

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When deploying code to a Linux App Service using `az webapp deployment source config-zip` or GitHub Actions (without a pre-built artifact), Oryx detects the runtime and runs the build. Under what conditions does Oryx misdetect the runtime or choose wrong build parameters, causing the app to fail to start with no obvious error?

## 2. Why this matters

Oryx is the open-source build system used by App Service when `SCM_DO_BUILD_DURING_DEPLOYMENT=true`. Oryx infers the runtime and build command from project files. When multiple framework indicators exist (e.g., both `requirements.txt` and `package.json` in the same repo), Oryx may select the wrong runtime. This causes the deployment to succeed (build output looks normal) but the app fails to start because the wrong startup command is generated. The mismatch is subtle and not caught by the CI/CD pipeline.

## 3. Customer symptom

"Deployment succeeds in the pipeline but the app shows 'Application Error' and we can't find what changed" or "The startup command seems wrong — it's trying to run node but we deployed a Python app" or "Build worked locally but the zip deploy fails to start the app on Azure."

## 4. Hypothesis

- H1: When a Python repository also contains a `package.json` at the root (e.g., for frontend assets), Oryx detects both Python and Node.js indicators. The selection priority determines which runtime is used; if Node.js is selected for a Python app, the startup command is `node` instead of `gunicorn`, and the app fails to start.
- H2: Setting `ORYX_DISABLE_PLATFORM_DETECTION` or explicitly setting `WEBSITE_NODE_DEFAULT_VERSION` / runtime version app settings overrides Oryx detection and forces the correct runtime.
- H3: The Oryx build log (accessible via Kudu) clearly shows the detected platform and the generated startup command, providing the diagnostic signal needed to identify the mismatch.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| App name | app-batch-1777849901 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Deployment / Configuration

**Controlled:**

- Zip deploy with `SCM_DO_BUILD_DURING_DEPLOYMENT=true` (default for code deploys)
- App Service configured as Python 3.11
- Flask app with `app.py` and `requirements.txt`

**Observed:**

- HTTP response code when startup command is absent vs. present
- App startup result (success or failure)
- Oryx detection behavior when `appCommandLine` is cleared vs. set

**Scenarios:**

- S1: Python app with explicit gunicorn startup command → app starts, HTTP 200
- S2: Clear `appCommandLine` via REST API → Oryx auto-detection takes over → app fails
- S3: Restore explicit gunicorn startup command → app recovers

## 7. Instrumentation

- `az rest` PATCH to `config/web` to clear/set `appCommandLine`
- `curl` to measure HTTP response code
- Kudu console (`https://<app>.scm.azurewebsites.net`) for process list
- `az webapp restart` to force Oryx re-detection

## 8. Procedure

1. Baseline: Deploy Flask app (`app.py`, `requirements.txt`) with `appCommandLine = "gunicorn --bind=0.0.0.0:8000 --workers=4 --timeout 120 app:app"`. Confirm HTTP 200.
2. Clear `appCommandLine` via REST PATCH to `config/web` with `{"properties":{"appCommandLine":""}}`.
3. Restart app (`az webapp restart`). Wait 40 seconds.
4. Send HTTP request. Observe result.
5. Restore `appCommandLine` to gunicorn command. Restart. Verify recovery.

## 9. Expected signal

- S1: App returns HTTP 200; gunicorn workers active.
- S2: After clearing startup command, Oryx cannot bind app — HTTP 000 (connection refused).
- S3: After restoring startup command, app returns HTTP 200.

## 10. Results

### S1 — Baseline with explicit startup command

```
appCommandLine: gunicorn --bind=0.0.0.0:8000 --workers=4 --timeout 120 app:app
HTTP: 200
Response: {"bits":64,"machine":"x86_64","platform":"Linux-6.6.126.1-1.azl3-x86_64...","status":"ok"}
```

### S2 — Clear startup command (Oryx auto-detection)

```bash
$ az rest --method PATCH \
  --uri "https://management.azure.com/subscriptions/.../sites/app-batch-1777849901/config/web?api-version=2022-03-01" \
  --body '{"properties":{"appCommandLine":""}}'

# After restart (40s wait):
HTTP: 000  # connection refused — app not listening on any port
```

Note: `az webapp config set --startup-file ""` did NOT clear the value — the underlying `appCommandLine` remained set. Only the direct REST PATCH cleared it.

### S3 — Restore startup command

```bash
$ az rest --method PATCH \
  --uri ".../config/web?api-version=2022-03-01" \
  --body '{"properties":{"appCommandLine":"gunicorn --bind=0.0.0.0:8000 --workers=4 --timeout 120 app:app"}}'

# After restart (60s wait):
HTTP: 200
```

## 11. Interpretation

- **Observed**: Removing the explicit startup command causes the app to stop responding entirely (HTTP 000 / connection refused).
- **Inferred**: Without an explicit `appCommandLine`, Oryx auto-detection either selects no startup command or generates one that does not match the app's entry point. The app process starts but does not bind to port 8080 (the default App Service port).
- **Observed**: `az webapp config set --startup-file ""` does not reliably clear the `appCommandLine` value. The REST API `config/web` PATCH is the authoritative method.
- **Inferred**: H3 is partially confirmed — the failure is visible as a connection refusal, but the exact Oryx-generated command requires Kudu log inspection to confirm.

## 12. What this proves

- Clearing `appCommandLine` on a Python App Service running gunicorn causes immediate startup failure after restart. **Measured**.
- `az webapp config set --startup-file ""` is unreliable for clearing the startup command; REST PATCH to `config/web` is required. **Observed**.
- App recovery is deterministic: restoring `appCommandLine` and restarting recovers the app fully. **Measured**.

## 13. What this does NOT prove

- This experiment did not test the mixed `requirements.txt` + `package.json` multi-runtime detection scenario (Oryx selecting Node.js for a Python app). That scenario requires a fresh deploy with both files present during Oryx build, not a startup command change post-deploy.
- The exact Oryx-generated startup command when auto-detection runs was not captured. Kudu log inspection during a cold deploy would be required.
- Behavior on Free (F1) plan or Windows App Service was not tested.

## 14. Support takeaway

When a Python App Service stops responding after a configuration change:

1. Check `az rest GET .../config/web` for `appCommandLine` — if empty, Oryx startup command is absent.
2. `az webapp config set --startup-file` may not reliably clear or set `appCommandLine` — verify with REST GET after the call.
3. For Python apps, the explicit startup command (`gunicorn --bind=0.0.0.0:8000 --workers=4 --timeout 120 app:app`) must always be set if `SCM_DO_BUILD_DURING_DEPLOYMENT=true` and the app does not have a `Procfile`.
4. Use `az rest PATCH .../config/web` with `{"properties":{"appCommandLine":"..."}}` as the authoritative method to set or clear startup commands.

## 15. Reproduction notes

```bash
APP="<your-app-name>"
RG="<your-resource-group>"
SUB="<subscription-id>"

# Clear startup command
az rest --method PATCH \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/config/web?api-version=2022-03-01" \
  --body '{"properties":{"appCommandLine":""}}'

az webapp restart -n $APP -g $RG
sleep 45
curl -o /dev/null -w "%{http_code}" "https://${APP}.azurewebsites.net/"
# Expected: 000 (connection refused)

# Restore
az rest --method PATCH \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/config/web?api-version=2022-03-01" \
  --body '{"properties":{"appCommandLine":"gunicorn --bind=0.0.0.0:8000 --workers=4 --timeout 120 app:app"}}'

az webapp restart -n $APP -g $RG
sleep 60
curl -o /dev/null -w "%{http_code}" "https://${APP}.azurewebsites.net/"
# Expected: 200
```

- `SCM_DO_BUILD_DURING_DEPLOYMENT=true` is the default for code-based zip deploys on Linux; set to `false` to skip Oryx.
- The startup command can be set via `az webapp config set --startup-file` (unreliable for clearing) or REST PATCH to `config/web` (authoritative).
- Oryx platform detection priority and rules: https://github.com/microsoft/Oryx/tree/main/doc

## 16. Related guide / official docs

- [Oryx build system](https://github.com/microsoft/Oryx)
- [Configure a custom startup command for Linux containers](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python#customize-startup-command)
- [App Service config web REST API](https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/update-configuration)
