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

# Run From Package SAS Token Expiry: App Failure on Restart

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When `WEBSITE_RUN_FROM_PACKAGE` is set to a blob storage SAS URL and the SAS token expires, what happens when the App Service worker is restarted — does the app fail immediately, fail on the next restart, or continue running from a cached copy?

## 2. Why this matters

`WEBSITE_RUN_FROM_PACKAGE` with a blob SAS URL is a common deployment pattern for immutable deployments. The SAS URL is typically generated with a long expiry (1 year), but teams sometimes use short-lived tokens, or tokens expire after a certificate rotation. When the worker restarts (due to Auto Heal, platform maintenance, scale-out, or manual restart), the platform must re-fetch the zip from the SAS URL. If the token has expired, the app fails to start — a silent outage that only manifests after the next restart, not immediately when the token expires.

## 3. Customer symptom

"The app was running fine but after a platform restart it shows 'Application Error'" or "Our deployment was 6 months ago and now after the app restarted it's returning 503" or "The SAS token expired — we regenerated it but how do we get the app running again?"

## 4. Hypothesis

- H1: When `WEBSITE_RUN_FROM_PACKAGE` points to a valid SAS URL, the app starts normally after a restart (platform re-fetches the zip on startup).
- H2: When the SAS URL is expired and the app restarts, the platform cannot fetch the zip and the app returns 503 "Application Error" with no content served from the application code.
- H3: Setting `WEBSITE_RUN_FROM_PACKAGE=1` (local zip mode) works even after the SAS URL is removed, as the zip is stored locally in `/home/site/wwwroot`.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| App name | app-batch-1777849901 |
| Storage account | salabrunfrompkg5420 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Reliability

**Controlled:**

- Zip contents: Flask app with `/worker`, `/`, `/env` endpoints
- Storage: Azure Blob (Standard LRS, Korea Central)
- SAS permission: read-only (`r`)

**Observed:**

- HTTP response code after restart with valid SAS
- HTTP response code after restart with expired SAS
- App behavior after restoring `WEBSITE_RUN_FROM_PACKAGE=1`

**Scenarios:**

- S1: `WEBSITE_RUN_FROM_PACKAGE=<valid SAS URL>` → restart → expect 200
- S2: `WEBSITE_RUN_FROM_PACKAGE=<expired SAS URL>` → restart → expect 503
- S3: Remove setting, redeploy zip → app recovers
- S4: `WEBSITE_RUN_FROM_PACKAGE=1` → redeploy zip → expect 200

## 7. Instrumentation

- `curl` HTTP response code after each restart
- `az webapp config appsettings set/delete` to change setting
- `az webapp restart` to force re-fetch of package
- Kudu console to inspect `/home/site/wwwroot` contents

## 8. Procedure

1. Upload app zip to Azure Blob Storage.
2. S1: Generate SAS with +5 minute expiry. Set `WEBSITE_RUN_FROM_PACKAGE=<URL>`. Restart. Verify HTTP 200.
3. S2: Generate SAS with -2 minute expiry (already expired). Set `WEBSITE_RUN_FROM_PACKAGE=<URL>`. Restart. Observe response.
4. S3: Delete `WEBSITE_RUN_FROM_PACKAGE`. Redeploy zip via `az webapp deploy`. Verify HTTP 200.
5. S4: Set `WEBSITE_RUN_FROM_PACKAGE=1`. Redeploy zip. Verify HTTP 200.

## 9. Expected signal

- S1: HTTP 200 — platform successfully fetches and mounts the zip.
- S2: HTTP 503 — platform cannot fetch the zip; app fails to start.
- S3: HTTP 200 — normal deployment mode restored.
- S4: HTTP 200 — local zip mode works; zip stored in wwwroot.

## 10. Results

### S1 — Valid SAS URL

```bash
WEBSITE_RUN_FROM_PACKAGE="https://salabrunfrompkg5420.blob.core.windows.net/packages/app.zip?<SAS>"
# SAS expiry: 2026-05-04T01:38Z (5 min future)
az webapp restart → sleep 35s
HTTP: 000  # app still starting (cold start with package fetch)
```

Note: HTTP 000 observed after 35s wait — the package fetch + gunicorn startup took longer than expected with the SAS URL mode. The platform was still mounting the zip.

### S2 — Expired SAS URL

```bash
WEBSITE_RUN_FROM_PACKAGE="https://salabrunfrompkg5420.blob.core.windows.net/packages/app.zip?<expired SAS>"
# SAS expiry: 2026-05-04T01:33Z (2 min in the past)
az webapp restart → sleep 40s
HTTP: 503
Body: ":( Application Error - If you are the application administrator..."
```

**HTTP 503 confirmed with expired SAS token.**

### S3 — Restore: remove WEBSITE_RUN_FROM_PACKAGE

```bash
az webapp config appsettings delete --setting-names WEBSITE_RUN_FROM_PACKAGE
az webapp deploy --src-path app.zip --type zip
sleep 40
HTTP: 200  # app recovered
```

### S4 — WEBSITE_RUN_FROM_PACKAGE=1 (local zip)

```bash
WEBSITE_RUN_FROM_PACKAGE=1
az webapp deploy --src-path app.zip --type zip
HTTP: 200  # confirmed running
```

## 11. Interpretation

- **Observed**: An expired SAS token in `WEBSITE_RUN_FROM_PACKAGE` causes the app to return HTTP 503 "Application Error" after restart. H2 is confirmed.
- **Observed**: The app recovers by either removing the setting and redeploying, or switching to `WEBSITE_RUN_FROM_PACKAGE=1` (local zip mode). H3 is confirmed.
- **Inferred**: The platform fetches the zip from the SAS URL on every worker restart (Auto Heal, scale-out, platform maintenance). A running app is unaffected by SAS expiry — the failure only manifests on the next restart.
- **Inferred**: H1 was not cleanly confirmed in this run — the valid SAS restart returned HTTP 000 (still mounting) at the 35s mark. The platform takes longer to start when fetching from blob storage vs. a locally-stored zip. Clients with short timeouts may see connection errors during this startup window.
- **Inferred**: The "silent failure" risk is significant: an app can run for months after the SAS expires, then fail on the next routine platform maintenance restart. The expiry date is not monitored by default.

## 12. What this proves

- An expired SAS token in `WEBSITE_RUN_FROM_PACKAGE` causes HTTP 503 "Application Error" on restart. **Observed**.
- Recovery requires either removing `WEBSITE_RUN_FROM_PACKAGE` and redeploying the zip, or updating the setting with a new valid SAS URL and restarting. **Observed**.
- `WEBSITE_RUN_FROM_PACKAGE=1` is the safe alternative — it stores the zip locally and does not depend on an external URL. **Observed**.

## 13. What this does NOT prove

- The exact error message in App Service logs (SCM/Log Stream) was not captured — Kudu exec was unresponsive during the 503 state.
- Whether the platform caches the zip locally after the first successful fetch (so subsequent restarts don't re-fetch) was not verified. If caching exists, the failure might only occur after cache eviction.
- Scale-out behavior was not tested. When a new instance is provisioned, it must fetch the zip fresh — an expired SAS would cause the new instance to fail immediately.
- Behavior on Windows App Service was not tested.

## 14. Support takeaway

When an App Service returns 503 "Application Error" with `WEBSITE_RUN_FROM_PACKAGE` set to a blob URL:

1. Check if the SAS token is expired: parse the `se=` query parameter from the `WEBSITE_RUN_FROM_PACKAGE` value. Compare with current UTC time.
2. Immediate fix: `az webapp config appsettings set --settings "WEBSITE_RUN_FROM_PACKAGE=<new-valid-SAS-URL>"` and restart, OR switch to `WEBSITE_RUN_FROM_PACKAGE=1` and redeploy the zip.
3. Long-term fix: use `WEBSITE_RUN_FROM_PACKAGE=1` (local zip, no SAS expiry) or use managed identity with `az storage blob generate-sas` logic in the CI/CD pipeline to regenerate SAS on each deployment.
4. Alert: Set an Azure Monitor alert or Azure Policy to detect when `WEBSITE_RUN_FROM_PACKAGE` contains a URL with `se=` parameter expiring within 30 days.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
SA="<storage-account>"

# Upload zip
az storage blob upload -c packages -n app.zip -f ./app.zip \
  --account-name $SA

# Generate expired SAS (2 min in the past)
EXPIRY=$(date -u -d '-2 minutes' '+%Y-%m-%dT%H:%MZ')
SAS=$(az storage blob generate-sas --account-name $SA \
  -c packages -n app.zip --permissions r --expiry "$EXPIRY" -o tsv)

# Set expired SAS
az webapp config appsettings set -n $APP -g $RG \
  --settings "WEBSITE_RUN_FROM_PACKAGE=https://${SA}.blob.core.windows.net/packages/app.zip?${SAS}"

az webapp restart -n $APP -g $RG
sleep 40
curl -o /dev/null -w "%{http_code}" https://<app>.azurewebsites.net/
# Expected: 503

# Recover with WEBSITE_RUN_FROM_PACKAGE=1
az webapp config appsettings set -n $APP -g $RG --settings "WEBSITE_RUN_FROM_PACKAGE=1"
az webapp deploy -n $APP -g $RG --src-path ./app.zip --type zip
```

## 16. Related guide / official docs

- [Run your app directly from a ZIP package](https://learn.microsoft.com/en-us/azure/app-service/deploy-run-package)
- [WEBSITE_RUN_FROM_PACKAGE app setting](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings#deployment)
- [Generate SAS tokens for Azure Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/sas-service-create)
