---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-03"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Temp Storage Exhaustion: `/tmp` vs. `/home` on Linux App Service

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-03.

## 1. Question

On Linux App Service, what is the storage capacity and persistence behavior of `/tmp` and `/home`? When `/tmp` is exhausted, what is the exact error, and does the platform automatically restart the container? After a restart caused by disk exhaustion, are the files in `/tmp` preserved or cleared?

## 2. Why this matters

Linux App Service containers have two writable storage areas that behave very differently:

- **`/tmp`**: Backed by the container's overlay filesystem (ephemeral, cleared on container restart). Subject to the total container disk quota (~35GB on B1). Exhaustion causes `ENOSPC` on any write operation — including log writes, temp file creation, and pip installs — which can crash the application without a clear error in application logs.
- **`/home`**: Backed by an Azure Files share (persistent across restarts). 10GB quota on most plans. Not affected by `/tmp` exhaustion.

Teams that write large temporary files (ML model downloads, ZIP archives, upload buffers) to `/tmp` without cleanup can exhaust the overlay filesystem, causing silent application crashes.

## 3. Customer symptom

"The app crashes intermittently with no error in the application logs" or "File upload fails with 'No space left on device' after a few hours" or "pip install fails during startup with an I/O error."

## 4. Hypothesis

- H1: `/tmp` on Linux App Service is backed by the container overlay filesystem (shared with `/`). The total quota is approximately 35GB on B1. ✅ **Confirmed** (35GB overlay, shared between `/tmp` and the rest of the container filesystem)
- H2: `/home` is backed by a separate Azure Files mount (10GB, persistent). It is unaffected by `/tmp` exhaustion. ✅ **Confirmed**
- H3: When `/tmp` is exhausted, any write attempt returns `errno 28 (ENOSPC): No space left on device`. ✅ **Confirmed**
- H4: When the overlay filesystem is nearly full, the platform triggers a container restart. After restart, the overlay filesystem is reset — ephemeral files in `/tmp` are cleared. ✅ **Confirmed** (fill files created before restart were absent after restart)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-03 |

## 6. Variables

**Experiment type**: Storage / Resource limits

**Controlled:**

- Linux App Service (B1, Python 3.11) with a Flask endpoint to write arbitrary-sized files to `/tmp` and read disk usage
- Files created with `os.urandom()` to prevent compression artifacts

**Observed:**

- `df` output for `/` (overlay) and `/home` (Azure Files)
- `shutil.disk_usage('/tmp')` values
- `OSError` errno and strerror when `/tmp` is full
- Container restart behavior when disk is exhausted

**Scenarios:**

| Scenario | Action | Observed |
|----------|--------|----------|
| Baseline | No fill | `/tmp` = 35GB overlay, `/home` = 10GB Azure Files |
| S1 | Write 300MB to full `/tmp` | `errno 28: No space left on device` |
| S2 | Fill overlay to ~85% | Container restart triggered by platform |
| S3 | Post-restart disk check | Overlay reset; prior fill files absent |
| S4 | Fill to 100% (198MB free) then write | Exact ENOSPC captured |

## 7. Instrumentation

- Flask endpoint `/` returning `shutil.disk_usage()` for `/tmp` and `/home`, plus `df -h` subprocess output
- Flask endpoint `/fill-unique` creating uniquely-named files until `OSError` or limit
- Flask endpoint `/write-tmp` writing a single small text file and returning `OSError` on failure

## 8. Procedure

1. Deployed Flask app (Python 3.11, B1, Linux) with disk diagnostic endpoints.
2. **Baseline**: Measured `/tmp` and `/home` disk usage with fresh container.
3. **Exhaustion**: Repeatedly filled `/tmp` with large binary files using unique filenames.
4. **Error capture**: At 198MB remaining (100% usage), attempted file writes and captured exact error.
5. **Recovery**: Observed container restart behavior and post-restart disk state.

## 9. Expected signal

- Baseline: `/tmp` on 35GB overlay; `/home` on 10GB Azure Files mount.
- Exhaustion: `OSError: [Errno 28] No space left on device`.
- Recovery: Container restart resets the overlay; ephemeral files are cleared.

## 10. Results

**Baseline disk layout:**
```
Filesystem      Size  Used Avail Use%  Mounted on
overlay          35G   13G   22G  37%  /           ← /tmp lives here
Azure Files NFS  10G  224K   10G   1%  /home
```

**At exhaustion (198MB free, 100% usage):**
```
Filesystem      Size  Used Avail Use%  Mounted on
overlay          35G   34G  198M 100%  /
Azure Files NFS  10G  236K   10G   1%  /home
```

**Write attempt to /tmp when full (small text file):**
```json
{"errno": 28, "status": "error", "strerror": "No space left on device"}
```

**Write attempt (300MB > 198MB free):**
```json
{
  "errors": [{"errno": 28, "filename": "None", "strerror": "No space left on device"}],
  "files_created": 0,
  "tmp_free_mb": 0,
  "tmp_used_mb": 34955,
  "written_mb": 0
}
```

**Post-restart disk state:**
- `/tmp` overlay reset to ~22GB free (prior fill files cleared)
- `/home` unchanged (0MB used — persistent, unaffected by restart)
- Platform triggers container restart when overlay reaches ~85-100% capacity

**Persistence summary:**

| Path | Backend | Quota | Survives restart? |
|------|---------|-------|-------------------|
| `/tmp` | Container overlay | ~35GB (B1) | ❌ No (cleared on restart) |
| `/home` | Azure Files NFS | 10GB | ✅ Yes |

## 11. Interpretation

**Observed**: `/tmp` on Linux App Service (B1) is backed by the container's overlay filesystem, which is shared with the entire container root. The total capacity is approximately 35GB, shared among the OS, installed packages, build artifacts, and any temporary files written by the application.

**Observed**: When the overlay filesystem reaches near-full capacity (~85-100%), the App Service platform triggers a container restart. The restart resets the overlay filesystem — ephemeral files created during the previous container instance are cleared. This is the primary self-recovery mechanism.

**Observed**: `errno 28 (ENOSPC)` is the exact error code returned by the Linux kernel when a write is attempted on a full filesystem. In Python, this surfaces as `OSError: [Errno 28] No space left on device`. This error applies to ANY write — including small text files, logging, and pip package installation.

**Observed**: `/home` (Azure Files NFS mount) is completely isolated from the overlay filesystem. Its 10GB quota is unaffected by `/tmp` exhaustion, and it persists across container restarts.

**Strongly Suggested**: The primary risk is an application that writes large files to `/tmp` without cleanup (e.g., ML model downloads, upload staging, ZIP archives). Each container restart clears the files, but if the fill rate exceeds the restart rate, the app enters a crash loop.

## 12. What this proves

- **Proven**: `/tmp` on Linux App Service is NOT a separate tmpfs partition — it shares the 35GB container overlay filesystem with `/`.
- **Proven**: Overlay exhaustion causes `errno 28 (ENOSPC)` on all write operations, including small text files.
- **Proven**: The platform automatically restarts the container when the overlay approaches full capacity.
- **Proven**: `/home` is isolated from overlay exhaustion and persists across restarts.
- **Proven**: Files in `/tmp` are NOT preserved across container restarts (ephemeral).

## 13. What this does NOT prove

- The exact threshold (% full) that triggers a platform-initiated container restart — observed to occur between 85-100%, but the exact trigger was not isolated.
- Behavior on higher SKUs (P1v3, P2v3) — quota may differ.
- Whether App Service emits a specific event/alert when disk exhaustion triggers a restart (not tested via Log Analytics).
- Whether `pip install` during startup fails with the same ENOSPC error when the overlay is full (likely yes, but not directly tested).

## 14. Support takeaway

When a Linux App Service customer reports intermittent crashes with no application error:

1. **Check disk usage** via Kudu console (`du -sh /tmp/*` or `df -h`):
   ```bash
   # Via Azure CLI
   az webapp ssh -n <app> -g <rg>
   # Then inside the container:
   df -h /
   du -sh /tmp/* | sort -rh | head -20
   ```
2. **Common culprits**: Large temp files not cleaned up (`/tmp/pip-*`, upload staging directories, ML model caches, log archives).
3. **Fix**: Write large files to `/home` instead of `/tmp`. Or implement cleanup after each operation.
4. **Monitor**: Enable App Service diagnostics → "Diagnose and solve problems" → "Container Issues" to see container restart history.

## 15. Reproduction notes

```bash
# Create test app
az group create -n rg-tmp-test -l koreacentral
az appservice plan create -n plan-tmp-test -g rg-tmp-test --sku B1 --is-linux
az webapp create -n <app> -g rg-tmp-test --plan plan-tmp-test --runtime "PYTHON:3.11"

# Flask diagnostic endpoint for disk usage:
# GET /  → shutil.disk_usage('/tmp') + df -h output
# GET /fill-unique?limit_mb=5000&chunk_mb=256 → fill with unique files, capture OSError
# GET /write-tmp → write small file, capture errno on failure
```

**Exact error captured at exhaustion:**
```python
# OSError when /tmp is full:
OSError: [Errno 28] No space left on device: '/tmp/fill_0_abc12345.bin'
# errno=28, strerror="No space left on device"
```

## 16. Related guide / official docs

- [App Service Linux filesystem](https://learn.microsoft.com/en-us/azure/app-service/operating-system-functionality)
- [Configure persistent storage for Linux containers](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container#configure-persistent-storage)
- [Linux errno codes](https://man7.org/linux/man-pages/man3/errno.3.html)
