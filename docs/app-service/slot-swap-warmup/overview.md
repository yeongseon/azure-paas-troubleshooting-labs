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

!!! info "Status: Draft - Awaiting Execution"
    This experiment design is complete, but it has not been executed yet. All procedures, expected signals, and result tables below are prepared for a future lab run on Azure App Service.

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

Pending execution.

Use the tables below during the live run.

### 10.1 Configuration movement

| Scenario | Production before | Staging before | Production after | Staging after |
|----------|-------------------|----------------|------------------|---------------|
| `sticky_app_setting` | TBD | TBD | TBD | TBD |
| `shared_app_setting` | TBD | TBD | TBD | TBD |
| `sticky_connection_string` | TBD | TBD | TBD | TBD |
| `shared_connection_string` | TBD | TBD | TBD | TBD |

### 10.2 Availability during swap

| Scenario | Swap type | Warm-up configured | Health Check enabled | Startup delay | `200` count | `503` count | Other `5xx` | First stable `200` after swap |
|----------|-----------|--------------------|----------------------|---------------|-------------|-------------|-------------|-------------------------------|
| 1 | Manual | No | No | 0s | TBD | TBD | TBD | TBD |
| 2 | Manual | Yes | No | 0s | TBD | TBD | TBD | TBD |
| 3 | Manual | Optional | Yes | 0s | TBD | TBD | TBD | TBD |
| 4 | Manual | Yes/No | Optional | 75s | TBD | TBD | TBD | TBD |
| 6 | Auto-swap | Yes/No | Optional | varies | TBD | TBD | TBD | TBD |

### 10.3 Swap command outcome

| Scenario | Swap command result | Observed activity log summary | Notes |
|----------|---------------------|-------------------------------|-------|
| 1 | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD |
| 4 | TBD | TBD | TBD |
| 5 | TBD | TBD | TBD |
| 6 | TBD | TBD | TBD |

## 11. Interpretation

Pending execution.

Current evidence status:

- **Unknown** whether non-sticky app settings and non-sticky connection strings will show identical movement semantics in this exact Linux/Python slot configuration.
- **Unknown** how consistently swap warm-up removes transient `503` for a slow-starting app on this SKU and region.
- **Unknown** whether Health Check failure causes swap failure, delayed activation, or only post-swap unhealthy behavior in this test design.

## 12. What this proves

Not yet executed.

Once completed, this experiment should prove only the specific behaviors observed on:

- Azure App Service P1v3
- `koreacentral`
- Python 3.11 on Linux
- one production slot and one staging slot

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- That all App Service SKUs behave identically
- That Windows/IIS slot swap behavior is identical to Linux/Python behavior
- That every application framework reacts to warm-up the same way as this Flask app
- That connection string behavior is identical across every connection string type
- That auto-swap timing is identical across deployment mechanisms other than this zip deployment flow

## 14. Support takeaway

Provisional guidance pending execution:

- When customers report wrong config after swap, explicitly separate **slot settings** from ordinary app settings and inspect connection strings independently.
- When customers report a brief outage immediately after swap, ask whether the app needs warm-up or performs expensive startup work before serving live traffic.
- When Health Check is enabled, verify the slot can return healthy responses on the configured path before attempting swap.
- For auto-swap complaints, reconstruct the timeline from deployment completion, warm-up behavior, and first failed customer requests instead of assuming a pure configuration issue.

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
