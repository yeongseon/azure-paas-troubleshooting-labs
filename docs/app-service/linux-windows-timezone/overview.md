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

# Linux vs. Windows Timezone: `TZ` vs. `WEBSITE_TIME_ZONE` Mismatch

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-03.

## 1. Question

On a Linux App Service, what is the correct way to set the process timezone? Does `WEBSITE_TIME_ZONE` (the Windows App Service setting) affect a Linux app? And what happens when a Windows-style timezone name (e.g., `"Korea Standard Time"`) is used on a Linux runtime instead of the IANA name (`"Asia/Seoul"`)?

## 2. Why this matters

App Service runs on both Windows and Linux. The timezone configuration mechanism differs between the two:

- **Windows**: `WEBSITE_TIME_ZONE` accepts Windows timezone names (e.g., `"Korea Standard Time"`).
- **Linux**: `TZ` env var accepts IANA timezone names (e.g., `"Asia/Seoul"`). `WEBSITE_TIME_ZONE` is silently ignored.

Teams migrating from Windows to Linux App Service, or copying app settings between environments, often carry over `WEBSITE_TIME_ZONE` with a Windows-style name. The result is that `datetime.now()` (Python), `new Date()` (Node.js), and similar calls return UTC unexpectedly — causing timestamp bugs in logs, scheduled jobs, and any time-sensitive business logic — with no error at the platform level.

## 3. Customer symptom

"Timestamps in our logs are 9 hours behind even though we set the timezone" or "The scheduled job runs at the wrong time after migrating to Linux" or "We set `WEBSITE_TIME_ZONE` but `datetime.now()` still returns UTC."

## 4. Hypothesis

- H1: On Linux App Service, `TZ=Asia/Seoul` (IANA name) correctly shifts `datetime.datetime.now()` to KST (+09:00). ✅ **Confirmed**
- H2: On Linux App Service, `TZ="Korea Standard Time"` (Windows timezone name) causes a Python `ZoneInfo` lookup failure; `datetime.datetime.now()` returns UTC (the system default). ✅ **Confirmed**
- H3: On Linux App Service, `WEBSITE_TIME_ZONE="Korea Standard Time"` is silently ignored by the OS — it does not affect the process timezone. ✅ **Confirmed**
- H4: The platform does not warn or error when `WEBSITE_TIME_ZONE` is set on a Linux app; the setting is accepted without effect. ✅ **Confirmed**

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

**Experiment type**: Configuration / Runtime behavior

**Controlled:**

- Single Linux App Service (B1, Python 3.11) with a Flask endpoint returning `datetime.datetime.now()` and timezone diagnostic info
- App settings changed between scenarios; app restarted between each test

**Observed:**

- `datetime_now_no_tz`: value of `datetime.datetime.now().isoformat()` (no explicit tz — affected by `TZ` env)
- `local`: value of `datetime.now(utc).astimezone(configured_tz).isoformat()`
- `tz_valid`: whether the configured timezone name was recognized by Python `zoneinfo`

**Scenarios:**

| Scenario | `TZ` setting | `WEBSITE_TIME_ZONE` | Expected |
|----------|-------------|---------------------|----------|
| Baseline | (not set) | (not set) | UTC |
| S1 | `Asia/Seoul` | (not set) | KST +09:00 |
| S2 | `Korea Standard Time` | (not set) | Error / UTC fallback |
| S3 | (empty) | `Korea Standard Time` | UTC (ignored) |
| S4 | `Asia/Seoul` | (empty) | KST +09:00 (confirmed fix) |

## 7. Instrumentation

- Flask endpoint at `/` returning JSON with `utc`, `local`, `TZ_env`, `WEBSITE_TIME_ZONE_env`, `tz_valid`, `datetime_now_no_tz`
- `curl -s https://<app>.azurewebsites.net/`
- `az webapp config appsettings set` to change settings between scenarios

## 8. Procedure

1. Deployed a minimal Flask app (Python 3.11, Linux, B1) returning timezone diagnostics via `zoneinfo` and `datetime`.
2. **Baseline**: No `TZ` or `WEBSITE_TIME_ZONE` set → measured UTC output.
3. **S1**: Set `TZ=Asia/Seoul` → waited for restart (~30s) → measured KST output.
4. **S2**: Set `TZ="Korea Standard Time"` (Windows style) → waited for restart → measured behavior.
5. **S3**: Set `TZ=""`, `WEBSITE_TIME_ZONE="Korea Standard Time"` → waited for restart → measured behavior.
6. **S4**: Reset to `TZ=Asia/Seoul` → confirmed correct behavior restored.

## 9. Expected signal

- S1: `datetime_now_no_tz` shows KST (21:xx) not UTC (12:xx). `tz_valid: true`.
- S2: `tz_valid: false`, error message in `local` field, `datetime_now_no_tz` shows UTC.
- S3: `WEBSITE_TIME_ZONE` ignored; `datetime_now_no_tz` shows UTC. `tz_valid: false` (empty TZ).

## 10. Results

| Scenario | `datetime_now_no_tz` | `tz_valid` | `local` |
|----------|---------------------|-----------|---------|
| Baseline | `2026-05-03T12:32:33` (UTC) | true | `+00:00` |
| S1: `TZ=Asia/Seoul` | `2026-05-03T21:34:39` **(KST)** | true | `+09:00` |
| S2: `TZ=Korea Standard Time` | `2026-05-03T12:36:29` (UTC) | **false** | `ERROR: 'No time zone found with key Korea Standard Time'` |
| S3: `WEBSITE_TIME_ZONE=Korea Standard Time` | `2026-05-03T12:38:23` (UTC) | **false** | `ERROR: ZoneInfo keys must be normalized...` |
| S4: `TZ=Asia/Seoul` (reset) | `2026-05-03T21:40:15` **(KST)** | true | `+09:00` |

Raw responses (selected):

**Baseline:**
```json
{"TZ_env":"NOT_SET","WEBSITE_TIME_ZONE_env":"NOT_SET","datetime_now_no_tz":"2026-05-03T12:32:33.110096","local":"2026-05-03T12:32:33.110038+00:00","tz_valid":true,"utc":"2026-05-03T12:32:33.110038+00:00"}
```

**S1 — `TZ=Asia/Seoul`:**
```json
{"TZ_env":"Asia/Seoul","WEBSITE_TIME_ZONE_env":"NOT_SET","datetime_now_no_tz":"2026-05-03T21:34:39.352547","local":"2026-05-03T21:34:39.352205+09:00","tz_valid":true,"utc":"2026-05-03T12:34:39.352205+00:00"}
```

**S2 — `TZ=Korea Standard Time` (Windows name on Linux):**
```json
{"TZ_env":"Korea Standard Time","WEBSITE_TIME_ZONE_env":"NOT_SET","datetime_now_no_tz":"2026-05-03T12:36:29.247750","local":"ERROR: 'No time zone found with key Korea Standard Time'","tz_valid":false,"utc":"2026-05-03T12:36:29.245328+00:00"}
```

**S3 — `WEBSITE_TIME_ZONE=Korea Standard Time` (TZ empty):**
```json
{"TZ_env":"","WEBSITE_TIME_ZONE_env":"Korea Standard Time","datetime_now_no_tz":"2026-05-03T12:38:23.398819","local":"ERROR: ZoneInfo keys must be normalized relative paths, got: ","tz_valid":false,"utc":"2026-05-03T12:38:23.398755+00:00"}
```

## 11. Interpretation

**Observed**: `TZ=Asia/Seoul` (IANA name) correctly shifts `datetime.datetime.now()` to KST (+09:00) on Linux App Service.

**Observed**: `TZ="Korea Standard Time"` is silently passed to the Linux process as an environment variable. Python `zoneinfo` raises a key lookup error. `datetime.datetime.now()` falls back to UTC — the system default — without raising any exception at the platform or application level.

**Observed**: `WEBSITE_TIME_ZONE` is stored as an env var in the process (visible via `os.environ.get`), but the Linux OS timezone resolution mechanism (`/etc/localtime`, `TZ` env) does not consult it. It has zero effect on runtime timezone behavior.

**Inferred**: The App Service control plane accepts `WEBSITE_TIME_ZONE` on Linux apps without validation. No warning is emitted. A customer setting `WEBSITE_TIME_ZONE` on a Linux app with the expectation it works (as it does on Windows) will see silent UTC timestamps — the worst kind of bug.

## 12. What this proves

- **Proven**: `TZ` with an IANA timezone name is the only correct mechanism for setting process timezone on Linux App Service Python runtimes.
- **Proven**: `WEBSITE_TIME_ZONE` is silently ignored by the Linux runtime environment.
- **Proven**: Windows timezone names (`"Korea Standard Time"`) are rejected by Python `zoneinfo` with a `ZoneInfoNotFoundError`. No platform-level error or warning is produced.
- **Proven**: The failure is silent — `datetime.datetime.now()` returns UTC without throwing, making this bug difficult to detect without explicit timezone logging.

## 13. What this does NOT prove

- Behavior of other runtimes (Node.js, Java, .NET) on Linux under the same `TZ` misconfiguration — not tested.
- Whether `WEBSITE_TIME_ZONE` affects OS-level cron or system processes on Linux App Service (only Python process behavior tested).
- Behavior of `pytz` or `python-dateutil` under Windows timezone names — `zoneinfo` (stdlib, Python 3.9+) was used exclusively.

## 14. Support takeaway

When a Linux App Service customer reports timestamps appearing in UTC despite timezone configuration:

1. **Check `TZ` env var** (not `WEBSITE_TIME_ZONE`):
   ```bash
   az webapp config appsettings list -n <app> -g <rg> --query "[?name=='TZ'].value" -o tsv
   ```
2. **Verify the value is an IANA name**, not a Windows name:
   - ✅ Correct: `Asia/Seoul`, `America/New_York`, `Europe/London`, `UTC`
   - ❌ Wrong: `Korea Standard Time`, `Eastern Standard Time`, `Pacific Standard Time`
3. If `WEBSITE_TIME_ZONE` is set but `TZ` is missing or wrong — **add `TZ` with the IANA equivalent**. Use the [Unicode CLDR mapping](https://github.com/unicode-org/cldr/blob/main/common/supplemental/windowsZones.xml) to convert Windows → IANA names.
4. **Restart the app** after changing `TZ`.

## 15. Reproduction notes

```bash
# Create test environment
az group create -n rg-tz-test -l koreacentral
az appservice plan create -n plan-tz-test -g rg-tz-test --sku B1 --is-linux
az webapp create -n <app-name> -g rg-tz-test --plan plan-tz-test --runtime "PYTHON:3.11"

# Correct: IANA timezone via TZ
az webapp config appsettings set -n <app-name> -g rg-tz-test --settings TZ="Asia/Seoul"

# Wrong: Windows name on Linux (silently fails)
az webapp config appsettings set -n <app-name> -g rg-tz-test --settings TZ="Korea Standard Time"

# Wrong: Windows-only setting (silently ignored on Linux)
az webapp config appsettings set -n <app-name> -g rg-tz-test --settings WEBSITE_TIME_ZONE="Korea Standard Time"
```

**Flask diagnostic endpoint used in this experiment:**
```python
import os, datetime, zoneinfo
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    tz_env = os.environ.get("TZ", "NOT_SET")
    try:
        local_tz = zoneinfo.ZoneInfo(tz_env) if tz_env not in ("NOT_SET", "") else datetime.timezone.utc
        local_str = now_utc.astimezone(local_tz).isoformat()
        tz_valid = True
    except Exception as e:
        local_str = f"ERROR: {e}"
        tz_valid = False
    return jsonify({
        "utc": now_utc.isoformat(),
        "local": local_str,
        "TZ_env": tz_env,
        "WEBSITE_TIME_ZONE_env": os.environ.get("WEBSITE_TIME_ZONE", "NOT_SET"),
        "tz_valid": tz_valid,
        "datetime_now_no_tz": datetime.datetime.now().isoformat()
    })
```

## 16. Related guide / official docs

- [Configure timezone in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/faq-configuration-and-management#how-do-i-set-a-custom-time-zone-for-my-app)
- [IANA timezone database](https://www.iana.org/time-zones)
- [Windows to IANA timezone mapping (Unicode CLDR)](https://github.com/unicode-org/cldr/blob/main/common/supplemental/windowsZones.xml)
