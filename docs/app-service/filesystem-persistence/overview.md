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

# Linux /home vs Writable Layer Persistence

!!! info "Status: Planned"

## 1. Question

On App Service Linux, what is the persistence behavior difference between the `/home` mount and the container's writable layer, and does data written to each survive restarts, deployments, and scale operations?

## 2. Why this matters

Customers often store temporary files, caches, or user uploads on the local filesystem without understanding which paths persist across restarts and which are ephemeral. Losing files after a deployment or instance migration causes data loss incidents that are difficult to debug because the app appears functional.

## 3. Customer symptom

- "Files uploaded by users disappear after we deploy a new version."
- "Our cache directory is empty after the app restarts."
- "Some files survive restarts but others don't — we don't understand the pattern."

## 4. Hypothesis

On App Service Linux:

1. Files written to `/home` persist across restarts and deployments because `/home` is backed by Azure Storage.
2. Files written outside `/home` (e.g., `/tmp`, `/var/data`) are lost on restart because they exist only in the container's writable overlay layer.
3. During scale-out, new instances can access `/home` files but not files written to the writable layer of other instances.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1, P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Write locations: `/home/data/`, `/tmp/data/`, `/var/local/data/`
- File sizes and write timestamps
- Trigger events: restart, deployment, scale-out, instance migration

**Observed:**

- File existence after each trigger event
- File content integrity (checksum verification)
- `/home` mount type and backing storage
- I/O latency for `/home` vs local filesystem

## 7. Instrumentation

- SSH/Kudu console: filesystem inspection
- Application logging: file write/read operations with timestamps
- Azure Monitor: instance identity changes

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Files in `/home` survive all trigger events
- Files outside `/home` are lost on restart and deployment
- New scale-out instances can see `/home` files but not local-layer files from other instances

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

- `/home` is an Azure Storage-backed SMB mount; performance characteristics differ from local disk
- WEBSITE_ENABLE_PERSISTENT_STORAGE setting affects behavior on custom containers
- Multi-instance scenarios require careful file locking for `/home`

## 16. Related guide / official docs

- [Operating system functionality on Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/operating-system-functionality)
- [Configure a custom container - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
