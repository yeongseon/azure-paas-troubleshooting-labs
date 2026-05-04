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

# Windows vs Linux App Service Behavioral Differences

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution across both Windows and Linux App Service plans.

## 1. Question

What are the observable behavioral differences between Windows and Linux App Service plans for the same application workload? Which differences are diagnostic traps — cases where a behavior expected on one platform is silently different on the other?

## 2. Why this matters

Many App Service support cases originate from unexpected behavior when an application is migrated from Windows to Linux (or vice versa), or when support engineers apply debugging techniques specific to one platform to the other. Critical differences in file system case sensitivity, environment variable availability, diagnostic endpoint behavior, and container model affect both debugging and application correctness.

## 3. Customer symptom

- "The app works on Windows but fails on Linux — same code, same settings."
- "I can't find the App Service Editor on Linux."
- "On Linux, `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` doesn't work."
- "Windows shows me the process list in Kudu but Linux doesn't."
- "File paths work differently — some files are missing on Linux."

## 4. Hypothesis

**H1 — Filesystem case sensitivity**: Linux App Service uses a case-sensitive filesystem. Windows uses case-insensitive NTFS. Code with inconsistent file path casing works on Windows and fails on Linux.

**H2 — Environment variable differences**: Certain `WEBSITE_*` and `APPSETTING_*` environment variables are injected differently or not at all on Linux vs. Windows. The `APPSETTING_` prefix wrapper present on Windows is absent on Linux.

**H3 — Kudu surface differences**: Kudu on Windows provides the App Service Editor, Process Explorer, and CMD console. Kudu on Linux provides SSH (Bash shell) only — no App Service Editor, no Process Explorer.

**H4 — IIS presence**: Windows App Service runs IIS as the reverse proxy; Linux runs a custom proxy (Oryx/custom container). `X-ARR-SSL`, `X-Original-URL`, and certain IIS-specific headers are Windows-only.

**H5 — Startup command differences**: On Linux, the `STARTUP_FILE` or `startupCommand` setting specifies the entrypoint. On Windows, `web.config` controls IIS HTTP handler mapping. The same app requires different startup configuration on each platform.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Windows vs B1 Linux (same region) |
| Region | Korea Central |
| Runtime | Python 3.11 (both) |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Platform Comparison

**Controlled:**

- Application code (identical Python Flask app deployed to both)
- App settings (identical values on both)
- SKU tier (B1 on both)

**Observed:**

- Environment variables present on each platform
- Kudu feature availability
- HTTP headers injected by the platform
- Filesystem case sensitivity behavior
- Startup command requirements

## 7. Instrumentation

- Diagnostic endpoint: `GET /env` dumps all environment variables
- Header endpoint: `GET /headers` dumps all request headers
- File test endpoint: `GET /file-test` attempts both `README.md` and `readme.md`
- Kudu API: `https://<app>.scm.azurewebsites.net/api/diagnostics/processes` (Windows) vs. SSH Bash (Linux)

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
# Windows plan
az appservice plan create --name plan-win --resource-group rg-platform-diff \
  --sku B1 --location koreacentral
az webapp create --name app-win-diff --resource-group rg-platform-diff \
  --plan plan-win --runtime "PYTHON:3.11"

# Linux plan  
az appservice plan create --name plan-linux --resource-group rg-platform-diff \
  --sku B1 --location koreacentral --is-linux
az webapp create --name app-linux-diff --resource-group rg-platform-diff \
  --plan plan-linux --runtime "PYTHON:3.11"
```

### 8.2 Scenarios

**S1 — Environment variable comparison**: Deploy identical app to both. Compare `GET /env` output. Identify variables present on one but not the other.

**S2 — Header injection**: Send HTTP request to both. Compare headers received by the application. Look for IIS-specific headers on Windows.

**S3 — Case sensitivity**: Create a file named `Data.json`. Attempt to open `data.json` (lowercase) via code. Observe success (Windows, case-insensitive) vs. failure (Linux, case-sensitive).

**S4 — Kudu surface**: Document available Kudu endpoints on each platform. Identify diagnostic capabilities exclusive to Windows.

**S5 — Startup command**: Deploy the same app with identical `startupCommand`. Observe whether both platforms interpret the command identically.

## 9. Expected signal

- **S1**: Windows injects `APPSETTING_*` wrappers; Linux does not. `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` is Windows-specific.
- **S2**: `X-ARR-SSL`, `X-Original-URL` present on Windows; absent or different on Linux.
- **S3**: `data.json` open fails on Linux (FileNotFoundError); succeeds on Windows.
- **S4**: App Service Editor unavailable on Linux Kudu. Process Explorer (Windows-only).
- **S5**: `startupCommand` behavior differs — Windows may require full `python -m flask run` while Linux uses it as Docker CMD override.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Python runtime may behave differently from Node.js or .NET on the same platform — this experiment focuses on Python.
- Windows App Service on B1 tier uses shared workers; some behaviors may differ on dedicated tiers.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Linux filesystem is case-sensitive | **Observed** (well-documented) |
| `APPSETTING_` prefix differs between platforms | **Strongly Suggested** |
| Kudu Process Explorer is Windows-only | **Observed** |

## 14. Related experiments

- [Linux Windows Timezone](../zip-vs-container/overview.md) — timezone handling differences
- [Worker Bitness Mismatch](../zip-vs-container/overview.md) — 32-bit vs 64-bit worker issues
- [procfs Interpretation](../procfs-interpretation/overview.md) — Linux-specific /proc filesystem behavior

## 15. References

- [App Service on Linux FAQ](https://learn.microsoft.com/en-us/azure/app-service/faq-app-service-linux)
- [Configure a Linux Python app](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)

## 16. Support takeaway

When troubleshooting platform migration issues (Windows to Linux or vice versa):

1. Always verify the platform with `WEBSITE_OS_NAME` or check Kudu — Windows Kudu has Process Explorer and App Service Editor; Linux Kudu has SSH only.
2. Filesystem case sensitivity is the most common silent breakage on Windows-to-Linux migration. Ask the customer to grep for mixed-case file references in their code.
3. `APPSETTING_` prefix wrappers exist on Windows but not Linux. Code that reads `os.environ.get("APPSETTING_MY_KEY")` works on Windows, fails silently on Linux.
4. IIS-specific headers (`X-ARR-SSL`, `X-Original-URL`) are injected by IIS on Windows. Linux uses a different reverse proxy and these headers may not be present.
