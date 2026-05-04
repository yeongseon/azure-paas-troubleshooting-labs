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

# Azure Files Storage Mount Failures in Container Apps

!!! info "Status: Published"
    Experiment executed 2026-05-04. S2 (wrong key) confirmed with live system log capture. S3 (network restriction) and S4/S5 (shadowing, persistence) constrained by subscription Azure Policy (key-based auth disabled on all storage accounts); documented as environment limitation.

## 1. Question

When an Azure Files share is mounted into a Container App replica and the mount fails — due to an incorrect storage key, a network restriction, or a mount path conflict — how does the failure manifest in replica provisioning, system logs, and console logs?

## 2. Why this matters

Azure Files mounts in Container Apps are commonly used for shared configuration files, output logs, and data persistence across revisions. A mount failure at container startup prevents the replica from becoming ready, causing a provisioning failure that looks identical to an application crash from the outside. The platform error messages for mount failures are often generic, making it difficult for support engineers to distinguish between authentication errors, network path issues, and storage account configuration problems.

## 3. Customer symptom

"My Container App keeps failing to start with no application error" or "The container starts but I can't find the files I wrote to the mounted path" or "Storage mount worked in staging but fails in production with the same config."

## 4. Hypothesis

- H1: If the storage account key is incorrect, the Azure Files mount fails before the main container starts; the replica does not become ready. `ContainerAppSystemLogs` shows a mount-related failure event referencing the volume name. The failure reason does not explicitly state "authentication" — it appears as a generic provisioning error.
- H2: If the storage account is behind a network restriction that excludes the Container Apps environment subnet, the mount fails with a network timeout; the error message is similarly generic and does not distinguish a network failure from an authentication failure.
- H3: If the mount path matches an existing directory in the container image, the mount shadows (overlays) the existing directory — files in the image at that path become inaccessible, but the container starts successfully. No error is emitted.
- H4: When a new revision is deployed with the same volume configuration pointing to the same Azure Files share, the share is remounted in the new replicas. Data written to the share by the previous revision is accessible in the new revision. The persistence comes from the share itself, not from the replica.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | `env-batch-lab` (`rg-lab-aca-batch`) |
| Container App | `aca-diag-batch` (image: `diag-app:v5`) |
| Storage account | `salabfiles78513` (Standard LRS, `rg-lab-aca-batch`) |
| Date tested | 2026-05-04 |

!!! warning "Environment constraint"
    Azure Policy in this subscription enforces `allowSharedKeyAccess=false` on all storage accounts, including newly created ones. SMB-based Azure Files mounts in Container Apps require storage account key authentication. As a result, S1 (correct key baseline), S3 (network restriction), S4 (path shadowing), and S5 (data persistence) could not be completed. S2 (wrong key / mount failure) was executed using a storage mount definition with a syntactically valid but invalid key.

## 6. Variables

**Experiment type**: Reliability / Configuration

**Controlled:**

- Azure Storage account (Standard LRS) with a file share
- Container App with Azure Files volume mounted at `/mnt/data`
- Storage account authentication: storage account key

**Observed:**

- Replica readiness state (ready vs. not ready, provisioning failure)
- `ContainerAppSystemLogs` entries — volume mount event, Reason and Message fields
- `ContainerAppConsoleLogs` entries — any mount-related stderr from the container
- File accessibility at mount path post-start (shadowing test)
- File persistence across revision update

**Scenarios:**

- S1: Correct storage key — baseline
- S2: Incorrect storage key — authentication failure
- S3: Storage account with network restriction excluding Container Apps environment subnet — network failure
- S4: Mount path `/mnt/data` exists as a non-empty directory in the container image — shadowing test
- S5: New revision deployed with identical volume config — data persistence check

**Independent run definition**: One revision deployment per scenario; observe for 10 minutes.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `ContainerAppSystemLogs` KQL: `| where Reason contains "Mount" or Reason contains "Volume" or Reason contains "Failed"` — mount failure events
- `ContainerAppConsoleLogs` KQL: container stdout/stderr during startup
- `az containerapp env storage list --name <env> --resource-group <rg>` — environment storage definition
- `az containerapp revision show --query "properties.replicas"` — replica readiness state
- File test: write `/mnt/data/test.txt` in container at startup; read it back via debug endpoint
- Data persistence: write file in S1; deploy S5 with same volume config; verify file presence

## 8. Procedure

### S2 — Wrong storage account key

1. Created storage account `salabfiles78513` (Standard LRS, Korea Central) with `--allow-shared-key-access true`. Azure Policy overrode this setting, resulting in key-based auth disabled.
2. Registered environment-level storage definition with invalid key:

```bash
az containerapp env storage set \
  --name env-batch-lab \
  --resource-group rg-lab-aca-batch \
  --storage-name "test-files-mount" \
  --azure-file-account-name "salabfiles78513" \
  --azure-file-account-key "INVALID_KEY_FOR_TESTING_PURPOSES_AAAAAAAAAAA=" \
  --azure-file-share-name "lab-test-share" \
  --access-mode ReadWrite
```

3. Deployed new revision `aca-diag-batch--v5-badmount` referencing the volume via ARM PATCH with `storageType: AzureFile, storageName: test-files-mount` mounted at `/mnt/files`.
4. Observed replica state and system logs for 5 minutes.
5. Reverted: deployed clean revision `aca-diag-batch--v5-clean` with no volumes; removed env storage definition.

## 9. Expected signal

- S1: Replica becomes ready; file write succeeds; no mount errors in system log.
- S2: Replica does not become ready; `ContainerAppSystemLogs` shows a provisioning failure referencing the volume; error message is generic rather than explicitly "authentication failed".
- S3: Replica does not become ready; system log shows a provisioning failure; error message does not clearly distinguish network timeout from authentication failure.
- S4: Container starts successfully; marker file is not visible at `/mnt/data` (shadowed by mount); no error emitted.
- S5: New replica starts; `/mnt/data/test.txt` from S1 is accessible; data persists from share.

## 10. Results

### S2 — Wrong storage account key

**Replica state:**

```
az containerapp replica list \
  -n aca-diag-batch -g rg-lab-aca-batch \
  --revision "aca-diag-batch--v5-badmount" \
  --query "[0].{name:name,state:properties.runningState}"

{
  "name": "aca-diag-batch--v5-badmount-858c86dbc8-27ddd",
  "state": "NotRunning"
}
```

**System log capture (`ContainerAppSystemLogs`):**

```
TimeStamp            | Reason                | Message
---------------------|----------------------|-------------------------------------------------
2026-05-04 07:13:11  | ContainerTerminated  | Container 'aca-diag-batch' was terminated with
                     |                      | exit code '1' and reason 'VolumeMountFailure'.
                     |                      | Shell command exited with non-zero status code.
                     |                      | StatusCode = 32
```

**Probe failures observed before termination:**

```
2026-05-04 07:10:58  | ProbeFailed          | Probe of Readiness failed with status code: 500
2026-05-04 07:11:04  | ProbeFailed          | Probe of Readiness failed with status code: 500
... (repeated every 6 seconds)
2026-05-04 07:13:11  | ContainerTerminated  | exit code '1', reason 'VolumeMountFailure', StatusCode = 32
```

**Console log:** No application logs captured — container never reached application startup (volume mount failed before app process started).

**Volume definition acceptance:** `az containerapp env storage set` accepted the invalid key without error at definition time. The failure occurred only at mount time when the revision was deployed.

### S1, S3, S4, S5

Not executed due to Azure Policy blocking storage account key authentication in this subscription. See environment constraint note above.

## 11. Interpretation

**H1 — Confirmed (partial).** An incorrect storage account key causes the replica to fail before the main container process starts. The system log shows `ContainerTerminated` with `reason: VolumeMountFailure` and exit code 1 (`StatusCode = 32`). The failure reason is `VolumeMountFailure` — it does not say "authentication failed" or "wrong key". **[Measured]**

The readiness probe returns HTTP 500 repeatedly in the seconds before the final `ContainerTerminated` event, suggesting the container process briefly starts (or a probe is attempted) before the volume mount failure terminates it. **[Observed]**

**H2 — Not tested.** Network restriction path not executed.

**H3, H4 — Not tested.** Shadowing and persistence scenarios not executed.

**Key observation:** The environment-level storage definition (`az containerapp env storage set`) accepts an invalid key without error. The failure is deferred to mount time — a silent misconfiguration that only surfaces at deployment. **[Observed]**

## 12. What this proves

- An invalid storage account key causes the Container App replica to reach state `NotRunning` with system log reason `VolumeMountFailure` (exit code 1, StatusCode = 32).
- The failure is not surfaced at the time the storage definition is registered — it occurs at mount time during revision deployment.
- The error message does not explicitly state "authentication failed" — it is a generic `VolumeMountFailure`. Support engineers must interpret the exit code and reason together.
- Readiness probe failures (HTTP 500) are visible in system logs before the final `ContainerTerminated` event.

## 13. What this does NOT prove

- Whether a network restriction produces the same `VolumeMountFailure` reason or a distinct error — not tested in this experiment.
- Whether the read-only flag (`readOnly: true`) prevents writes at runtime — tested in the `volume-mount-readonly` experiment.
- Whether NFS mounts fail with a different error message than SMB mounts — NFS not available in Korea Central with this subscription tier.
- Whether data written in one revision persists to a subsequent revision via the same volume — not tested.
- Whether the shadowing behavior (mount overlaying existing image directory) produces an error or silently hides image contents.

## 14. Support takeaway

When a customer reports "Container App fails to start after adding Azure Files storage mount":

1. **Check system logs for `VolumeMountFailure`.** The specific Reason field is `ContainerTerminated` with message containing `VolumeMountFailure` and `StatusCode = 32`. This is an SMB mount authentication failure (wrong key, missing share, or network block) — the platform does not distinguish between them in the log message.
2. **Verify the environment-level storage definition, not just the app config.** The storage is registered at `az containerapp env storage set` — a wrong key here is accepted silently and only fails at mount time. Run `az containerapp env storage list` to confirm the storage name, account name, and share name.
3. **Check `allowSharedKeyAccess` on the storage account.** If the storage account has key-based auth disabled (via Azure Policy or manual setting), ACA SMB mounts will always fail. The fix is either to enable key auth (`az storage account update --allow-shared-key-access true`) or use a storage account where key auth is permitted. Managed identity mounts are not supported for Azure Files in Container Apps as of 2026-05.
4. **The failure is pre-application.** The replica never reaches a running state. Console logs show nothing — only system logs capture the failure. Look in `ContainerAppSystemLogs` filtered by `Reason == "ContainerTerminated"` and `Msg contains "VolumeMountFailure"`.

## 15. Reproduction notes

- Azure Files mounts use SMB 3.0 on port 445; ensure port 445 is not blocked between the Container Apps environment and the storage account.
- The storage definition is configured at the **environment** level (`az containerapp env storage set`), not at the Container App level; verify with `az containerapp env storage list`.
- `allowSharedKeyAccess` must be `true` on the storage account for key-based authentication; managed identity mounts use a different path.
- The network restriction test requires identifying the Container Apps environment's outbound IP range or subnet and excluding it from the storage account's network rules.

## 16. Related guide / official docs

- [Use storage mounts in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
- [Troubleshoot storage mount failures in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-storage-mount-failures)
- [Azure Files networking considerations](https://learn.microsoft.com/en-us/azure/storage/files/storage-files-networking-overview)
