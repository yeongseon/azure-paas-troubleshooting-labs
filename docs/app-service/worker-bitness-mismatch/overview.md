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

# 32-bit vs. 64-bit Worker Process: Native Dependency Failures

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Windows App Service allows configuring the worker process bitness (32-bit or 64-bit). On Linux App Service, is the runtime always 64-bit? What does the platform-level bitness look like from within the application process?

## 2. Why this matters

Many enterprise applications depend on native COM components, native database drivers (Oracle ODP.NET native), or cryptographic libraries compiled for a specific CPU architecture. On Windows App Service, the default worker process is 32-bit for legacy compatibility reasons. Teams that migrate from IIS servers (which default to 64-bit) encounter `BadImageFormatException` or `DllNotFoundException` errors that are specific to this bitness mismatch. On Linux App Service, there is no 32-bit option — but customers migrating from Windows sometimes assume they need to configure bitness. This experiment confirms the Linux baseline.

## 3. Customer symptom

"The app deploys correctly but crashes immediately with a `BadImageFormatException`" or "`DllNotFoundException` for a library that clearly exists in the deployment package" or "The app runs on our IIS server but fails on App Service with the same code."

## 4. Hypothesis

- H1: Linux App Service always runs a 64-bit process; `sys.maxsize > 2**32` is `True` and `struct.calcsize("P") * 8` equals 64. ✅ **Confirmed**
- H2: The platform architecture on Linux App Service is `x86_64`. ✅ **Confirmed**
- H3: The Linux kernel version and glibc version are visible from `platform.platform()`. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (Basic, Linux) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Runtime / Configuration

**Controlled:**

- Python 3.11 Flask app deployed via ZIP deploy
- Endpoint `/` returns `platform`, `machine`, `bits`, `maxsize`, `is_64bit`

**Observed:**

- `platform.machine()` — CPU architecture string
- `struct.calcsize("P") * 8` — pointer size in bits (definitive bitness indicator)
- `sys.maxsize` — maximum integer value (>2^32 for 64-bit)
- `platform.platform()` — full OS/kernel/glibc string

## 7. Instrumentation

- Flask app endpoint returning `json.dumps` of `platform.*` and `sys.*` values
- `curl -s https://<app>.azurewebsites.net/` — direct JSON response

## 8. Procedure

1. Added to Flask app: `platform.platform()`, `platform.machine()`, `struct.calcsize("P") * 8`, `sys.maxsize`, `sys.maxsize > 2**32`.
2. Redeployed via ZIP.
3. Queried `GET /` and recorded JSON response.

## 9. Expected signal

- `machine`: `x86_64`
- `bits`: `64`
- `is_64bit`: `true`
- `maxsize`: `9223372036854775807` (2^63 - 1)
- `platform` string containing kernel version and glibc version

## 10. Results

```json
{
  "bits": 64,
  "is_64bit": true,
  "machine": "x86_64",
  "maxsize": 9223372036854775807,
  "platform": "Linux-6.6.126.1-1.azl3-x86_64-with-glibc2.31",
  "python": "3.11.14 (main, Oct 14 2025, 15:29:35) [GCC 10.2.1 20210110]",
  "status": "ok"
}
```

Worker endpoint (`/worker`):

```json
{
  "bits": 64,
  "cpu_count": 1,
  "hostname": "31991dac338a",
  "pid": 1894,
  "platform": "x86_64",
  "ppid": 1891
}
```

## 11. Interpretation

- **Measured**: Linux App Service (B1) runs a 64-bit process. `struct.calcsize("P") * 8 = 64` and `sys.maxsize = 9223372036854775807` (2^63 - 1) definitively confirm 64-bit pointer width.
- **Observed**: The machine architecture is `x86_64`. The platform is Azure Linux 3 (`azl3`) running kernel `6.6.126.1-1.azl3` with glibc 2.31.
- **Observed**: `cpu_count` is 1 on a B1 plan (1 vCPU).
- **Inferred**: There is no 32-bit option on Linux App Service. The `Platform` general setting (32-bit/64-bit) in the portal only applies to Windows App Service workers. On Linux, the setting has no effect — the container always runs x86_64.

## 12. What this proves

- Linux App Service always runs a 64-bit (x86_64) process on B1.
- Python `sys.maxsize` and `struct.calcsize("P") * 8` are reliable bitness indicators from within the app.
- The Linux kernel version (`6.6.126.1-1.azl3`) and glibc version (`2.31`) are visible to the application.

## 13. What this does NOT prove

- Windows App Service bitness behavior (`BadImageFormatException` for 32-bit/64-bit mismatch) was **Not Tested** — Windows runtime was out of scope for this lab environment (Linux-only B1 plan).
- ARM64 architecture availability on App Service was **Not Tested**.
- The 32-bit portal setting on Windows plans was **Not Tested**.

## 14. Support takeaway

- Customer on Linux App Service asking about bitness mismatch: Linux always runs 64-bit. `BadImageFormatException` on Linux is unlikely to be a bitness issue — more likely a wrong platform target (e.g., `win-x64` native binary on Linux).
- Customer on Windows App Service with `BadImageFormatException`: check **Configuration > General settings > Platform**. Default is 32-bit. Change to 64-bit and restart.
- To check bitness from Python: `import struct; print(struct.calcsize("P") * 8)` — returns 32 or 64.
- The platform string `Linux-6.6.126.1-1.azl3-x86_64-with-glibc2.31` identifies the Azure Linux 3 host kernel, useful for narrowing compatibility issues with native extensions.

## 15. Reproduction notes

```python
import platform, struct, sys

print(platform.machine())         # x86_64 on Linux App Service
print(struct.calcsize("P") * 8)   # 64
print(sys.maxsize > 2**32)        # True (64-bit)
print(platform.platform())        # Full OS/kernel/glibc string
```

```bash
# Query from deployed Flask app
curl -s https://<app>.azurewebsites.net/ | python3 -m json.tool
```

## 16. Related guide / official docs

- [Configure an App Service app in the Azure portal](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [BadImageFormatException class](https://learn.microsoft.com/en-us/dotnet/api/system.badimageformatexception)
- [Python platform module](https://docs.python.org/3/library/platform.html)
