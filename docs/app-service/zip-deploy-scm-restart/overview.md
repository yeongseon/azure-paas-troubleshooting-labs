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

# ZIP Deploy Interrupted by App Restart

!!! info "Status: Planned"

## 1. Question

When an app restart occurs during an active ZIP deployment, does the deployment fail cleanly with a recoverable error, fail silently, or succeed? Does the deployment mode (extract vs. Run-From-Package) change the outcome?

## 2. Why this matters

ZIP Deploy routes through the Kudu/SCM endpoint and involves file extraction into wwwroot. If the app or the SCM process is restarted mid-deployment — due to a configuration change, manual restart, or scale event — the in-flight deployment may be interrupted without a clear failure signal at the CI/CD pipeline. Support engineers often see a failed pipeline with no obvious cause in application logs, or a partially deployed state that causes the app to behave inconsistently.

## 3. Customer symptom

"My CI/CD pipeline randomly fails with a deployment timeout or a broken connection" or "The app deployed but is missing files or using a mix of old and new code" or "The deployment log shows success but the app is not updated."

## 4. Hypothesis

- H1: If the app is restarted during an active ZIP deploy (extract mode), the deployment client receives a connection reset or HTTP 5xx error — not a structured Kudu error message.
- H2: In extract mode, an interrupted deployment may leave wwwroot in a partial state (some new files, some old files), detectable by comparing file hashes before and after.
- H3: In Run-From-Package mode, an interrupted deployment does not leave a partial wwwroot state; the package file itself either lands or does not, making the failure mode cleaner.
- H4: Kudu does not automatically retry a deployment interrupted by a restart; the pipeline must detect the failure via exit code or deployment history API and retry explicitly.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B2 (Basic) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Reliability / Failure injection

**Controlled:**

- ZIP package size: small (~1 MB) and large (~50 MB)
- Deployment mode: extract (default) vs. Run-From-Package (`WEBSITE_RUN_FROM_PACKAGE=1`)
- Restart trigger: `az webapp restart` timed 3–5 seconds into deployment start

**Observed:**

- HTTP status returned to the deployment client (`az webapp deploy` exit code and stderr)
- Kudu deployment history entry (`GET /api/deployments`) — present, absent, or incomplete
- wwwroot file state after interruption (extract mode only) — partial, clean old, clean new
- Time-to-failure detection at the client

**Independent run definition**: One deployment attempt paired with one timed restart trigger.

**Planned runs per configuration**: 5 per (mode × size) combination

**Warm-up exclusion rule**: Allow Kudu to reach healthy state before each test run.

**Primary metric**: Deployment failure rate under restart condition vs. baseline (no restart). Meaningful effect: ≥50% failure rate under restart condition.

**Comparison method**: Success/failure count; failure mode categorization (HTTP error, timeout, partial wwwroot, silent success).

## 7. Instrumentation

- `az webapp deploy` exit code and stderr — client-side failure signal
- Kudu REST API: `GET /api/deployments` — deployment history and per-entry status
- Kudu logstream: `GET /api/logstream` — real-time SCM log during deployment
- wwwroot file inventory via Kudu VFS API (`GET /api/vfs/site/wwwroot/`) — pre- and post-deployment snapshot
- File hash comparison: `sha256sum` of selected representative files
- App Service Activity Log — app restart events and timing

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy baseline ZIP (extract mode, small package); verify clean wwwroot and successful Kudu history entry.
2. Begin deployment of large ZIP (extract mode); trigger `az webapp restart` 3–5 seconds after deployment starts.
3. Capture client exit code, stderr, and Kudu history entry.
4. Inspect wwwroot via Kudu VFS API; compare file hashes with expected new-version contents.
5. Repeat with small ZIP (may complete before restart lands).
6. Switch to Run-From-Package mode; repeat steps 2–4.
7. Aggregate failure mode counts across 5 runs per configuration.

## 9. Expected signal

- Large ZIP (extract mode): connection reset or HTTP 5xx at client; partial wwwroot state possible; Kudu history entry absent or incomplete.
- Small ZIP (extract mode): deployment may complete before restart; failure rate lower.
- Run-From-Package: no partial wwwroot; failure is binary (package present or not); client error still likely if restart interrupts upload.
- All modes: Kudu does not auto-retry; pipeline must re-run.

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

- Timing sensitivity is high: the restart must land during Kudu's file extraction phase, not before upload completes. Use a large ZIP to widen the window.
- Always inspect Kudu deployment history (`/api/deployments`) rather than relying solely on CLI exit codes — a 0 exit code does not guarantee wwwroot integrity.
- Run-From-Package mode makes the failure mode cleaner but does not prevent the deployment from being interrupted; it just prevents partial file states.
- In extract mode, verify wwwroot with file hashes, not just file count — new files may be added while old files are not yet removed.

## 16. Related guide / official docs

- [Deploy files to App Service (ZIP deploy)](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [Run your app directly from a ZIP package](https://learn.microsoft.com/en-us/azure/app-service/deploy-run-package)
- [Kudu REST API — deployment history](https://github.com/projectkudu/kudu/wiki/REST-API#deployment)
