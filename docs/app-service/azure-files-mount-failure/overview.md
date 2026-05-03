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

# Azure Files Mount Failure: Authentication and Latency Issues

!!! info "Status: Planned"

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
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Storage / Networking

**Controlled:**

- Azure Files share in the same region and a share in a remote region (e.g., West US)
- Storage account with and without firewall rules
- App Service with custom storage mount configured

**Observed:**

- App startup success/failure with incorrect key
- App startup success/failure with firewall blocking
- I/O operation latency on same-region vs. remote-region share

**Scenarios:**

- S1: Correct key, no firewall → mount succeeds, app starts
- S2: Wrong account key → mount fails, app returns 503
- S3: Correct key, firewall blocks App Service IPs → mount fails, app returns 503
- S4: Correct key, no firewall, remote region share → mount succeeds but I/O is slow

## 7. Instrumentation

- App Service platform logs (`AppServicePlatformLogs`)
- Kudu SSH console: `mount | grep cifs`, `time ls -la /mnt/share`
- Azure Storage metrics: `Availability`, `SuccessE2ELatency`
- Application timing logs for file operations

## 8. Procedure

_To be defined during execution._

### Sketch

1. Create Azure Files share in Korea Central; mount to App Service with correct credentials; verify startup.
2. S2: Change the account key in the mount configuration to an invalid value; restart; observe 503 and platform log error.
3. S3: Restore correct key; add firewall rule to storage account blocking all networks; restart; observe failure and error type.
4. S4: Remove firewall; create a share in West US; remount app to West US share; measure `time ls -la /mnt/share` with 100+ files.

## 9. Expected signal

- S1: App starts; `mount | grep cifs` shows the share mounted.
- S2: App fails to start; platform logs show CIFS authentication error; portal shows "Mount error" status.
- S3: App fails to start; error message references connection timeout or refused (different from S2).
- S4: `ls -la` with 100 files takes significantly longer than same-region; application file-listing operations exhibit proportional latency.

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

- Custom storage mounts are configured under **Configuration > Path mappings** or via ARM: `properties.storageConfiguration`.
- SMB port 445 must be reachable from App Service outbound IPs. Use VNet Integration + service endpoint or private endpoint for firewall-protected storage.
- Azure Files performance scales with the share provisioned IOPS and throughput — premium shares are recommended for latency-sensitive workloads.

## 16. Related guide / official docs

- [Mount Azure Storage as a local share in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-connect-to-azure-storage)
- [Azure Files networking](https://learn.microsoft.com/en-us/azure/storage/files/storage-files-networking-overview)
