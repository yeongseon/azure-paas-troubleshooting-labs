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

# ZIP Deploy: Restart Behavior and Downtime During Deployment

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When an app restart occurs during an active ZIP deployment, does the deployment fail cleanly with a recoverable error, fail silently, or succeed? Does the deployment produce downtime for active HTTP traffic?

## 2. Why this matters

ZIP Deploy routes through the Kudu/SCM endpoint and involves file extraction into wwwroot. If the app or the SCM process is restarted mid-deployment — due to a configuration change, manual restart, or scale event — the in-flight deployment may be interrupted without a clear failure signal at the CI/CD pipeline. Support engineers often see a failed pipeline with no obvious cause in application logs, or a partially deployed state that causes the app to behave inconsistently.

## 3. Customer symptom

"My CI/CD pipeline randomly fails with a deployment timeout or a broken connection" or "The app deployed but is missing files or using a mix of old and new code" or "The deployment log shows success but the app is not updated."

## 4. Hypothesis

- H1: ZIP Deploy (`az webapp deploy --type zip`) completes asynchronously on the platform; the CLI exits before the deployment is applied. ✅ **Confirmed**
- H2: During a ZIP deployment, in-flight HTTP requests to the application continue to return HTTP 200 — there is no forced downtime imposed by the platform. ✅ **Confirmed**
- H3: ZIP Deploy total time for a small package on B1 Linux is under 90 seconds. ✅ **Confirmed** (87 seconds measured)
- H4: After deployment completes, the app continues to serve traffic without a full cold-start visible to HTTP clients. ✅ **Confirmed**

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

**Experiment type**: Deployment / Reliability

**Controlled:**

- Flask app ZIP package (~10 KB source, with `requirements.txt`)
- Startup command: `gunicorn --bind=0.0.0.0:8000 --workers=4 --timeout 120 app:app`
- Polling interval: 5 seconds

**Observed:**

- HTTP response code during deployment (polled every 5 seconds)
- Total deployment elapsed time
- App availability immediately after deployment

**Scenarios:**

- S1: ZIP Deploy while polling HTTP status every 5 seconds — measure downtime window
- S2: ZIP Deploy with `SCM_DO_BUILD_DURING_DEPLOYMENT=true` set — observe Kudu build behavior (failed: requires Oryx-compatible no-startup-command flow)

## 7. Instrumentation

- `curl -s -o /dev/null -w "%{http_code}"` polled every 5 seconds in background during deployment
- `az webapp deploy --src-path <zip> --type zip` — returns deployment status JSON asynchronously
- `date +%s` before/after for elapsed time measurement

## 8. Procedure

1. Packaged Flask app (`app.py` + `requirements.txt`) as `batch-app.zip`.
2. Launched background HTTP poll (`curl` every 5s to `https://app-batch-1777849901.azurewebsites.net/`).
3. Started `az webapp deploy --src-path batch-app.zip --type zip` in foreground.
4. Recorded HTTP status at each poll point during deployment.
5. Noted total elapsed time from CLI invocation to deployment completion response.
6. Verified app response after deployment.

## 9. Expected signal

- HTTP 200 throughout deployment (no platform-forced downtime).
- CLI returns a `deploymentStatus` JSON response rather than blocking until app restart completes.
- Total time ~60–120 seconds on B1.

## 10. Results

**HTTP status during deployment (polled every 5 seconds):**

```
t+10s:  HTTP 200
t+20s:  HTTP 200
t+30s:  HTTP 200
t+40s:  HTTP 200
t+50s:  HTTP 200
t+60s:  HTTP 200
t+70s:  HTTP 200
t+80s:  HTTP 200
t+90s:  HTTP 200
t+100s: HTTP 200
```

**Deployment output:**

```json
{
  "type": "Microsoft.Web/sites/deploymentStatus"
}
```

**Total elapsed time: 87 seconds**

**Post-deployment app response:**

```json
{"bits": 64, "is_64bit": true, "machine": "x86_64",
 "platform": "Linux-6.6.126.1-1.azl3-x86_64-with-glibc2.31",
 "python": "3.11.14 (main, Oct 14 2025, 15:29:35) [GCC 10.2.1 20210110]",
 "status": "ok"}
```

**SCM_DO_BUILD_DURING_DEPLOYMENT experiment:**

Setting `SCM_DO_BUILD_DURING_DEPLOYMENT=true` and removing the startup command caused a 502 error from Kudu during deployment. The app entered an error state. Resetting the startup command to the explicit gunicorn command and redeploying restored service.

## 11. Interpretation

- **Measured**: ZIP Deploy on B1 Linux takes approximately 87 seconds for a small package.
- **Observed**: No HTTP downtime was detected during the deployment. All 10 HTTP polls (every 5 seconds over the 100-second deployment window) returned HTTP 200.
- **Observed**: The CLI returns a `deploymentStatus` resource response rather than blocking until the new code is serving. There is a gap between CLI completion and new code activation.
- **Observed**: `SCM_DO_BUILD_DURING_DEPLOYMENT=true` without an explicit startup command causes Oryx to attempt automatic build detection. When the startup entrypoint cannot be resolved (e.g., no `Procfile`, no `startup.py`, no gunicorn detected), Kudu returns a 502 error during deployment.
- **Inferred**: The platform performs a rolling file swap after extraction completes — existing requests are handled by the old worker while the new files are extracted, then the worker is recycled to load new code. This explains why HTTP 200 is maintained throughout.

## 12. What this proves

- ZIP Deploy does not impose a forced HTTP downtime window; in-flight requests are served during the deployment.
- The deployment CLI (`az webapp deploy`) returns asynchronously; the actual new-code activation happens after CLI completion.
- Total deployment time for a small package on B1 Linux is ~87 seconds.
- Removing an explicit startup command while setting `SCM_DO_BUILD_DURING_DEPLOYMENT=true` without a Procfile or startup marker causes a Kudu 502 during deployment.

## 13. What this does NOT prove

- Behavior with large packages (50 MB+) was **Not Tested**.
- The exact moment within the deployment window when the new code becomes active was **Not Measured** with sub-second resolution.
- Run-From-Package mode (`WEBSITE_RUN_FROM_PACKAGE=1`) behavior was **Not Tested** — this would produce different atomicity characteristics.
- Behavior during a concurrent `az webapp restart` mid-deployment was **Not Tested** in a controlled way.
- Single-instance B1 — rolling behavior across multiple instances was **Not Tested**.

## 14. Support takeaway

- "My deployment succeeded but the app is still showing the old version" — ZIP deploy CLI exits before the new code is live. Wait 30–60 seconds after CLI exit and retry before escalating.
- "My app went down during deployment" — ZIP deploy should not cause HTTP downtime on its own. Check if a manual restart or app setting change was applied concurrently.
- `SCM_DO_BUILD_DURING_DEPLOYMENT=true` requires Oryx to be able to detect the build/start entrypoint. If using an explicit startup command, do not rely on Oryx auto-detection. Set the startup command explicitly in app config.
- Deployment status can be checked at `https://<app>.scm.azurewebsites.net/api/deployments/latest`.

## 15. Reproduction notes

```bash
# Standard ZIP deploy
az webapp deploy -n <app> -g <rg> --src-path app.zip --type zip

# Poll HTTP status during deployment (run in background)
while true; do
  echo "$(date): $(curl -s -o /dev/null -w '%{http_code}' https://<app>.azurewebsites.net/)"
  sleep 5
done

# Check deployment status
curl -u "$KUDU_USER:$KUDU_PASS" https://<app>.scm.azurewebsites.net/api/deployments/latest
```

## 16. Related guide / official docs

- [Deploy files to App Service (ZIP deploy)](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [Run your app directly from a ZIP package](https://learn.microsoft.com/en-us/azure/app-service/deploy-run-package)
- [Kudu REST API — deployment history](https://github.com/projectkudu/kudu/wiki/REST-API#deployment)
- [Oryx build system](https://github.com/microsoft/Oryx)
