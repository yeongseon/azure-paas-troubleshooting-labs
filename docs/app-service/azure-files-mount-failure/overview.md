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

# Azure Files Mount Failure: Authentication and Latency Issues

!!! info "Status: Published"
    Experiment executed 2026-05-04. S2 (wrong storage account key) confirmed with live platform log capture. S3 (firewall block) and S4 (remote region latency) not executed — S4 requires a B1+ plan cross-region share; S3 blocked by Azure Policy (key auth disabled on new storage accounts, making a correct-key+firewall test infeasible).

## 1. Question

When Azure Files is mounted to an App Service Linux app as a custom storage mount, what failure modes occur due to authentication errors (wrong account key, missing firewall rule) or high SMB latency, and how do these failures manifest in the application vs. what is visible in platform diagnostics?

## 2. Why this matters

Azure Files custom storage mounts are commonly used for shared content, configuration files, and session state. When the mount fails or becomes unavailable, the app may fail at startup (if the mount is required for startup) or degrade mid-operation (if the mount becomes unavailable after startup). The failure mode differs significantly between a failed mount at startup (app never starts) and a mount that becomes unavailable after startup (I/O errors on existing processes). Engineers often cannot distinguish between a networking issue and a permissions issue from application logs alone.

## 3. Customer symptom

"The app fails to start after we added Azure Files storage mount" or "File operations randomly fail with timeout errors even though the storage account is accessible" or "The app started correctly but hangs whenever it tries to read a file from the mounted share."

## 4. Hypothesis

- H1: When the Azure Files storage account key is incorrect, the mount fails at app startup with an authentication error. The app does not start and returns 503; the error is visible in App Service platform logs.
- H2: When the storage account has a firewall rule that blocks App Service outbound IPs (and VNet Integration is not configured), the SMB connection is refused. The mount failure is network-level and produces a different error message than the authentication failure.
- H3: When Azure Files is in a remote region (high latency), SMB operations that involve many small I/O operations (e.g., directory listings, stat calls) exhibit significant latency amplification. Each stat call incurs the round-trip; an operation that lists 100 files takes 100× the RTT.
- H4: The mount status is visible in the App Service **Configuration > Path mappings** blade, but the error detail requires checking platform logs or the Kudu console (`mount | grep cifs` output).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| App | `app-batch-1777849901` (`rg-lab-appservice-batch`) |
| Storage account | `salabfiles78513` (Standard LRS, `rg-lab-aca-batch`) |
| Date tested | 2026-05-04 |

!!! warning "Environment constraint"
    Azure Policy in this subscription disables storage account key authentication. A correct-key baseline (S1) could not be completed. The S2 test used an explicitly invalid key string, which was sufficient to observe the full failure path and platform log messages.

## 6. Variables

**Experiment type**: Storage / Networking

**Controlled:**

- Azure Files share in the same region
- Storage account with an incorrect key
- App Service with custom storage mount configured at `/mnt/azfiles`

**Observed:**

- App startup success/failure with incorrect key
- Platform log error detail (`docker.log` from `az webapp log download`)
- Mount status in `az webapp config storage-account list` — `state` field
- App behavior during the failure loop (503 vs. restarting)

**Scenarios:**

- S1: Correct key, no firewall → mount succeeds, app starts (not executed — key auth blocked by Azure Policy)
- S2: Wrong account key → mount fails, app returns 503
- S3: Correct key, firewall blocks App Service IPs → mount fails, app returns 503 (not executed)
- S4: Correct key, no firewall, remote region share → mount succeeds but I/O is slow (not executed)

## 7. Instrumentation

- `az webapp config storage-account list` — `state` field immediately reflects `InvalidCredentials` or `Ok`
- App Service platform logs via `az webapp log download` → `docker.log` — `LastError`, `LastErrorDetails`, `VolumeMountFailure` entries
- App health endpoint (`/health`) — returns 503 or "Application Error" when container fails to start
- `AppServicePlatformLogs` in Log Analytics (if streaming logs are enabled): `BYOSFailure` events

## 8. Procedure

### S2 — Wrong storage account key

1. Added Azure Files custom storage mount with an invalid key via CLI:

```bash
az webapp config storage-account add \
  -n app-batch-1777849901 -g rg-lab-appservice-batch \
  --custom-id "test-azure-files" \
  --storage-type AzureFiles \
  --account-name salabfiles78513 \
  --share-name "lab-test-share" \
  --access-key "INVALID_KEY_FOR_TESTING_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==" \
  --mount-path "/mnt/azfiles"
```

2. Checked `az webapp config storage-account list` for immediate mount state.
3. Observed app health endpoint — received "Application Error" (503).
4. Downloaded platform logs via `az webapp log download`; inspected `docker.log` for error details.
5. Removed the mount to restore the app:

```bash
az webapp config storage-account delete \
  -n app-batch-1777849901 -g rg-lab-appservice-batch \
  --custom-id "test-azure-files"
```

## 9. Expected signal

- S2: App fails to start; platform logs show `BYOSFailure` and `VolumeMountFailure`; `az webapp config storage-account list` shows `state: InvalidCredentials`; portal shows "Mount error" status.

## 10. Results

### S2 — Wrong storage account key

**Immediate mount state (`az webapp config storage-account list`):**

```json
{
  "name": "test-azure-files",
  "value": {
    "accessKey": "INVALID_KEY_...",
    "accountName": "salabfiles78513",
    "mountPath": "/mnt/azfiles",
    "protocol": "Smb",
    "shareName": "lab-test-share",
    "state": "InvalidCredentials",
    "type": "AzureFiles"
  }
}
```

The `state: InvalidCredentials` was visible **immediately** after `storage-account add` — before any restart.

**App health endpoint:** returned "Application Error" page (HTTP 503-equivalent) — app not serving requests.

**Platform log (`docker.log`) — key entries:**

```
2026-05-04T07:35:25Z  State: Stopped
  LastError: BYOSFailure
  LastErrorDetails: Failure mounting the provided storage. Permission was denied.
    Check Network and Auth configuration to ensure the File Share is accessible from App Service.
    Current settings: Account: salabfiles78513 | ShareName: lab-test-share

2026-05-04T07:36:23Z  Volume: BYOS_FILES_test-azure-files cannot be mounted at /mnt/azfiles
    during container: app-batch-1777849901 startup. The volume mount is required. Terminate.

2026-05-04T07:36:23Z  Container start up failed with reason: VolumeMountFailure. Revert by terminate.

2026-05-04T07:36:23Z  State: Stopping, Action: CancellingStartup
  LastError: BYOSFailure
  LastErrorDetails: Failure mounting the provided storage. Permission was denied.
    Check Network and Auth configuration to ensure the File Share is accessible from App Service.
    Current settings: Account: salabfiles78513 | ShareName: lab-test-share
```

The platform restart loop: `Stopped → Starting → MountingVolumes → VolumeMountFailure → CancellingStartup → Stopped` repeating.

**After mount removal:** App recovered within ~30 seconds (`/health` returned `{"status":"healthy"}`).

### S1, S3, S4

Not executed — see environment constraint note above.

## 11. Interpretation

**H1 — Confirmed.** An incorrect storage account key causes a `BYOSFailure` at mount time. The app enters a crash loop (`Stopped → Starting → VolumeMountFailure → Stopped`). The error is visible in two places: `state: InvalidCredentials` in `az webapp config storage-account list` (immediate), and `LastError: BYOSFailure` + `LastErrorDetails: Permission was denied` in platform logs. **[Measured]**

**H4 — Confirmed (partially).** The `state: InvalidCredentials` field is visible immediately via CLI (`az webapp config storage-account list`) without needing to check platform logs. This is the fastest diagnostic signal for authentication failures. Platform logs provide the full error message (`BYOSFailure`, `Permission was denied`, volume name). **[Measured]**

**H2, H3 — Not tested.** Firewall and remote-region scenarios not executed.

**Key observation:** The `state` field in `az webapp config storage-account list` is updated immediately upon adding the mount, before any restart — making it a reliable first-check indicator. The platform log entry `The volume mount is required. Terminate.` confirms that Azure Files mounts with `isRequired=true` (the default) prevent the container from starting if they fail. **[Observed]**

## 12. What this proves

- A wrong Azure Files storage account key produces `state: InvalidCredentials` in `az webapp config storage-account list` immediately after configuration, before any app restart.
- The platform log (`docker.log`) contains a specific `BYOSFailure` event with `LastErrorDetails: Failure mounting the provided storage. Permission was denied.` including the account name and share name.
- The error message for authentication failure says **"Permission was denied"** — not "authentication failed" or "wrong key." Support engineers must recognize this phrase as an auth/credentials issue, not a file permission issue.
- When the mount is required (default), the App Service container enters a crash loop — `VolumeMountFailure → Terminate → restart → VolumeMountFailure` — and never serves requests.
- Removing the invalid mount via `az webapp config storage-account delete` restores the app within ~30 seconds.

## 13. What this does NOT prove

- Whether a firewall-blocked storage account produces a different error message than a wrong-key error (H2) — not tested. The firewall block may produce "connection timed out" rather than "Permission was denied."
- Whether high SMB latency (remote region share) causes application-visible I/O slowness (H3) — not tested.
- Whether an `isRequired=false` mount (optional mount) allows the app to start even if the mount fails — not tested; would require ARM-level configuration.
- The behavior when the Azure Files share becomes unavailable **after** a successful mount (mid-operation failure) — not tested.

## 14. Support takeaway

When a customer reports "App Service fails to start after adding Azure Files storage mount":

1. **First check: `az webapp config storage-account list`.** If `state: InvalidCredentials` — the account key is wrong, the share name is wrong, or the storage account has `allowSharedKeyAccess=false`. This is the fastest diagnostic signal and does not require log access.
2. **Platform log error phrase: "Permission was denied."** In App Service platform logs (`docker.log`), the error for wrong key is `BYOSFailure` with `Permission was denied`. This is **not** a file ACL error — it is an SMB authentication failure. Also look for `VolumeMountFailure` and `The volume mount is required. Terminate.`.
3. **Check `allowSharedKeyAccess` on the storage account.** Azure Policy may disable this. If so, key-based SMB mounts will never succeed. Managed identity-based mounts are not yet supported for App Service Azure Files custom mounts (as of 2026-05).
4. **Remove the mount to unblock the app immediately.** `az webapp config storage-account delete` removes the failing mount and lets the app restart. The fix to the credential/config can then be applied without a prolonged outage.
5. **Distinguish from network failure (H2, not confirmed).** If the key is correct and `allowSharedKeyAccess=true` but the mount still fails, check storage account firewall rules. A network-blocked mount likely shows "connection timed out" rather than "Permission was denied" — but this was not confirmed in this experiment.

## 15. Reproduction notes

- Custom storage mounts are configured under **Configuration > Path mappings** or via ARM: `properties.storageConfiguration`.
- SMB port 445 must be reachable from App Service outbound IPs. Use VNet Integration + service endpoint or private endpoint for firewall-protected storage.
- Azure Files performance scales with the share provisioned IOPS and throughput — premium shares are recommended for latency-sensitive workloads.
- `allowSharedKeyAccess` must be `true` on the storage account for key-based mounts. Check with `az storage account show --query "properties.allowSharedKeyAccess"`.

## 16. Related guide / official docs

- [Mount Azure Storage as a local share in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-connect-to-azure-storage)
- [Azure Files networking](https://learn.microsoft.com/en-us/azure/storage/files/storage-files-networking-overview)
- [Troubleshoot Azure Files mount issues in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-connect-to-azure-storage#troubleshoot)
