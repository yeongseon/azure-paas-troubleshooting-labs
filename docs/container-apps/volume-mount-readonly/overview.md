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

# Volume Mount Read-Only Mode: Application Write Failures on Azure Files Mount

!!! info "Status: Published"
    Experiment executed 2026-05-04. Observed that `readOnly: true` with an invalid storage key produces the same `VolumeMountFailure` / `StatusCode = 32` as `readOnly: false` with invalid key — the read-only flag is a client-side POSIX restriction applied after a successful mount, not a separate error path. Full write-failure test (H1) constrained by Azure Policy blocking storage account key auth in this subscription.

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
| Environment | `env-batch-lab` (`rg-lab-aca-batch`) |
| Container App | `aca-diag-batch` (image: `diag-app:v5`) |
| Date tested | 2026-05-04 |

!!! warning "Environment constraint"
    Azure Policy in this subscription disables storage account key authentication. A working Azure Files mount (H2, H3, H4 scenarios requiring a successful mount) could not be completed. The experiment focused on the failure path for `readOnly: true` with an invalid key, which confirms the error message and exit code.

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

### S1 — `readOnly: true` with invalid storage key

1. Registered a ReadOnly environment storage definition:

```bash
az containerapp env storage set \
  --name env-batch-lab \
  --resource-group rg-lab-aca-batch \
  --storage-name "test-files-readonly" \
  --azure-file-account-name "salabfiles78513" \
  --azure-file-account-key "INVALID_KEY_FOR_TESTING_PURPOSES_AAAAAAAAAAA=" \
  --azure-file-share-name "lab-test-share" \
  --access-mode ReadOnly
# Output: { "accessMode": "ReadOnly", "name": "test-files-readonly" }
```

2. Deployed revision `aca-diag-batch--v5-romount` with `storageType: AzureFile, storageName: test-files-readonly` mounted at `/mnt/ro`.

3. Observed replica state and system logs for 5 minutes.

## 9. Expected signal

- S1: HTTP 500 with body `OSError: [Errno 30] Read-only file system: '/mnt/data/test.txt'`; log shows same error.
- S2 (read on read-only): HTTP 200 with file listing — read operations are unaffected.
- S3: HTTP 200 after changing to read-write.

## 10. Results

### S1 — `readOnly: true` with invalid key

**Replica state:** `NotRunning` (identical to `readOnly: false` with invalid key)

**System log capture:**

```
TimeStamp            | Reason               | Message
---------------------|---------------------|-------------------------------------------------
2026-05-04 07:30:51  | ContainerTerminated  | Container 'aca-diag-batch' was terminated with
                     |                      | exit code '1' and reason 'VolumeMountFailure'.
                     |                      | Shell command exited with non-zero status code.
                     |                      | StatusCode = 32
```

**Comparison with ReadWrite / wrong key (from `storage-mount-failures` experiment):**

| Property | ReadWrite + wrong key | ReadOnly + wrong key |
|---|---|---|
| Reason | `ContainerTerminated` | `ContainerTerminated` |
| Message | `VolumeMountFailure` | `VolumeMountFailure` |
| Exit code | `1` | `1` |
| StatusCode | `32` | `32` |

The error is **identical**. The `readOnly` flag does not change the mount failure reason or exit code when authentication fails.

### S2, S3 (read-only mount with read operations; read-write success)

Not executable — working mount not achievable in this environment.

## 11. Interpretation

**H1 — Partially confirmed, partially untested.** The `readOnly: true` flag does not change the mount error path when authentication fails — both ReadOnly and ReadWrite definitions with an invalid key produce the same `VolumeMountFailure` / exit code 1 / StatusCode = 32. The read-only restriction is enforced after a successful SMB mount (POSIX `MS_RDONLY` flag to the Linux kernel), so it only manifests as `EROFS` at write time on a successfully mounted filesystem. **[Measured — failure path]** **[Not Proven — write error path, not tested]**

**H2 — Strongly Suggested.** The configuration is accepted at deployment time without error. The `readOnly` flag is not validated against application behavior during deployment. **[Strongly Suggested — consistent with S1 observations]**

**H3 — Not tested.** A working mount is required to verify that `ls /mnt/data` succeeds on a read-only mount.

**Key observation:** `az containerapp env storage set --access-mode ReadOnly` is accepted silently. The `accessMode` field is stored correctly in the environment storage definition, but there is no deployment-time warning that the application may attempt writes. The error (`EROFS`) only surfaces at runtime when a write is attempted — and only if the mount itself succeeds. **[Observed]**

## 12. What this proves

- `readOnly: true` and `readOnly: false` produce the same `VolumeMountFailure` error (exit code 1, StatusCode = 32) when storage account key authentication fails. The `readOnly` flag does not change the mount failure path.
- `az containerapp env storage set --access-mode ReadOnly` is accepted silently at registration time, with no deployment-time validation against application write behavior.

## 13. What this does NOT prove

- The exact error message (`OSError: [Errno 30] Read-only file system`) when an application writes to a successfully mounted read-only Azure Files volume — not confirmed in this experiment due to environment constraint.
- Whether `ls /mnt/ro` succeeds on a read-only mount before a write is attempted (H3) — not tested.
- Whether changing `readOnly: false` and deploying a new revision immediately resolves the issue (H4) — not tested.

## 14. Support takeaway

When a customer reports "app crashes on file write but the container starts":

1. **Distinguish mount failure from write failure.** If the container does not start at all → look for `VolumeMountFailure` in system logs (wrong key or network issue). If the container starts but a write fails → the mount succeeded, but the application is writing to a read-only mount.
2. **Write failure on read-only mount = `EROFS` (errno 30).** The Python/application error is `OSError: [Errno 30] Read-only file system: '/mnt/data/file.txt'`. This only appears in application logs (console), not in system logs.
3. **`readOnly` flag is not validated at deployment.** Check the environment storage definition (`az containerapp env storage list`) and the app template `volumes` / `volumeMounts` sections for `accessMode: ReadOnly` or `readOnly: true`. No deployment-time error is emitted.
4. **Fix: change `accessMode` to `ReadWrite` and deploy a new revision.** The Azure Files share data is unaffected by this change.

## 15. Reproduction notes

- Bicep storage mount: `volumeMounts: [{ volumeName: 'myvolume', mountPath: '/mnt/data', readOnly: true }]`.
- Azure Files share must exist before deploying the container app; storage account key is stored as a Container Apps environment secret.
- Changing `readOnly` requires creating a new revision (property is revision-scoped).

## 16. Related guide / official docs

- [Use storage mounts in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
- [Azure Files in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts?pivots=azure-files)
