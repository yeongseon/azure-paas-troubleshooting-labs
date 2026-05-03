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

# Volume Mount Read-Only Mode: Application Write Failures on Azure Files Mount

!!! info "Status: Planned"

## 1. Question

When an Azure Files volume is mounted to a Container Apps container with read-only mode (`readOnly: true`), what is the exact error message when the application attempts to write to the mount? And conversely, when read-write mode is intended but the mount is inadvertently set to read-only (e.g., due to a Bicep default or misconfiguration), is the error detectable at deployment time or only at runtime?

## 2. Why this matters

Azure Files volumes in Container Apps can be mounted as read-only or read-write. The `readOnly` flag in the Bicep/ARM template defaults to `false` (read-write), but misconfigurations or explicit `readOnly: true` settings for security hardening can cause application write failures that are not apparent until the application attempts to write (e.g., first log write, file upload, cache write). The error occurs at runtime, not at deployment time, making it harder to catch in CI/CD pipelines.

## 3. Customer symptom

"The app deploys successfully but crashes on first file write with 'Read-only file system' error" or "File upload endpoint returns 500 — the mounted path is read-only" or "We set up Azure Files for shared storage but writes fail silently."

## 4. Hypothesis

- H1: When `readOnly: true` is set on a volume mount, any write operation to the mount path returns a Linux `EROFS (Read-only file system)` error. In Python, this surfaces as `OSError: [Errno 30] Read-only file system: '/mnt/data/file.txt'`.
- H2: The read-only vs. read-write setting is a deployment-time configuration and is NOT validated against application behavior — the container starts successfully and the error only occurs when a write is attempted.
- H3: The mount path itself is visible in the container filesystem (`ls /mnt/data` works), making the misconfiguration hard to detect without attempting a write.
- H4: Changing `readOnly` from `true` to `false` and redeploying (which creates a new revision) immediately resolves the issue — existing data on the Azure Files share is unaffected.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Storage / Configuration

**Controlled:**

- Azure Files share mounted to Container Apps
- `readOnly` flag: `true` vs. `false`
- Python app with file write endpoint

**Observed:**

- Error message and HTTP status code when write is attempted on read-only mount
- Visibility of the mount path in the container filesystem
- Application behavior on read operations from the same mount

**Scenarios:**

- S1: `readOnly: true` → write attempt → error
- S2: `readOnly: false` → write attempt → success
- S3: `readOnly: true` → read attempt → success (mount is readable)

## 7. Instrumentation

- Application logs (`ContainerAppConsoleLogs`) for `OSError` or `EROFS` messages
- HTTP endpoint returning error detail for write operations
- `kubectl exec` equivalent via Azure CLI or container console for interactive testing

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create Azure Files share; create storage mount in Container Apps environment; mount to container at `/mnt/data`.
2. S1: Set `readOnly: true`; deploy; call write endpoint (`POST /write`); observe `EROFS` error in response and logs.
3. S2: Check that `GET /read` (listing files) works on the same mount.
4. S3: Change `readOnly: false`; redeploy; call write endpoint; verify success.

## 9. Expected signal

- S1: HTTP 500 with body `OSError: [Errno 30] Read-only file system: '/mnt/data/test.txt'`; log shows same error.
- S2 (read on read-only): HTTP 200 with file listing — read operations are unaffected.
- S3: HTTP 200 after changing to read-write.

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

- Bicep storage mount: `volumeMounts: [{ volumeName: 'myvolume', mountPath: '/mnt/data', readOnly: true }]`.
- Azure Files share must exist before deploying the container app; storage account key is stored as a Container Apps environment secret.
- Changing `readOnly` requires creating a new revision (property is revision-scoped).

## 16. Related guide / official docs

- [Use storage mounts in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
- [Azure Files in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts?pivots=azure-files)
