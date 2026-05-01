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

# Azure Files Storage Mount Failures in Container Apps

!!! info "Status: Planned"

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
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

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

_To be defined during execution._

### Sketch

1. Create Azure Storage account and file share; configure Container Apps environment storage definition.
2. Deploy Container App with correct config (S1); verify `/mnt/data/test.txt` write succeeds; note replica ready.
3. Update storage definition with incorrect key (S2); deploy new revision; observe system logs and replica state for 5 minutes.
4. Restore correct key; add network restriction to storage account excluding environment subnet (S3); deploy new revision; capture system log error vs. S2 error.
5. Build container image with a non-empty `/mnt/data` directory (containing a marker file); deploy with mount at same path (S4); check if marker file is visible or shadowed.
6. Write a test file in S1; deploy new revision with identical volume config (S5); verify file persists.

## 9. Expected signal

- S1: Replica becomes ready; file write succeeds; no mount errors in system log.
- S2: Replica does not become ready; `ContainerAppSystemLogs` shows a provisioning failure referencing the volume; error message is generic rather than explicitly "authentication failed".
- S3: Replica does not become ready; system log shows a provisioning failure; error message does not clearly distinguish network timeout from authentication failure.
- S4: Container starts successfully; marker file is not visible at `/mnt/data` (shadowed by mount); no error emitted.
- S5: New replica starts; `/mnt/data/test.txt` from S1 is accessible; data persists from share.

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

- Azure Files mounts use SMB 3.0 on port 445; ensure port 445 is not blocked between the Container Apps environment and the storage account.
- The storage definition is configured at the **environment** level (`az containerapp env storage set`), not at the Container App level; verify with `az containerapp env storage list`.
- `allowSharedKeyAccess` must be `true` on the storage account for key-based authentication; managed identity mounts use a different path.
- The network restriction test requires identifying the Container Apps environment's outbound IP range or subnet and excluding it from the storage account's network rules.

## 16. Related guide / official docs

- [Use storage mounts in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
- [Troubleshoot storage mount failures in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-storage-mount-failures)
- [Azure Files networking considerations](https://learn.microsoft.com/en-us/azure/storage/files/storage-files-networking-overview)
