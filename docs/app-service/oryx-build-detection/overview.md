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

# Oryx Build Detection Mismatch on Code Deploy

!!! info "Status: Planned"

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
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Configuration

**Controlled:**

- Zip deploy with `SCM_DO_BUILD_DURING_DEPLOYMENT=true`
- Repository containing both `requirements.txt` (Python) and `package.json` (Node.js)
- App Service configured as Python 3.11

**Observed:**

- Oryx-detected platform in build log
- Generated startup command
- App startup result (success or failure)

**Scenarios:**

- S1: Python-only repository → correct detection, app starts
- S2: Mixed Python + Node.js repository → observe Oryx detection choice
- S3: Set `ORYX_DISABLE_PLATFORM_DETECTION=true` and explicit startup command → verify override works
- S4: Set `ENABLE_ORYX_BUILD=false` and pre-build the app → verify no Oryx interference

## 7. Instrumentation

- Kudu console (`https://<app>.scm.azurewebsites.net`) → **Deployments** → deployment log for Oryx output
- App Service **Log Stream** for startup errors
- `AppServiceConsoleLogs` in Log Analytics

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create a Python Flask app with `requirements.txt`. Deploy; verify correct startup.
2. Add a `package.json` to the root of the project (simulate frontend tooling in a monorepo). Re-zip and deploy.
3. Check Oryx build log in Kudu — note detected platform and generated startup command.
4. If Node.js is selected: observe app startup failure (Flask app started with `node`).
5. S3: Add app setting `WEBSITE_STARTUP_COMMAND=gunicorn --bind=0.0.0.0:8000 app:app`; redeploy; verify Python app starts correctly.
6. S4: Set `SCM_DO_BUILD_DURING_DEPLOYMENT=false`; upload a pre-built zip; verify it runs without Oryx.

## 9. Expected signal

- S1: Oryx log shows `Detected Python`; app starts normally.
- S2: Oryx log shows `Detected Node.js` (wrong); startup command is `node server.js`; app returns 500 or fails to bind.
- S3: Explicit startup command overrides Oryx; app starts correctly.
- S4: No Oryx build log; pre-built package is extracted and run directly.

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

- Oryx platform detection priority and rules: https://github.com/microsoft/Oryx/tree/main/doc
- `SCM_DO_BUILD_DURING_DEPLOYMENT=true` is the default for code-based zip deploys on Linux; set to `false` to skip Oryx.
- The startup command can be set via `az webapp config set --startup-file` or the `WEBSITE_STARTUP_COMMAND` app setting.

## 16. Related guide / official docs

- [Oryx build system](https://github.com/microsoft/Oryx)
- [Configure a custom startup command for Linux containers](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python#customize-startup-command)
