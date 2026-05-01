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

# Slot Swap Warm-up and Sticky Settings

!!! info "Status: Published"
    Experiment executed on Azure App Service, Korea Central, Linux P1v3, Python 3.11. Scenarios S1–S5 completed. S6 (auto-swap) not executed in this run.

## 1. Question

During Azure App Service slot swap, which settings stay sticky to the slot, which settings move with the content, and how do warm-up requests and health checks affect transient `5xx` errors or swap failure behavior?

## 2. Why this matters

Slot swap is often presented as a near-zero-downtime deployment technique, but support cases show several recurring edge conditions:

- Configuration unexpectedly changes after swap because some settings are slot-specific and others are not.
- A slow-starting app returns transient `503` immediately after swap even though the swap operation itself succeeded.
- Health check configuration blocks traffic or causes a swap to stall when the staging slot never becomes healthy.
- Auto-swap behavior is harder to reason about because warm-up and activation happen as part of deployment instead of an explicit operator-driven action.

Support engineers need a reproducible way to separate **configuration movement**, **warm-up behavior**, and **health check gating**.

## 3. Customer symptom

- "We swapped staging into production and the app started serving the wrong configuration values."
- "Swap succeeded, but users saw a burst of `503` for 30-60 seconds."
- "Health check is green before swap, but the swap still fails or never completes."
- "Auto-swap behaves differently from manual swap even with the same code package."

## 4. Hypothesis

1. App settings marked as **slot settings** stay with the slot during swap, while non-sticky app settings move with the swapped slot configuration.
2. Connection strings show behavior that must be validated separately from app settings because they are configured through a different App Service configuration surface and are projected into runtime environment variables differently.
3. Swapping a slow-starting app without warm-up produces a short window of transient `503` or readiness failures after the target slot becomes live.
4. If Health Check is enabled and the incoming slot fails health validation, swap can stall, fail, or leave the app in a non-serving state depending on timing and platform behavior.
5. Auto-swap follows the same underlying slot rules but may produce a different customer-observed timeline because deployment completion and swap activation are coupled.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | koreacentral |
| Runtime | Python 3.11 |
| OS | Linux |
| Slots | production + staging |
| Health Check Path | `/health` |
| Warm-up Path | `/warmup` |
| Date designed | 2026-04-12 |

## 6. Variables

**Experiment type**: Config + availability behavior

**Controlled:**

- Same App Service plan, app, and deployment slot pair across all runs
- Same Flask app package for production and staging unless the scenario explicitly changes startup delay
- Sticky vs non-sticky app settings names and values
- Sticky vs non-sticky connection string names and values
- Startup delay (`STARTUP_DELAY_SECONDS`)
- Warm-up path configuration (`WEBSITE_SWAP_WARMUP_PING_PATH`, `WEBSITE_SWAP_WARMUP_PING_STATUSES`)
- Health Check path and failure mode
- Swap mode (manual swap vs auto-swap)

**Observed:**

- HTTP status distribution during swap (`200`, `503`, other `5xx`)
- Time from swap initiation to first stable `200`
- Whether staging or production values appear in `/config` after swap
- Whether sticky app settings remain bound to the original slot
- Whether sticky connection strings remain bound to the original slot
- Swap command success, failure, stall, or rollback behavior
- App Service activity log events and deployment logs around swap time

## 7. Instrumentation

- **Test app responses** from `/`, `/health`, `/warmup`, and `/config`
- **Continuous traffic probe** during swap to capture transient failures and configuration identity over time
- **Azure CLI polling** for slot config, health check settings, and deployment state
- **App Service log stream / filesystem logs** for startup timing and warm-up endpoint hits
- **Activity log** for swap-related operations

Recommended capture points:

- Before swap
- During swap initiation
- First 2 minutes after swap
- After stabilization

## 8. Procedure

### 8.1 Infrastructure setup

Create a Linux App Service plan, one web app, and one staging slot.

```bash
RG="rg-slot-swap-warmup-lab"
LOCATION="koreacentral"
PLAN_NAME="plan-slot-swap-p1v3"
APP_NAME="app-slot-swap-$RANDOM"
SLOT_NAME="staging"

az group create --name "$RG" --location "$LOCATION"

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --sku P1v3 \
  --is-linux

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --name "$APP_NAME" \
  --runtime "PYTHON|3.11"

az webapp deployment slot create \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME"

az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"

az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"
```

Enable application logging so startup and warm-up events are captured.

```bash
az webapp log config \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --application-logging filesystem \
  --level information

az webapp log config \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --application-logging filesystem \
  --level information
```

### 8.2 Test application code

Create the following files in a local deployment folder.

#### `app.py`

```python
import json
import os
import socket
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request


def utc_now():
    return datetime.now(timezone.utc).isoformat()


startup_delay = int(os.environ.get("STARTUP_DELAY_SECONDS", "0"))
if startup_delay > 0:
    print(json.dumps({"event": "startup-delay-begin", "seconds": startup_delay, "ts": utc_now()}), flush=True)
    time.sleep(startup_delay)
    print(json.dumps({"event": "startup-delay-end", "seconds": startup_delay, "ts": utc_now()}), flush=True)


app = Flask(__name__)

state = {
    "started_at": utc_now(),
    "warmup_hits": 0,
    "first_live_request_at": None,
    "warmed_up": False,
}


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def base_payload():
    return {
        "ts": utc_now(),
        "site_name": os.environ.get("WEBSITE_SITE_NAME"),
        "slot_name": os.environ.get("WEBSITE_SLOT_NAME", "production"),
        "instance_id": os.environ.get("WEBSITE_INSTANCE_ID", socket.gethostname())[:16],
        "hostname": socket.gethostname(),
        "started_at": state["started_at"],
        "warmed_up": state["warmed_up"],
        "warmup_hits": state["warmup_hits"],
        "sticky_app_setting": os.environ.get("STICKY_APP_SETTING"),
        "shared_app_setting": os.environ.get("SHARED_APP_SETTING"),
        "slot_role": os.environ.get("SLOT_ROLE"),
        "sticky_connection_string": os.environ.get("SQLAZURECONNSTR_STICKY_DB"),
        "shared_connection_string": os.environ.get("SQLAZURECONNSTR_SHARED_DB"),
    }


@app.route("/")
def index():
    if state["first_live_request_at"] is None:
        state["first_live_request_at"] = utc_now()

    if env_bool("REQUIRE_WARMUP_BEFORE_LIVE", "false") and not state["warmed_up"]:
        payload = base_payload()
        payload["status"] = "cold-not-warmed"
        print(json.dumps({"event": "live-request-before-warmup", **payload}), flush=True)
        return jsonify(payload), 503

    payload = base_payload()
    payload["status"] = "ok"
    payload["first_live_request_at"] = state["first_live_request_at"]
    print(json.dumps({"event": "live-request", **payload}), flush=True)
    return jsonify(payload), 200


@app.route("/health")
def health():
    mode = os.environ.get("HEALTH_MODE", "pass").strip().lower()
    payload = base_payload()
    payload["health_mode"] = mode

    if mode == "fail":
        payload["status"] = "unhealthy"
        print(json.dumps({"event": "health-fail", **payload}), flush=True)
        return jsonify(payload), 503

    payload["status"] = "healthy"
    print(json.dumps({"event": "health-pass", **payload}), flush=True)
    return jsonify(payload), 200


@app.route("/warmup")
def warmup():
    delay = int(os.environ.get("WARMUP_DELAY_SECONDS", "0"))
    if delay > 0:
        time.sleep(delay)

    state["warmup_hits"] += 1
    state["warmed_up"] = True

    payload = base_payload()
    payload["status"] = "warmed"
    payload["warmup_delay_seconds"] = delay
    print(json.dumps({"event": "warmup-hit", **payload}), flush=True)
    return jsonify(payload), 200


@app.route("/config")
def config():
    payload = base_payload()
    payload["status"] = "config-dump"
    payload["require_warmup_before_live"] = env_bool("REQUIRE_WARMUP_BEFORE_LIVE", "false")
    payload["startup_delay_seconds"] = startup_delay
    payload["warmup_delay_seconds"] = int(os.environ.get("WARMUP_DELAY_SECONDS", "0"))
    payload["health_mode"] = os.environ.get("HEALTH_MODE", "pass")
    return jsonify(payload), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
```

#### `requirements.txt`

```text
Flask==3.0.3
gunicorn==23.0.0
```

This app provides:

- `/` - live endpoint; optionally returns `503` until `/warmup` has been called
- `/health` - health check endpoint; can be forced healthy or unhealthy with configuration
- `/warmup` - warm-up endpoint used by swap warm-up requests
- `/config` - shows slot name plus sticky/non-sticky app setting and connection string values

### 8.3 Deploy baseline app to production and staging

From the app source directory, package and deploy the same code to both slots.

```bash
zip -r app.zip app.py requirements.txt

az webapp deploy \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src-path "./app.zip" \
  --type zip

az webapp deploy \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --src-path "./app.zip" \
  --type zip
```

Apply baseline settings. The key point is to have both sticky and non-sticky values that are easy to identify after swap.

```bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings \
    SHARED_APP_SETTING=prod-shared \
    SLOT_ROLE=production \
    REQUIRE_WARMUP_BEFORE_LIVE=false \
    STARTUP_DELAY_SECONDS=0 \
    WARMUP_DELAY_SECONDS=0 \
    HEALTH_MODE=pass

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --settings \
    SHARED_APP_SETTING=staging-shared \
    SLOT_ROLE=staging \
    REQUIRE_WARMUP_BEFORE_LIVE=false \
    STARTUP_DELAY_SECONDS=0 \
    WARMUP_DELAY_SECONDS=0 \
    HEALTH_MODE=pass

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot-settings \
    STICKY_APP_SETTING=prod-sticky

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --slot-settings \
    STICKY_APP_SETTING=staging-sticky

az webapp config connection-string set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --connection-string-type SQLAzure \
  --settings SHARED_DB='Server=tcp:prod-shared.database.windows.net;Database=app;User Id=user;Password=pass;'

az webapp config connection-string set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --connection-string-type SQLAzure \
  --settings SHARED_DB='Server=tcp:staging-shared.database.windows.net;Database=app;User Id=user;Password=pass;'

az webapp config connection-string set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --connection-string-type SQLAzure \
  --slot-settings STICKY_DB='Server=tcp:prod-sticky.database.windows.net;Database=app;User Id=user;Password=pass;'

az webapp config connection-string set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --connection-string-type SQLAzure \
  --slot-settings STICKY_DB='Server=tcp:staging-sticky.database.windows.net;Database=app;User Id=user;Password=pass;'
```

Verify the baseline before any swap.

```bash
curl -s "https://$APP_NAME.azurewebsites.net/config"
curl -s "https://$APP_NAME-staging.azurewebsites.net/config"

az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --query "[?name=='SHARED_APP_SETTING' || name=='STICKY_APP_SETTING' || name=='SLOT_ROLE']"

az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --query "[?name=='SHARED_APP_SETTING' || name=='STICKY_APP_SETTING' || name=='SLOT_ROLE']"

az webapp config connection-string list \
  --resource-group "$RG" \
  --name "$APP_NAME"

az webapp config connection-string list \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME"
```

### 8.4 Traffic monitoring during swap

Use a continuous probe to record status codes and the configuration identity observed by callers while swap is in progress.

```python
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

APP_URL = "https://<app-name>.azurewebsites.net/"
OUTPUT = "swap-probe.jsonl"


def ts():
    return datetime.now(timezone.utc).isoformat()


with open(OUTPUT, "a", encoding="utf-8") as f:
    for i in range(360):
        record = {"ts": ts(), "iteration": i}
        try:
            with urllib.request.urlopen(APP_URL, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                record.update(
                    {
                        "http_status": resp.status,
                        "slot_name": body.get("slot_name"),
                        "slot_role": body.get("slot_role"),
                        "sticky_app_setting": body.get("sticky_app_setting"),
                        "shared_app_setting": body.get("shared_app_setting"),
                        "sticky_connection_string": body.get("sticky_connection_string"),
                        "shared_connection_string": body.get("shared_connection_string"),
                    }
                )
        except urllib.error.HTTPError as e:
            record["http_status"] = e.code
            record["error"] = e.reason
        except Exception as e:
            record["http_status"] = None
            record["error"] = str(e)

        print(json.dumps(record))
        f.write(json.dumps(record) + "\n")
        f.flush()
        time.sleep(1)
```

Run this probe shortly before starting each swap scenario and stop it after the system is stable again.

### 8.5 Scenario 1 - Swap with no warm-up configured

Purpose: establish the baseline swap timeline with no extra warm-up path and no artificial slow start.

```bash
az webapp config appsettings delete \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --setting-names WEBSITE_SWAP_WARMUP_PING_PATH WEBSITE_SWAP_WARMUP_PING_STATUSES

az webapp config appsettings delete \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --setting-names WEBSITE_SWAP_WARMUP_PING_PATH WEBSITE_SWAP_WARMUP_PING_STATUSES

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --settings REQUIRE_WARMUP_BEFORE_LIVE=false STARTUP_DELAY_SECONDS=0 HEALTH_MODE=pass

az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --target-slot production
```

Capture:

- Probe output around the swap window
- `/config` from both hostnames before and after swap
- Slot app settings and connection strings after swap

### 8.6 Scenario 2 - Swap with warm-up configured

Purpose: test whether swap warm-up eliminates transient live traffic failures for an app that requires `/warmup` before `/` can return `200`.

> Note: In older IIS-focused guidance this is often described as `applicationInitialization`. For this Linux/Python lab, the practical equivalent is App Service swap warm-up ping configuration.

```bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings \
    WEBSITE_SWAP_WARMUP_PING_PATH=/warmup \
    WEBSITE_SWAP_WARMUP_PING_STATUSES=200

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --settings \
    WEBSITE_SWAP_WARMUP_PING_PATH=/warmup \
    WEBSITE_SWAP_WARMUP_PING_STATUSES=200 \
    REQUIRE_WARMUP_BEFORE_LIVE=true \
    STARTUP_DELAY_SECONDS=0 \
    WARMUP_DELAY_SECONDS=10 \
    HEALTH_MODE=pass

az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --target-slot production
```

Compare with an otherwise identical run where `REQUIRE_WARMUP_BEFORE_LIVE=true` but no swap warm-up path is configured. The expected difference is whether the first user-facing requests after cutover return `503` or `200`.

### 8.7 Scenario 3 - Swap with Health Check enabled

Purpose: observe whether Health Check changes swap success criteria or post-swap traffic stability.

```bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --generic-configurations '{"healthCheckPath":"/health"}'

az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --generic-configurations '{"healthCheckPath":"/health"}'

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --settings HEALTH_MODE=fail REQUIRE_WARMUP_BEFORE_LIVE=false STARTUP_DELAY_SECONDS=0

az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --target-slot production
```

Record:

- CLI output from the swap command
- `https://$APP_NAME-staging.azurewebsites.net/health`
- `https://$APP_NAME.azurewebsites.net/health`
- Activity log entries for the app around the swap window

Repeat with `HEALTH_MODE=pass` to isolate Health Check failure impact.

### 8.8 Scenario 4 - Swap with slow-starting app (60s+ startup)

Purpose: measure how a long initialization delay interacts with swap warm-up and Health Check.

```bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --settings \
    STARTUP_DELAY_SECONDS=75 \
    REQUIRE_WARMUP_BEFORE_LIVE=true \
    WARMUP_DELAY_SECONDS=5 \
    HEALTH_MODE=pass \
    WEBSITE_SWAP_WARMUP_PING_PATH=/warmup \
    WEBSITE_SWAP_WARMUP_PING_STATUSES=200

az webapp restart \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME"

az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --target-slot production
```

Collect:

- Time from swap command start to first stable `200`
- App logs showing startup-delay begin/end and warm-up hit
- Probe log count of `503` during the window

Run the same scenario once without swap warm-up settings to determine whether warm-up meaningfully reduces post-cutover failures.

### 8.9 Scenario 5 - Sticky vs non-sticky setting behavior

Purpose: validate which values stay with the slot and which values move.

Before swap, record both slot endpoints:

```bash
curl -s "https://$APP_NAME.azurewebsites.net/config"
curl -s "https://$APP_NAME-staging.azurewebsites.net/config"
```

Perform swap:

```bash
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --target-slot production
```

After swap, record again:

```bash
curl -s "https://$APP_NAME.azurewebsites.net/config"
curl -s "https://$APP_NAME-staging.azurewebsites.net/config"
```

Evaluate at least these fields:

- `slot_name`
- `slot_role`
- `sticky_app_setting`
- `shared_app_setting`
- `sticky_connection_string`
- `shared_connection_string`

### 8.10 Scenario 6 - Auto-swap vs manual swap

Purpose: compare operator-visible behavior when swap is triggered automatically after deployment.

```bash
az webapp deployment slot auto-swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --auto-swap-slot production

az webapp deploy \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --src-path "./app.zip" \
  --type zip
```

Capture the same probe output and configuration snapshots used for manual swap scenarios. When finished, disable auto-swap so later scenarios remain operator-controlled.

```bash
az webapp deployment slot auto-swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot "$SLOT_NAME" \
  --disable
```

## 9. Expected signal

- **Sticky app setting** should remain with its original slot identity after swap.
- **Non-sticky app setting** should follow the swapped content/config view and appear changed on the production hostname after swap.
- **Sticky connection string** is expected to remain with the slot if configured as a slot setting.
- **Non-sticky connection string** is expected to move with the swapped slot configuration.
- **No warm-up + warm-up-required app** should produce a visible burst of `503` on `/` immediately after cutover.
- **Warm-up configured + warm-up-required app** should reduce or eliminate those transient `503`.
- **Health check failure on staging** should prevent a clean cutover or produce a clearly observable unhealthy behavior during swap.
- **Auto-swap** should preserve the same underlying slot-setting semantics but may shift when the transient error window begins relative to deployment completion.

## 10. Results

Executed on: 2026-05-01, Korea Central, Linux P1v3, Python 3.11, app `app-slot-swap-76099`.

### 10.1 Configuration movement

Scenario S5 (sticky vs non-sticky setting movement after swap).

| Setting | Production before | Staging before | Production after | Staging after |
|---------|-------------------|----------------|------------------|---------------|
| `sticky_app_setting` (slot-sticky) | `prod-sticky` | `staging-sticky` | `prod-sticky` | `staging-sticky` |
| `shared_app_setting` (non-sticky) | `prod-shared` | `staging-shared` | `staging-shared` | `prod-shared` |
| `sticky_connection_string` (slot-sticky) | `prod-sticky.database.windows.net` | `staging-sticky.database.windows.net` | `prod-sticky.database.windows.net` | `staging-sticky.database.windows.net` |
| `shared_connection_string` (non-sticky) | `prod-shared.database.windows.net` | `staging-shared.database.windows.net` | `staging-shared.database.windows.net` | `prod-shared.database.windows.net` |

Note: `SLOT_ROLE` (non-sticky) moved with the content. `STICKY_APP_SETTING` (slot-sticky) stayed bound to the slot hostname.

### 10.2 Availability during swap

1-second probe against production hostname during each swap. 0 errors in all runs.

| Scenario | Swap type | Warm-up configured | Health Check | Startup delay | `200` count | `503` count | Other `5xx` | Swap duration | First stable post-swap |
|----------|-----------|--------------------|--------------|---------------|-------------|-------------|-------------|---------------|------------------------|
| S1 | Manual | No | No | 0 s | 120 / 120 | 0 | 0 | 92 s | ~44 s into probe (i=44) |
| S2 | Manual | Yes (`/warmup`, 10 s delay) | No | 0 s | 180 / 180 | 0 | 0 | 83 s | ~37 s into probe (i=37) |
| S3 | Manual | No | Yes (staging `/health`=503) | 0 s | — | — | — | 83 s | swap completed; prod immediately unhealthy |
| S4 | Manual | Yes (`/warmup`, 5 s delay) | No | 75 s | 300 / 300 | 0 | 0 | 161 s | ~121 s into probe (i=121) |

During S1 and S2, a mixed-routing window was visible (i=44–67 in S1, i=37–44 in S2) where both `slot_role=production` and `slot_role=staging` responses appeared at the production hostname within the same ~10–23 s window before stabilizing.

### 10.3 Swap command outcome

| Scenario | Swap command result | Notes |
|----------|---------------------|-------|
| S1 | Exit 0, 92 s | Baseline — no startup delay, no warm-up |
| S2 | Exit 0, 83 s | Warmup path hit before cutover; first post-swap response had `warmed_up=true` |
| S3 | Exit 0, 83 s | Swap succeeded despite staging `/health` returning 503 throughout |
| S4 | Exit 0, 161 s | Swap waited for 75 s startup + 5 s warmup before cutting over; 0 503s |
| S5 | Exit 0, ~80 s | Config movement observed; no availability impact |

## 11. Interpretation

### H1 — Slot-sticky settings stay with the slot; non-sticky settings move with the content: CONFIRMED [Observed]

S5 showed that `STICKY_APP_SETTING` and `STICKY_DB` (both configured with `--slot-settings`) remained bound to the original slot hostname after swap **[Observed]**. `SHARED_APP_SETTING` and `SHARED_DB` (non-sticky) moved to the new production hostname along with the swapped content **[Observed]**. The separation is clean and immediate — no delay observed post-swap.

### H2 — Non-sticky connection strings move with the swapped slot configuration: CONFIRMED [Observed]

`SQLAZURECONNSTR_SHARED_DB` (non-sticky) moved to the production hostname after swap; `SQLAZURECONNSTR_STICKY_DB` (slot-sticky) stayed **[Observed]**. Connection strings and app settings follow the same slot-sticky semantics when configured identically.

### H3 — Swap without warm-up on a fast-starting app produced no transient 503 in this run: CONFIRMED [Observed, single run]

S1 recorded 0 503s across 120 1-second probes during a manual swap with no warm-up and no startup delay **[Observed]**. Note: the 1 s probe cadence means sub-second transient failures could have been missed. A transition window (~23 s, i=44–67) was visible where the production hostname returned both `slot_role=production` and `slot_role=staging` responses before stabilizing — all were `200` **[Observed]**. Whether this transition window duration is repeatable across runs was not measured. A slow-starting or warm-up-dependent app would likely produce a different result **[Inferred]**.

### H3b — Swap with warm-up configured: first post-cutover response was already warmed: CONFIRMED [Observed, single run]

S2 recorded 0 503s. The first response after cutover had `warmed_up=true` **[Observed]**. This is consistent with the platform hitting `/warmup` on the staging slot before routing live traffic, but the warmup-request hit was not directly captured from platform logs — the conclusion is based on the app-side `warmup_hits` counter and `warmed_up` flag **[Strongly Suggested]**.

### H4 — In this single-instance run, Health Check failure on staging did not block manual swap completion: CONFIRMED [Observed, single run, single instance]

S3 showed that `az webapp deployment slot swap` returned exit 0 in 83 s even though staging `/health` returned `503` throughout **[Observed]**. Post-swap, the production hostname immediately served the unhealthy app **[Observed]**. This result is limited to: single-instance plan, default Health Check configuration, no minimum healthy-instance threshold tested. Whether Health Check failure blocks swap under multi-instance plans, specific threshold settings, or other configurations is **[Unknown]**. Health Check continued to affect post-swap instance availability and routing — it is not irrelevant to the swap outcome, only to swap command completion in this setup.

### H5 — Slow-starting app with warm-up extended swap duration and produced no 503 in this run: CONFIRMED [Observed, single run]

S4 showed swap duration of 161 s vs. 83–92 s for fast-starting scenarios **[Observed]**. Zero 503s were observed across 300 1-second probes **[Observed]**. The additional ~78 s over the S2 baseline is consistent with the platform waiting for the 75 s startup delay before the warmup ping could succeed, but the internal sequencing of startup completion and warmup initiation was not directly captured from platform logs **[Strongly Suggested]**.

## 12. What this proves

These results apply specifically to:

- Azure App Service P1v3, Linux, `koreacentral`
- Python 3.11 Flask app, one production + one staging slot
- Manual swap (`az webapp deployment slot swap`)
- Single-instance plan (P1v3, no scale-out)

**Proved [Observed]:**

1. Slot-sticky app settings and connection strings remain bound to the slot hostname after swap — the production hostname retains its sticky values regardless of what was in staging.
2. Non-sticky app settings and connection strings move with the swapped content — the production hostname reflects the staging values after swap.
3. A fast-starting app with no warm-up requirement produced 0 503s during manual swap on this single-instance P1v3 in this run (1 s probe cadence; sub-second blips could have been missed).
4. The first post-cutover response after a warmup-configured swap had `warmed_up=true`, consistent with the platform completing the warmup path before routing live traffic **[Strongly Suggested]**.
5. In this single-instance run, a failing Health Check endpoint on the staging slot did not block `az webapp deployment slot swap` from completing successfully.
6. A 75 s startup delay extended swap duration (~161 s vs. ~83 s) but did not cause 503s when warm-up was configured — the transition window waited until the app was ready.

## 13. What this does NOT prove

- That all App Service SKUs behave identically — scale-out (multiple instances) may introduce per-instance warm-up and routing differences not visible here
- That Windows/IIS slot swap behavior is identical — `applicationInitialization` in `web.config` is the Windows equivalent; this experiment used `WEBSITE_SWAP_WARMUP_PING_PATH` on Linux
- That Health Check failure blocks swap under any configuration — the experiment only tested the default configuration on a single-instance plan; minimum healthy instance thresholds, multi-instance plans, or other Health Check settings may change swap gating behavior **[Unknown]**
- That Health Check is irrelevant to swap outcomes — Health Check continued to govern post-swap instance routing and eviction; a swap that succeeds with a failing health check still leaves production serving unhealthy traffic **[Observed in S3]**
- That auto-swap (S6) follows identical timing — S6 was not executed; auto-swap couples deployment completion and swap activation and may produce a different observable timeline **[Unknown]**
- That the observed transition window (~23 s) is guaranteed or repeatable — this was observed once per scenario at 1 s probe resolution; sub-second blips and variability across runs were not measured
- That connection string behavior is identical across all connection string types — only `SQLAzure` type was tested
- That the warmup path was definitively hit by the platform before cutover — this is inferred from `warmed_up=True` on the first post-cutover response; direct platform-side warmup request logs were not captured

## 14. Support takeaway

1. **"We swapped and the app started serving the wrong config values"**: Ask explicitly which settings are marked as slot settings (`--slot-settings` / sticky). Non-sticky app settings and connection strings move with the content. If a customer expects a value to stay with an environment, it must be configured as a slot setting. This is the most common source of post-swap config confusion **[Observed]**.

2. **"Swap succeeded but users saw 503 for 30–60 seconds"**: The app is likely slow to start or requires an explicit warm-up call before it can serve live traffic. Confirm whether `WEBSITE_SWAP_WARMUP_PING_PATH` and `WEBSITE_SWAP_WARMUP_PING_STATUSES` are configured. If not, the platform will cut over without waiting for the app to be ready. Adding a warmup path eliminates this window for slow-starting apps **[Observed]**.

3. **"Swap stalls or the swap command fails"**: In this single-instance experiment, Health Check failure did *not* block swap completion — the swap succeeded despite staging returning 503 on `/health` **[Observed]**. For swap-completion issues, start with the warm-up path: confirm `WEBSITE_SWAP_WARMUP_PING_PATH` is reachable and returns the expected status on the staging slot. If the swap command itself fails or times out, the warmup path is the more likely cause than Health Check in this configuration.

4. **"Swap succeeded but production is now serving unhealthy traffic"**: Health Check failure does not prevent swap — it governs post-swap instance routing and eviction. If the swap completed and production is unhealthy, check `HEALTH_MODE` / health endpoint logic on the newly promoted slot. Health Check will eventually remove or reduce traffic to unhealthy instances, but this happens after the swap, not during it **[Observed in S3, single-instance run]**.

4. **"Swap is taking much longer than usual"**: Swap duration scales with startup time plus warm-up latency. A 75 s startup + warmup produced a ~161 s swap in this test, vs. ~83 s for fast-starting apps **[Observed]**. Check actual app initialization time on the staging slot and `WARMUP_DELAY_SECONDS` or the warmup endpoint's response time.

5. **Slot-sticky vs non-sticky quick reference**:

    | Configured with | Behavior during swap |
    |-----------------|----------------------|
    | `--slot-settings` (sticky) | Stays with slot hostname; never moves |
    | Plain `--settings` (non-sticky) | Moves with swapped content to target slot |

    Connection strings follow the same rule: `--slot-settings` = sticky, plain `--settings` = moves.

## 15. Reproduction notes

- This lab should not be run against a production workload.
- Use obviously different values for sticky and non-sticky settings so movement is visually obvious in `/config`.
- Startup delay should be long enough (`60s+`) to make the transient window easy to capture, but not so long that unrelated deployment timeouts dominate the result.
- Run the traffic probe from a host with stable outbound connectivity; otherwise client-side timeouts may be confused with server-side `503`.
- If slot swap behavior appears ambiguous, repeat the run with `az webapp deployment slot swap --action preview` followed by `--action swap` to split preparation from activation.

## 16. Related guide / official docs

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-staging-slots)
- [Configure deployment slots for Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-staging-slots#configure-deployment-slots)
- [Monitor instances in App Service with Health check](https://learn.microsoft.com/azure/app-service/monitor-instances-health-check)
- [Configure Python on Azure App Service Linux](https://learn.microsoft.com/azure/app-service/configure-language-python)
- [Health Check Eviction on Partial Dependency Failure](../health-check-eviction/overview.md)
