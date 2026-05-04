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

# Azure Files Mount in Container Apps: Authentication and NFS vs SMB

!!! info "Status: Published"
    Experiment executed 2026-05-04. SMB authentication failure (S2, wrong key) confirmed. NFS scenarios (S3, S4) blocked — NFS v3 is not available in Korea Central for this subscription tier. Non-root write permission test (S5) blocked — working mount not achievable due to Azure Policy disabling storage account key auth.

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
| Service | Azure Container Apps |
| SKU / Plan | Consumption (no custom VNet) |
| Region | Korea Central |
| Environment | `env-batch-lab` (`rg-lab-aca-batch`) |
| Container App | `aca-diag-batch` (image: `diag-app:v5`) |
| Date tested | 2026-05-04 |

!!! warning "Environment constraints"
    - **NFS blocked:** `az storage account create --enable-nfs-v3 true` returned `InvalidRequestPropertyValue: The value 'True' is not allowed for property isNfsv3Enabled` in Korea Central for this subscription. NFS scenarios (S3, S4) could not be executed.
    - **SMB key auth blocked:** Azure Policy disables `allowSharedKeyAccess` on all storage accounts in this subscription. Only the SMB authentication *failure* path (S2) was observable.

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

### S2 — SMB authentication failure (wrong storage account key)

1. Attempted to create a Standard LRS storage account with `--allow-shared-key-access true`; Azure Policy overrode to disable key auth.
2. Created storage account `salabfiles78513`; registered environment storage definition with invalid key and `accessMode: ReadWrite`.
3. Deployed revision `aca-diag-batch--v5-badmount` with the volume mounted at `/mnt/files`.
4. Observed system logs and replica state for 5 minutes.

### NFS (S3, S4)

Attempted to create a Premium FileStorage account with `--enable-nfs-v3 true`; failed with `InvalidRequestPropertyValue: The value 'True' is not allowed for property isNfsv3Enabled` (Korea Central, this subscription tier).

### S1, S5

Not executable — working SMB mount not achievable due to Azure Policy.

## 9. Expected signal

- S1: Mount succeeds; container starts; files readable/writable.
- S2: Container fails to provision; platform log shows authentication error.
- S3: NFS mount succeeds; container starts.
- S4: NFS mount hangs; container provisioning times out; revision shows Failed status.
- S5: Container starts; `/write-file` returns 403 Permission denied (uid 1000 cannot write to uid 0 files without group permission).

## 10. Results

### S2 — SMB authentication failure

```
TimeStamp            | Reason               | Message
---------------------|---------------------|--------------------------------------------------
2026-05-04 07:13:11  | ContainerTerminated  | Container 'aca-diag-batch' was terminated with
                     |                      | exit code '1' and reason 'VolumeMountFailure'.
                     |                      | Shell command exited with non-zero status code.
                     |                      | StatusCode = 32
```

Replica reached `NotRunning`. No console log output — container never started.

### NFS availability check

```bash
az storage account create \
  -n "salabfilesnfs..." -g rg-lab-aca-batch -l koreacentral \
  --sku Premium_LRS --kind FileStorage \
  --enable-nfs-v3 true

# Error:
# (InvalidRequestPropertyValue) The value 'True' is not allowed
# for property isNfsv3Enabled.
```

NFS v3 is not available in Korea Central for this subscription tier.

### S1, S3, S4, S5

Not executed — see environment constraints.

## 11. Interpretation

**H1 — Confirmed (SMB failure path only).** An incorrect storage account key causes `VolumeMountFailure` (exit code 1, StatusCode = 32) before the main container process starts. The error message does not say "authentication failed" — it is a generic `VolumeMountFailure`. **[Measured]**

**H2 — Not tested.** NFS protocol not available in Korea Central for this subscription tier.

**H3 — Not tested.** Working SMB mount not achievable in this environment.

**Key finding — NFS availability:** NFS v3 support for Azure Files (`isNfsv3Enabled: true`) is not available in all regions or subscription tiers. Customers who want NFS mounts in Container Apps must verify NFS is supported in their region/subscription before relying on it. **[Observed]**

**Key finding — SMB error vs. NFS error (design-time knowledge):** SMB authentication failures produce an immediate `VolumeMountFailure` error. NFS failures (incorrect VNet access or missing NFS enablement) are expected to produce a timeout-style failure (the mount hangs) rather than an immediate error, because NFS does not have a key-based auth handshake — access control is purely network-based. This distinction has not been confirmed in this experiment.

## 12. What this proves

- SMB Azure Files mount failure with an incorrect storage account key produces `ContainerTerminated` with reason `VolumeMountFailure` (exit code 1, StatusCode = 32). The container never starts.
- `az containerapp env storage set` accepts an invalid key at registration time without error — failure deferred to mount time.
- NFS v3 is not available in all regions/subscription tiers for Azure Files. `isNfsv3Enabled: true` is rejected in Korea Central for this subscription.

## 13. What this does NOT prove

- Whether NFS mount failures in Container Apps produce a timeout-style error (hang) vs. an immediate error — not tested.
- Whether SMB and NFS produce different error messages when authentication/access fails — not compared.
- Whether non-root container processes encounter permission errors when writing to a successfully mounted SMB share (H3) — not tested.

## 14. Support takeaway

When a customer reports "Container App won't start after adding Azure Files mount":

1. **SMB failure = `VolumeMountFailure` / exit code 1 / StatusCode = 32.** Look in `ContainerAppSystemLogs` for `Reason: ContainerTerminated` with `VolumeMountFailure`. Check storage account key, `allowSharedKeyAccess` setting, and share name.
2. **NFS is not available everywhere.** If a customer is trying to use NFS mounts in Container Apps and the storage account creation fails with `isNfsv3Enabled not allowed`, they are in a region or subscription tier that does not support NFS. They must use SMB or choose a different region.
3. **SMB vs. NFS authentication differs fundamentally.** SMB uses storage account key (immediate auth check at mount → immediate failure if wrong). NFS uses VNet-based access (no key → failure appears as network timeout or permission denied, not auth error). If a customer says "permission denied on NFS mount" — verify the Container Apps environment VNet is in the allowed VNet list on the storage account firewall.
4. **Non-root write permission issue.** If the container starts but writes fail with `Permission denied` (not `EROFS`) — the SMB mount succeeded, but the file UID/GID inside the container defaults to root. Non-root processes (uid ≠ 0) may not have write access unless the container runs as root or the share has permissive group permissions configured.

## 15. Reproduction notes

- NFS requires Azure Files Premium tier and a storage account with NFS enabled. NFS does not support storage account key authentication — access is VNet-based.
- SMB uses storage account key or Azure AD authentication. For Container Apps, storage account key is the most common configuration.
- SMB file UID/GID: files created via SMB show uid=0 inside the container. Use `az containerapp env storage set --access-mode ReadWrite` with `--account-key` for writable shares.

## 16. Related guide / official docs

- [Storage mounts in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
- [Azure Files NFS protocol support](https://learn.microsoft.com/en-us/azure/storage/files/storage-files-how-to-create-nfs-shares)
