---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-10
    cli_version: "2.73.0"
    core_tools_version: null
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Linux /home vs Writable Layer Persistence

!!! info "Status: Published"
    Experiment completed with real data collected on 2026-04-10 from Azure App Service B1 (koreacentral).
    All three hypotheses confirmed with evidence from 4 trigger events across 2 instances.

## 1. Question

On App Service Linux, what is the persistence behavior difference between the `/home` mount and the container's writable layer, and does data written to each survive restarts, deployments, and scale operations?

## 2. Why this matters

Customers often store temporary files, caches, or user uploads on the local filesystem without understanding which paths persist across restarts and which are ephemeral. Losing files after a deployment or instance migration causes data loss incidents that are difficult to debug because the app appears functional.

### Background: How the Filesystem Works on App Service Linux

Azure App Service Linux runs each app inside a Docker container. The container's filesystem is an **overlay** composed of read-only image layers plus a thin writable layer on top. This writable layer is where files written to paths like `/tmp` or `/var/local` end up.

Separately, Azure mounts a **CIFS (SMB 3.1.1) share** from Azure Storage at `/home`. This mount is persistent, shared across all instances of the same app, and survives container recreation.

**Key architecture:**

```text
┌─────────────────────────────────────────┐
│  Container (overlay filesystem)         │
│  ├── / (read-only image layers)         │
│  ├── /tmp (writable layer - ephemeral)  │
│  ├── /var/local (writable - ephemeral)  │
│  └── /home (CIFS mount - persistent)    │
│       └── Azure Storage SMB share       │
└─────────────────────────────────────────┘
```

**What this means for developers:**

- Files in `/home` are backed by Azure Storage and persist across container restarts, deployments, and scale events
- Files outside `/home` exist only in the container's overlay writable layer and are lost whenever the container is recreated
- The I/O performance characteristics differ dramatically: `/home` writes go over the network to Azure Storage, while local writes hit the container's overlay on local disk

## 3. Customer symptom

- "Files uploaded by users disappear after we deploy a new version."
- "Our cache directory is empty after the app restarts."
- "Some files survive restarts but others don't — we don't understand the pattern."
- "The same file is visible on one instance but not another in a scaled-out app."

## 4. Hypothesis

On App Service Linux:

1. **H1**: Files written to `/home` persist across restarts and deployments because `/home` is backed by Azure Storage (CIFS mount).
2. **H2**: Files written outside `/home` (e.g., `/tmp`, `/var/local`) are lost when the container is recreated (stop/start, deployment) because they exist only in the container's writable overlay layer.
3. **H3**: During scale-out, new instances can access `/home` files (shared storage) but cannot see files written to the writable layer of other instances (instance-local storage).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 Linux (1 vCPU, 1.75 GB RAM) |
| Region | Korea Central |
| Runtime | Python 3.11.14 |
| OS | Linux |
| Deployment method | ZIP Deploy |
| Date tested | 2026-04-10 |
| Instance count | 1 → 2 (scaled during experiment) |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Write locations: `/home/data/`, `/tmp/data/`, `/var/local/data/`
- File content: JSON payload with instance ID, hostname, PID, timestamp, marker
- Integrity verification: SHA-256 checksum written alongside each file
- Trigger events: `az webapp restart`, `az webapp stop` + `az webapp start`, `az webapp deploy` (ZIP), scale-out to 2 instances

**Observed:**

- File existence after each trigger event
- File content integrity (SHA-256 checksum match)
- Container hostname changes (indicates container recreation)
- Instance ID changes (indicates instance migration)
- `/home` mount type and backing storage details
- I/O write/read latency for each path (4 KB payload, 10 iterations with `fsync`)

## 7. Instrumentation

- **Test application**: Custom Flask app with `/write`, `/read`, `/mount-info`, `/io-latency` endpoints
- **Deployment**: ZIP deploy via `az webapp deploy`
- **File verification**: SHA-256 checksum comparison
- **Instance identification**: `WEBSITE_INSTANCE_ID` environment variable + container hostname
- **Mount inspection**: `df -h` and `mount` commands via app endpoint
- **I/O measurement**: `time.perf_counter()` around file operations with `os.fsync()`

## 8. Procedure

### Step 1: Deploy test infrastructure

```bash
# Create resource group and B1 plan
az group create --name rg-fs-persistence-lab --location koreacentral
az appservice plan create --name plan-fs-persistence \
    --resource-group rg-fs-persistence-lab --sku B1 --is-linux

# Create Python 3.11 web app
az webapp create --name app-fs-persistence-lab \
    --resource-group rg-fs-persistence-lab \
    --plan plan-fs-persistence --runtime "PYTHON:3.11"

# Set startup command and deploy
az webapp config set --name app-fs-persistence-lab \
    --resource-group rg-fs-persistence-lab \
    --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"
az webapp deploy --name app-fs-persistence-lab \
    --resource-group rg-fs-persistence-lab \
    --src-path fs-persistence-app.zip --type zip
```

### Step 2: Establish baseline

1. Call `/write` to create test files in all 3 locations
2. Call `/read` to verify all files exist with valid checksums
3. Call `/mount-info` to capture filesystem mount details
4. Call `/io-latency` to measure baseline I/O performance
5. Record container hostname and instance ID

### Step 3: Test restart persistence

1. Execute `az webapp restart` → check files (soft restart)
2. Execute `az webapp stop` + `az webapp start` → check files (container recreation)

### Step 4: Test deployment persistence

1. Write fresh files to all 3 locations
2. Execute `az webapp deploy` with the same ZIP
3. Wait for new container to start
4. Call `/read` to check which files survived

### Step 5: Test scale-out visibility

1. Write fresh files on current instance
2. Scale plan to 2 instances: `az appservice plan update --number-of-workers 2`
3. Disable ARR affinity: `az webapp update --client-affinity-enabled false`
4. Send requests until hitting both instances
5. Compare file visibility between instances

## 9. Expected signal

- Files in `/home` survive all trigger events (restart, stop/start, deploy, scale-out)
- Files outside `/home` are lost on container recreation (stop/start, deploy)
- New scale-out instances can see `/home` files but not local-layer files from other instances
- `az webapp restart` (soft restart) may preserve the container, keeping all files intact
- `/home` write latency is significantly higher than local filesystem due to CIFS mount

## 10. Results

### 10.1 Mount Information

The `/mount-info` endpoint revealed the actual filesystem architecture:

```text
# /home mount - Azure Storage CIFS
//10.1.160.32/volume-18-default/...  10G  164K  10G  1%  /home
Type: cifs (rw,relatime,vers=3.1.1,cache=strict)

# Root filesystem - overlay (container writable layer)
overlay  35G  20G  15G  58%  /
Type: overlay (rw,relatime,lowerdir=122:...:41,upperdir=/mnt/lwasv2/container/...)
```

!!! note "Key finding"
    `/home` is a **CIFS (SMB 3.1.1)** mount backed by Azure Storage with 10 GB capacity.
    The root filesystem (`/`, `/tmp`, `/var/local`) uses Docker's **overlay2** driver with
    the writable layer stored at `/mnt/lwasv2/container/<app-name>/upper`.

### 10.2 I/O Latency

4 KB payload, 10 iterations per location, with `fsync()`:

| Location | Instance | Write Median (ms) | Write Min (ms) | Write Max (ms) | Read Median (ms) |
|---|---|---|---|---|---|
| `/home/data` | Instance 1 | **62.3** | 45.1 | 111.0 | 0.018 |
| `/tmp/data` | Instance 1 | **0.35** | 0.32 | 1.32 | 0.018 |
| `/var/local/data` | Instance 1 | **0.33** | 0.30 | 0.79 | 0.018 |
| `/home/data` | Instance 2 | **154.8** | 87.9 | 199.2 | 0.052 |
| `/tmp/data` | Instance 2 | **11.8** | 1.21 | 29.4 | 0.041 |
| `/var/local/data` | Instance 2 | **19.9** | 2.86 | 40.3 | 0.030 |

!!! warning "Performance gap"
    `/home` write latency is **~180x slower** than local filesystem on Instance 1 (62ms vs 0.35ms).
    Instance 2 showed even higher latencies across all paths, likely due to being on a different
    physical host (AZ2 vs AZ3) with different storage proximity.

### 10.3 Persistence Test Results

#### Soft Restart (`az webapp restart`)

| Location | File Exists | Checksum Valid | Container Changed |
|---|---|---|---|
| `/home/data` | ✅ Yes | ✅ Yes | No (`65925f18fa71`) |
| `/tmp/data` | ✅ Yes | ✅ Yes | No |
| `/var/local/data` | ✅ Yes | ✅ Yes | No |

!!! tip "How to read this"
    `az webapp restart` performs a **soft restart** — it restarts the application process
    (gunicorn) but does NOT recreate the container. The container hostname remained
    `65925f18fa71`, confirming the same container was reused. All files survived because
    the overlay writable layer was not destroyed.

#### Stop + Start (`az webapp stop` → `az webapp start`)

| Location | File Exists | Checksum Valid | Container Changed |
|---|---|---|---|
| `/home/data` | ✅ Yes | ✅ Yes | **Yes** (`65925f18fa71` → `b7803a4a7d99`) |
| `/tmp/data` | ❌ **No** | — | **Yes** |
| `/var/local/data` | ❌ **No** | — | **Yes** |

!!! tip "How to read this"
    Stop + Start **recreates the container** (hostname changed from `65925f18fa71` to
    `b7803a4a7d99`). The WEBSITE_INSTANCE_ID remained the same (`ede6ac89...`), meaning
    the request landed on the same VM — but a fresh container was created on that VM.
    Only `/home` data survived because it's backed by the Azure Storage CIFS mount.

#### Deployment (ZIP Deploy)

| Location | File Exists | Checksum Valid | Container Changed |
|---|---|---|---|
| `/home/data` | ✅ Yes | ✅ Yes | **Yes** (`b7803a4a7d99` → `d21f8f8bdd92`) |
| `/tmp/data` | ❌ **No** | — | **Yes** |
| `/var/local/data` | ❌ **No** | — | **Yes** |

!!! tip "How to read this"
    ZIP deployment also triggers container recreation. The new container (`d21f8f8bdd92`)
    could read the `/home/data` file written by the previous container (`b7803a4a7d99`),
    proving `/home` persistence across deployments.

#### Scale-Out (1 → 2 instances)

**Instance 1** (original, `ede6ac89...`, hostname `d21f8f8bdd92`, zone: koreacentral-az3):

| Location | File Exists | Checksum Valid |
|---|---|---|
| `/home/data` | ✅ Yes | ✅ Yes |
| `/tmp/data` | ✅ Yes | ✅ Yes |
| `/var/local/data` | ✅ Yes | ✅ Yes |

**Instance 2** (new, `2ebaea0b...`, hostname `7b391c89b135`, zone: koreacentral-az2):

| Location | File Exists | Written By |
|---|---|---|
| `/home/data` | ✅ **Yes** | Instance 1 (`d21f8f8bdd92`) — **cross-instance visible** |
| `/tmp/data` | ❌ **No** | — |
| `/var/local/data` | ❌ **No** | — |

!!! tip "How to read this"
    The new instance (on a different VM in a different availability zone) could read
    the `/home/data` file written by Instance 1, confirming that `/home` is a **shared
    Azure Storage mount** accessible by all instances. The `/tmp` and `/var/local` files
    from Instance 1 were not visible on Instance 2 because each instance has its own
    container with its own overlay writable layer.

### 10.4 Summary Matrix

| Trigger Event | `/home/data` | `/tmp/data` | `/var/local/data` | Container Recreated |
|---|---|---|---|---|
| Soft restart (`az webapp restart`) | ✅ Persists | ✅ Persists | ✅ Persists | No |
| Stop + Start | ✅ Persists | ❌ Lost | ❌ Lost | **Yes** |
| ZIP Deploy | ✅ Persists | ❌ Lost | ❌ Lost | **Yes** |
| Scale-out (new instance) | ✅ Visible | ❌ Not visible | ❌ Not visible | N/A (new container) |

## 11. Interpretation

All three hypotheses are **confirmed**:

**H1 confirmed**: `/home` files persisted across every trigger event — restart, stop/start, deployment, and scale-out. The mount info confirms `/home` is backed by an Azure Storage CIFS (SMB 3.1.1) share at `//10.1.160.32/volume-18-default/...` with 10 GB capacity.

**H2 confirmed**: Files written to `/tmp` and `/var/local` were lost whenever the container was recreated (stop/start, deployment). The only exception was `az webapp restart`, which performs a soft restart without recreating the container.

**H3 confirmed**: A new instance added during scale-out could read `/home` files written by the original instance, but could not see `/tmp` or `/var/local` files. The two instances were in different availability zones (az3 and az2), confirming that `/home` is a network-attached shared mount, not local storage.

### Unexpected Finding: Soft Restart Behavior

`az webapp restart` does **not** recreate the container — it only restarts the application process inside the existing container. This means:

- The container hostname remains unchanged
- All writable layer files survive
- This is a fundamentally different operation from stop+start or deployment

This distinction is critical for troubleshooting: if a customer reports files surviving a "restart" but not a "deployment," it's because these operations have different container lifecycle impacts.

### I/O Performance Implications

The `/home` CIFS mount introduces significant write latency overhead:

- **Instance 1**: `/home` write = 62ms median vs `/tmp` write = 0.35ms (**~180x slower**)
- **Instance 2**: `/home` write = 155ms median vs `/tmp` write = 12ms (**~13x slower**)
- Read latency is comparable across all paths (sub-millisecond) due to page caching

Applications that perform frequent writes (logging, caching, session storage) should use `/tmp` for performance-sensitive operations and only use `/home` for data that must persist. However, they must accept that `/tmp` data will be lost on any container recreation event.

## 12. What this proves

!!! success "Evidence level: Direct observation"

1. `/home` is a **CIFS (SMB 3.1.1)** mount backed by Azure Storage, confirmed by `mount` output
2. `/home` files persist across **all tested lifecycle events**: soft restart, stop/start, deployment, scale-out
3. Files outside `/home` exist only in the container's **overlay writable layer** and are lost on container recreation
4. `az webapp restart` performs a **soft restart** that does not recreate the container
5. `az webapp stop` + `az webapp start` and `az webapp deploy` **recreate** the container
6. `/home` is a **shared mount** visible to all instances of the same app across availability zones
7. `/home` write latency is **62–155ms** (median) vs **0.3–20ms** for local overlay — a 10–180x difference

## 13. What this does NOT prove

- **Custom container behavior**: This experiment used a built-in runtime (Python 3.11). Custom Docker containers may behave differently, especially regarding `WEBSITES_ENABLE_APP_SERVICE_STORAGE` setting.
- **Concurrent write safety**: We did not test concurrent writes to the same `/home` file from multiple instances. CIFS mounts may have locking and consistency issues under concurrent access.
- **Large file behavior**: The test used small JSON files (~239 bytes). Large file operations (>100 MB) may exhibit different latency patterns due to CIFS buffering and network constraints.
- **`az webapp restart` guarantee**: The soft restart behavior (container preservation) may be an implementation detail, not a guaranteed API contract. Future platform changes could alter this behavior.
- **Swap and scale-in behavior**: We did not test what happens when instances are removed during scale-in or during platform-initiated instance migrations.

## 14. Support takeaway

!!! abstract "For support engineers"

    **When a customer reports "files disappearing after deployment":**

    1. Ask which path they're writing to
    2. If it's anything other than `/home` → explain that only `/home` persists across deployments
    3. If it IS `/home` and files still disappear → investigate Azure Storage mount health

    **Key guidance:**

    - Use `/home` for **persistent data** (uploads, user content, configuration)
    - Use `/tmp` for **performance-sensitive ephemeral data** (caches, temp files, session data)
    - **Never** rely on `az webapp restart` preserving files — while it currently preserves the container, this is not a guaranteed behavior
    - For multi-instance apps, remember that `/home` is shared but has **no file locking** by default — implement application-level locking if needed
    - The write latency difference (62ms vs 0.35ms) means **do not put SQLite databases or write-heavy logs on `/home`**

## 15. Reproduction notes

- `/home` is an Azure Storage-backed CIFS (SMB 3.1.1) mount with `cache=strict` mode
- The CIFS mount options include `nobrl` (no byte-range locks) and `mfsymlinks` (Minshall+French symlinks)
- `WEBSITES_ENABLE_APP_SERVICE_STORAGE` setting affects `/home` mount behavior on custom containers (default: true for built-in runtimes)
- I/O latency varies significantly across instances and availability zones
- Multi-instance scenarios require application-level file locking for `/home` writes
- The test application source code is available in the `data/app-service/filesystem-persistence/` directory

## 16. Related guide / official docs

- [Operating system functionality on Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/operating-system-functionality)
- [Configure a custom container - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
- [Understanding the Azure App Service file system](https://github.com/projectkudu/kudu/wiki/Understanding-the-Azure-App-Service-file-system)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
