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

# WEBSITE_RUN_FROM_PACKAGE SAS Token Expiry

!!! info "Status: Planned"

## 1. Question

When `WEBSITE_RUN_FROM_PACKAGE` is set to a Blob Storage SAS URL and the SAS token expires, what exactly happens to the running application, and when does the failure surface — immediately on expiry, on the next restart, or on the next scale-out to a new instance?

## 2. Why this matters

Run-from-package with a SAS URL is a common pattern for large deployments and CI/CD pipelines. When the SAS token expires, the application continues to run on existing instances (the package is already mounted), but new instances created during scale-out fail to mount the package and become unavailable. This creates a split-brain scenario: existing instances serve traffic normally while new instances are stuck in a crash loop, causing intermittent failures proportional to the traffic load on broken instances.

## 3. Customer symptom

"Application started returning 503 errors intermittently after a scale-out event" or "Some instances are healthy but others fail — we haven't deployed anything" or "After a planned restart, the app won't start and we see 'failed to mount package' errors."

## 4. Hypothesis

- H1: When the SAS token expires, existing running instances are unaffected — the package is already memory-mapped and does not require re-authentication on each request.
- H2: When a new instance is created (scale-out or platform replacement), the platform attempts to download and mount the package using the SAS URL. If the SAS has expired, the download fails and the instance enters a crash loop, returning 503 for its share of traffic.
- H3: A manual restart or redeploy triggers a fresh package mount on all instances. If the SAS has expired, all instances fail simultaneously — a total outage.
- H4: The failure is visible in App Service application logs as a startup error referencing the package URL, and in `AppServiceAppLogs` with a storage access error.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Reliability

**Controlled:**

- App Service with `WEBSITE_RUN_FROM_PACKAGE` set to a Blob SAS URL with a short expiry (5 minutes for testing)
- App Service Plan with manual scale-out capability

**Observed:**

- Application availability on existing instances after SAS expiry
- Instance startup behavior after SAS expiry (scale-out and restart)
- Error messages in application and platform logs

**Scenarios:**

- S1: SAS expires while app is running, no restart — observe continued availability
- S2: Scale out after SAS expiry — observe new instance startup failure
- S3: Manual restart after SAS expiry — observe total outage
- S4: Replace SAS URL with new valid token via `az webapp config appsettings set` — verify recovery

## 7. Instrumentation

- App Service **Diagnose and Solve Problems** → Application Crashes
- `AppServiceAppLogs` in Log Analytics for startup errors
- Instance health check responses during scale-out
- Azure Storage access logs to confirm 403 responses on SAS expiry

## 8. Procedure

_To be defined during execution._

### Sketch

1. Upload app package to Blob Storage; generate SAS URL with 5-minute expiry.
2. Set `WEBSITE_RUN_FROM_PACKAGE` to the SAS URL; restart app; verify it starts correctly.
3. S1: Wait 6 minutes (past SAS expiry); make requests; verify existing instances still respond correctly.
4. S2: Scale out from 1 to 2 instances; observe the new instance's startup behavior; verify 503s on requests hitting the new instance.
5. S3: Restart all instances; observe total outage.
6. S4: Update `WEBSITE_RUN_FROM_PACKAGE` with a new SAS URL with 1-hour expiry; restart; verify recovery.

## 9. Expected signal

- S1: Existing instances serve requests normally despite expired SAS.
- S2: New instance logs show package download failure; health check fails; 503 returned for traffic routed to that instance.
- S3: All instances fail to start; app returns 503/502 universally.
- S4: After SAS update and restart, all instances start successfully.

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

- Generate a short-lived SAS with `az storage blob generate-sas --expiry $(date -u -d '+5 minutes' +%Y-%m-%dT%H:%MZ)`.
- `WEBSITE_RUN_FROM_PACKAGE=1` (numeric 1) causes the platform to use a local zip in `/home/data/SitePackages/` instead of a URL — different failure mode.
- Consider using Managed Identity with `WEBSITE_RUN_FROM_PACKAGE` pointing to the blob URL without SAS, relying on identity-based access — avoids SAS expiry entirely.

## 16. Related guide / official docs

- [Run your app in Azure App Service directly from a ZIP package](https://learn.microsoft.com/en-us/azure/app-service/deploy-run-package)
- [WEBSITE_RUN_FROM_PACKAGE app setting](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings#deployment-preferences)
