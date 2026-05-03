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

# Linux vs. Windows Timezone Handling: WEBSITE_TIME_ZONE Behavior

!!! info "Status: Planned"

## 1. Question

The `WEBSITE_TIME_ZONE` app setting controls the default timezone for App Service applications. However, this setting uses Windows timezone identifiers on Windows and IANA/tzdata identifiers on Linux — and the two formats are incompatible. What happens when a Windows-format timezone identifier is used on a Linux app, and what observable failures does this cause?

## 2. Why this matters

Teams that migrate applications from Windows App Service to Linux App Service, or that share infrastructure-as-code between Windows and Linux deployments, often copy the `WEBSITE_TIME_ZONE` app setting without adjusting the format. On Linux, an invalid `TZ` value causes the process to fall back to UTC silently. This affects scheduled tasks, cron jobs, log timestamps, and any time-sensitive business logic, causing subtle data inconsistencies that are difficult to trace back to the timezone configuration.

## 3. Customer symptom

"Scheduled tasks run at the wrong time after migrating to Linux" or "Log timestamps are 9 hours off even though we set the timezone correctly" or "The app uses UTC even though `WEBSITE_TIME_ZONE` is set to `Korea Standard Time`."

## 4. Hypothesis

- H1: On Windows App Service, `WEBSITE_TIME_ZONE=Korea Standard Time` (Windows format) correctly sets the process timezone to UTC+9. On Linux App Service, the same value is passed as the `TZ` environment variable, but `Korea Standard Time` is not a valid IANA tzdata identifier. The Linux glibc timezone lookup falls back to UTC silently.
- H2: On Linux App Service, the correct setting is `WEBSITE_TIME_ZONE=Asia/Seoul` (IANA format). This correctly sets the process timezone to UTC+9.
- H3: The fallback to UTC on an invalid `TZ` value produces no error message — the app starts normally and appears configured correctly from the portal perspective. The only indication is that `datetime.now()` returns UTC time instead of local time.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service (Linux and Windows, compared) |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 (Linux), Python 3.11 (Windows) |
| OS | Linux and Windows |
| Date tested | — |

## 6. Variables

**Experiment type**: Configuration / Platform behavior

**Controlled:**

- `WEBSITE_TIME_ZONE` app setting with various values
- Endpoint that returns `datetime.now().isoformat()` (local time) and `datetime.utcnow().isoformat()` (UTC)

**Observed:**

- Reported local time vs. UTC under each timezone setting

**Scenarios:**

- S1: Linux, `WEBSITE_TIME_ZONE=Asia/Seoul` → UTC+9 (correct)
- S2: Linux, `WEBSITE_TIME_ZONE=Korea Standard Time` → UTC fallback (Windows format on Linux)
- S3: Windows, `WEBSITE_TIME_ZONE=Korea Standard Time` → UTC+9 (correct)
- S4: Windows, `WEBSITE_TIME_ZONE=Asia/Seoul` → behavior (IANA on Windows)
- S5: Linux, `WEBSITE_TIME_ZONE` not set → UTC (default)

## 7. Instrumentation

- Application `/time` endpoint returning `datetime.now()` and `os.environ.get('TZ')` and `os.environ.get('WEBSITE_TIME_ZONE')`
- Kudu SSH: `echo $TZ` and `date` command to verify system timezone

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python app with `/time` endpoint on both Linux and Windows App Service.
2. S1: Set `WEBSITE_TIME_ZONE=Asia/Seoul` on Linux; call `/time`; verify UTC+9.
3. S2: Change to `WEBSITE_TIME_ZONE=Korea Standard Time` on Linux; call `/time`; verify fallback to UTC.
4. S3: Set `WEBSITE_TIME_ZONE=Korea Standard Time` on Windows; verify UTC+9.
5. S4: Change to `WEBSITE_TIME_ZONE=Asia/Seoul` on Windows; observe behavior.
6. S5: Remove `WEBSITE_TIME_ZONE` on Linux; verify UTC default.

## 9. Expected signal

- S1: `datetime.now()` returns KST (UTC+9); `TZ=Asia/Seoul` in environment.
- S2: `datetime.now()` returns UTC despite setting; `TZ=Korea Standard Time` in environment but glibc ignores invalid value.
- S3: `datetime.now()` returns KST; Windows timezone lookup works correctly.
- S4: Windows may support IANA identifiers via ICU; behavior is to be observed.
- S5: `datetime.now()` returns UTC.

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

- Linux App Service timezone reference: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
- Windows App Service timezone reference: Windows Registry `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Time Zones`
- The `TZ` environment variable is the POSIX standard for specifying timezone on Linux. App Service sets `TZ` to the value of `WEBSITE_TIME_ZONE` on Linux.

## 16. Related guide / official docs

- [WEBSITE_TIME_ZONE app setting](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings#time-zone)
- [Time zones on Linux vs. Windows App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common)
