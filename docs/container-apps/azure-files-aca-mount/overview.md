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

# Azure Files Mount in Container Apps: Authentication and NFS vs SMB

!!! info "Status: Planned"

## 1. Question

Container Apps supports Azure Files storage mounts using either SMB (CIFS) or NFS protocol. What failure modes occur with each protocol when authentication is misconfigured, and how do the observable symptoms differ between SMB authentication failure and NFS permission failure?

## 2. Why this matters

Azure Files mounts in Container Apps are used for shared data volumes across replicas — a common pattern for content management, configuration files, and shared caches. The two protocols (SMB and NFS) have different authentication mechanisms: SMB uses storage account key or Azure AD authentication, while NFS uses VNet-based access (no key, but requires VNet integration and NFS-enabled storage account). When teams choose the wrong protocol or misconfigure authentication, the mount failure prevents all replicas from starting, causing a total outage.

## 3. Customer symptom

"Container app fails to start after adding Azure Files storage mount" or "The mount works but we can't write files — permission denied" or "NFS mount fails but SMB mount works to the same storage account."

## 4. Hypothesis

- H1: SMB authentication failure (wrong account key) causes the container to fail to start. The error is `mount error(13): Permission denied` or `mount error(115): Operation now in progress` (timeout). The container app revision fails to provision.
- H2: NFS authentication failure occurs differently: NFS relies on network-level access (the client IP must be within an allowed VNet). If Container Apps is not VNet-integrated or the VNet is not allowed in the storage account firewall, the NFS mount hangs at connection time (no immediate error), eventually timing out.
- H3: SMB mounts created files with the file permissions set to the storage account owner (uid 0 inside the container by default). A non-root container process may receive `Permission denied` when writing to the SMB mount even though the mount itself succeeds.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps (VNet-integrated for NFS) |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Storage / Networking

**Controlled:**

- Azure Files share (SMB and NFS)
- Container Apps with and without VNet integration
- Correct and incorrect authentication credentials

**Observed:**

- Container startup success/failure with each protocol and auth configuration
- File permission behavior on successfully mounted shares

**Scenarios:**

- S1: SMB, correct key → mount succeeds
- S2: SMB, wrong key → mount fails (auth error)
- S3: NFS, VNet-integrated → mount succeeds
- S4: NFS, no VNet integration → mount hangs/times out
- S5: SMB success, non-root process writes → permission denied

## 7. Instrumentation

- Container app revision status (`az containerapp revision show`)
- Container logs for mount error messages
- `ContainerAppSystemLogs` for provisioning errors
- File operation test endpoint (`/write-file`, `/read-file`)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create Azure Files Premium share with both SMB and NFS enabled.
2. S1-S2: Configure SMB mount with correct and incorrect storage key; observe start behavior.
3. S3-S4: Configure NFS mount with VNet-integrated and non-VNet-integrated Container Apps environment; observe.
4. S5: Run container as non-root user (uid 1000); mount SMB share; attempt file write; observe permission error.

## 9. Expected signal

- S1: Mount succeeds; container starts; files readable/writable.
- S2: Container fails to provision; platform log shows authentication error.
- S3: NFS mount succeeds; container starts.
- S4: NFS mount hangs; container provisioning times out; revision shows Failed status.
- S5: Container starts; `/write-file` returns 403 Permission denied (uid 1000 cannot write to uid 0 files without group permission).

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

- NFS requires Azure Files Premium tier and a storage account with NFS enabled. NFS does not support storage account key authentication — access is VNet-based.
- SMB uses storage account key or Azure AD authentication. For Container Apps, storage account key is the most common configuration.
- SMB file UID/GID: files created via SMB show uid=0 inside the container. Use `az containerapp env storage set --access-mode ReadWrite` with `--account-key` for writable shares.

## 16. Related guide / official docs

- [Storage mounts in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
- [Azure Files NFS protocol support](https://learn.microsoft.com/en-us/azure/storage/files/storage-files-how-to-create-nfs-shares)
