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

# Temp Storage Exhaustion from Build Artifacts and Logs

!!! info "Status: Planned"

## 1. Question

App Service Linux containers have limited local temp storage (the writable container layer and `/tmp`). Under what conditions do accumulated build artifacts, log files, or large temporary files exhaust the temp storage quota, and what is the visible failure mode when this happens?

## 2. Why this matters

When Oryx builds occur on the SCM site, build artifacts are written to local storage. When application logging is enabled to the filesystem, log files accumulate. When the application writes large temporary files, they consume the container's writable layer. Once the quota is exhausted, any operation that requires a filesystem write fails — including logging, session file creation, and application-level file operations. The failure manifests as seemingly random I/O errors in the application that are unrelated to the actual code logic.

## 3. Customer symptom

"The app randomly fails with 'No space left on device' errors" or "Logging suddenly stopped working and we see 'disk quota exceeded' in the console" or "The app worked fine for weeks and then started throwing file write errors without any code change."

## 4. Hypothesis

- H1: The local temp storage on App Service Linux (the `/tmp` directory and the container writable layer) has a quota (believed to be 500MB–2GB depending on SKU). When accumulated logs, build artifacts, or application temp files exceed this quota, subsequent writes fail with `ENOSPC` or `No space left on device`.
- H2: Oryx build artifacts accumulate in `/home/data/` across deployments if not cleaned up. Each deployment without explicit cleanup adds to the used space.
- H3: Application filesystem logging (`/home/LogFiles/`) is on persistent storage (`/home` is NFS-mounted Azure Files) and does not contribute to the container layer quota — but it is subject to the Azure Files storage limit of the App Service plan.
- H4: The `df -h` command (accessible via Kudu SSH console) shows the current storage usage and available space, providing a direct diagnostic signal.

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

**Experiment type**: Runtime / Storage

**Controlled:**

- App Service with Oryx build enabled
- Application that writes large files to `/tmp` on each request
- Repeated deployments without cleanup

**Observed:**

- `df -h` output at `/tmp` and `/` before and after file accumulation
- Application error messages when storage is full
- Recovery after manual cleanup via Kudu console

**Scenarios:**

- S1: Write 1GB to `/tmp` progressively; observe failure point
- S2: Run 10 Oryx builds without cleanup; measure artifact accumulation
- S3: Clean `/tmp` via Kudu SSH; verify app recovers without restart

## 7. Instrumentation

- Kudu SSH console: `df -h`, `du -sh /tmp/*`, `du -sh /home/*`
- App Service application logs for `ENOSPC` errors
- Azure Monitor metric: `FileSystemUsage` (if available for the SKU)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy a Python app with an endpoint `/fill?mb=<n>` that writes `n` MB to `/tmp/testfile`.
2. S1: Call `/fill?mb=100` repeatedly; after each call run `df -h /tmp` via Kudu; record the point where writes fail.
3. S2: Trigger 10 Oryx deployments (zip deploy with `SCM_DO_BUILD_DURING_DEPLOYMENT=true`); check `/home/data/SitePackages` and `/tmp/oryx-*` accumulation.
4. S3: Delete files via Kudu SSH; retry write operations; confirm recovery without app restart.

## 9. Expected signal

- S1: `ENOSPC` error returned by the app after quota is reached; `df -h` shows 100% usage on the relevant mount.
- S2: Artifact directory grows linearly with each deployment; after several builds, the quota is approached.
- S3: After cleanup, writes succeed; no restart required (process continues with same mounted filesystem).

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

- The `/home` mount is persistent Azure Files storage (shared across instances); `/tmp` and the container root filesystem are ephemeral and instance-local.
- SCM and app run in separate containers; Oryx build artifacts in SCM do not directly consume app container storage.
- Platform storage quotas vary by SKU. Use Kudu SSH to verify current limits.

## 16. Related guide / official docs

- [App Service file system](https://learn.microsoft.com/en-us/azure/app-service/operating-system-functionality#file-system)
- [Kudu SSH console](https://learn.microsoft.com/en-us/azure/app-service/resources-kudu)
