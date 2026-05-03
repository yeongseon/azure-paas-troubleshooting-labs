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

# 32-bit vs. 64-bit Worker Process: Native Dependency Failures

!!! info "Status: Planned"

## 1. Question

Windows App Service allows configuring the worker process bitness (32-bit or 64-bit). When a .NET application has a dependency on a native library (DLL) compiled for a specific architecture, and the worker process bitness does not match, what is the exact failure mode and how does it manifest?

## 2. Why this matters

Many enterprise applications depend on native COM components, native database drivers (Oracle ODP.NET native), or cryptographic libraries compiled for a specific CPU architecture. On Windows App Service, the default worker process is 32-bit for legacy compatibility reasons. Teams that migrate from IIS servers (which default to 64-bit) encounter `BadImageFormatException` or `DllNotFoundException` errors that are specific to this bitness mismatch. The fix (changing the platform setting) is simple but the error message is opaque.

## 3. Customer symptom

"The app deploys correctly but crashes immediately with a `BadImageFormatException`" or "`DllNotFoundException` for a library that clearly exists in the deployment package" or "The app runs on our IIS server but fails on App Service with the same code."

## 4. Hypothesis

- H1: When the worker process is 32-bit and the application tries to load a 64-bit native DLL, the CLR throws `BadImageFormatException` with the message "An attempt was made to load a program with an incorrect format." The reverse (64-bit process, 32-bit DLL) produces the same exception.
- H2: When the worker process is 32-bit, the application's memory address space is limited to 4GB (effectively 1.3–3GB per process usable). Memory-intensive applications that exceed this limit throw `OutOfMemoryException` even when the host has physical memory available.
- H3: Changing **Configuration > General settings > Platform** to 64-bit and restarting resolves `BadImageFormatException` caused by bitness mismatch. No code change is required.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | .NET 8 |
| OS | Windows |
| Date tested | — |

## 6. Variables

**Experiment type**: Runtime / Configuration

**Controlled:**

- A test 64-bit native DLL (`DllImport` test library)
- Worker process set to 32-bit and 64-bit alternately

**Observed:**

- Exception type and message when bitness mismatches
- Success when bitness matches

**Scenarios:**

- S1: 32-bit worker, 64-bit native DLL → `BadImageFormatException`
- S2: 64-bit worker, 64-bit native DLL → success
- S3: 32-bit worker, allocate >2GB memory → `OutOfMemoryException`
- S4: 64-bit worker, allocate >2GB memory → success (up to SKU memory limit)

## 7. Instrumentation

- Application exception message (`BadImageFormatException.Message`, `HResult`)
- `AppServiceConsoleLogs` for unhandled exception stack traces
- Kudu process explorer: worker process bitness visible in `w3wp.exe` process details
- Kudu SSH or PowerShell: `[System.Environment]::Is64BitProcess`

## 8. Procedure

_To be defined during execution._

### Sketch

1. Compile a minimal native DLL targeting x64; create a .NET app that `DllImport`s it.
2. S1: Set platform to 32-bit; deploy; load the DLL → catch and report `BadImageFormatException`.
3. S2: Change to 64-bit in portal; restart; retry → success.
4. S3: 32-bit worker, endpoint that allocates memory in 256MB chunks until OOM → record threshold.
5. S4: 64-bit worker, repeat memory allocation → record threshold (should be much higher).

## 9. Expected signal

- S1: `BadImageFormatException: An attempt was made to load a program with an incorrect format.` (HRESULT 0x8007000B).
- S2: Native library loads successfully; no exception.
- S3: `OutOfMemoryException` at approximately 1.3–2GB allocated (32-bit virtual address space limit).
- S4: `OutOfMemoryException` only at or near the SKU's memory limit (P1v3: 8GB).

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

- Platform bitness is set under **Configuration > General settings > Platform** (32-bit / 64-bit). Default is 32-bit.
- Linux App Service always runs 64-bit; this issue is Windows-specific.
- Check process bitness in Kudu PowerShell: `[System.Environment]::Is64BitProcess` returns `False` for 32-bit.

## 16. Related guide / official docs

- [Configure an App Service app in the Azure portal](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [BadImageFormatException class](https://learn.microsoft.com/en-us/dotnet/api/system.badimageformatexception)
