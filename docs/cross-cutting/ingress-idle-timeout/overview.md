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

# Ingress Idle Timeout vs Streaming

!!! info "Status: Published"
    Experiment executed on 2026-05-01, Korea Central. App Service P1v3 Linux + Container Apps Consumption, Python 3.11 Flask (container image). Single run per configuration; Scenario D (repeatability) not completed.

## 1. Question

For long-running HTTP requests, when does Azure App Service ingress or Azure Container Apps ingress terminate the connection, and does periodic response streaming (chunked transfer or Server-Sent Events) prevent the ingress idle timeout from firing?

## 2. Why this matters

Customers often have endpoints that legitimately run for several minutes: report generation, archive export, AI inference, large upstream API aggregation, or batch orchestration. Support cases become confusing when:

- the application keeps working on the server side but the client connection is closed by the platform
- the customer believes the app "times out at exactly 4 minutes" but cannot tell whether the timeout is application, worker, client, or ingress
- one implementation style fails (single delayed response) while another succeeds (periodic streaming)

This experiment separates **connection idle timeout at the ingress layer** from **application processing time**, and tests whether periodic outbound bytes keep the request alive.

## 3. Customer symptom

- "Our request runs for 5 minutes and then the browser gets disconnected even though the server keeps processing."
- "App Service always fails around 230 seconds."
- "Container Apps works only when we send progress updates every 30 seconds."
- "SSE works, but a normal JSON response with the same total duration does not."

## 4. Hypothesis

1. Azure App Service terminates otherwise-idle HTTP requests at roughly **230 seconds**.
2. Azure Container Apps terminates otherwise-idle HTTP requests at roughly **240 seconds**.
3. Sending response bytes every 30 seconds via chunked transfer resets the ingress idle timer and allows requests longer than the nominal timeout to complete.
4. Sending SSE events every 30 seconds has the same keep-alive effect as generic chunked streaming.
5. Without streaming, the connection is terminated near the ingress idle timeout regardless of whether the Flask process continues sleeping or computing.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service and Azure Container Apps |
| SKU / Plan | App Service P1v3; Container Apps Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask + Gunicorn custom container) |
| OS | Linux |
| Test modes | delayed response, chunked streaming, SSE |
| Streaming cadence | 30 seconds |
| Date tested | 2026-05-01 |

## 6. Variables

**Experiment type**: Hybrid (Config + Performance)

**Controlled:**

- Region: `koreacentral`
- Application code: identical Flask image for both services
- Container image source: same ACR and same image digest
- Request durations for non-streaming mode: 60s, 120s, 180s, 240s, 300s
- Streaming cadence: 30-second intervals
- Payload size per streamed chunk/event: small text message only
- Client tool and timing method: `curl` + shell timestamps or Python client
- Single-request execution (no concurrency during baseline runs)

**Observed:**

- Client-visible HTTP status code
- Client-visible disconnect behavior (200, 502/504, connection reset, EOF, timeout)
- Time to first byte
- Total connected duration until success or disconnect
- Number of streamed chunks/events received before disconnect
- Server-side completion timestamp vs client disconnect timestamp
- App Service and Container Apps platform logs around each run

**Independent run definition**: One request to one endpoint mode (`/delay`, `/stream`, `/sse`) with one duration configuration, issued after confirming the current revision/container is healthy and no deployment is in progress.

**Planned runs per configuration**: 3 minimum per service/mode/duration combination

**Warm-up exclusion rule**: Exclude the first request after deployment or scale event; collect one warm-up request before measured runs.

**Primary metric**: Client disconnect time for non-streaming requests and successful completion rate for streaming requests

**Meaningful effect threshold**: >10 seconds difference from hypothesized ingress cutoff, or any successful completion beyond 300 seconds when streaming is enabled

**Comparison method**: Descriptive statistics by service and mode; compare observed cutoff windows and success rates across App Service vs Container Apps

## 7. Instrumentation

- **Client timing**: `curl --no-buffer --verbose --write-out` to capture connect time, TTFB, total time, and disconnect behavior
- **Optional scripted client**: Python `requests`/`httpx` runner with monotonic timestamps and per-chunk receipt logging
- **Application logging**: JSON logs from Flask/Gunicorn including request ID, mode, configured duration, chunk emission timestamps, and final completion timestamp
- **App Service logs**: container log stream and HTTP logs via `az webapp log tail`
- **Container Apps logs**: `az containerapp logs show` plus Log Analytics queries against `ContainerAppConsoleLogs_CL` and `ContainerAppSystemLogs_CL`
- **Platform metadata**: deployment configuration snapshots from `az webapp show` and `az containerapp show`

Suggested client-side response capture fields:

| Field | Description |
|-------|-------------|
| `service` | `appservice` or `containerapps` |
| `mode` | `delay`, `stream`, `sse` |
| `duration_seconds` | Requested total server duration |
| `started_utc` | Client request start time |
| `time_to_first_byte_seconds` | `curl` TTFB |
| `total_connected_seconds` | Time until success/disconnect |
| `http_status` | Final visible status if any |
| `chunks_received` | Count of chunk lines or SSE events |
| `disconnect_signature` | EOF, reset, timeout, 502, etc. |

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-ingress-idle-timeout-lab"
export LOCATION="koreacentral"
export ACR_NAME="acringressidle$RANDOM"
export IMAGE_NAME="flask-ingress-timeout"
export IMAGE_TAG="v1"
export PLAN_NAME="plan-ingress-idle-timeout"
export WEBAPP_NAME="app-ingress-idle-$RANDOM"
export LAW_NAME="law-ingress-idle-timeout"
export ACA_ENV_NAME="cae-ingress-idle-timeout"
export ACA_NAME="ca-ingress-idle-$RANDOM"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --location "$LOCATION"

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --sku P1v3 \
  --is-linux

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --location "$LOCATION"

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query customerId --output tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --query primarySharedKey --output tsv)

az containerapp env create \
  --resource-group "$RG" \
  --name "$ACA_ENV_NAME" \
  --location "$LOCATION" \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY"
```

### 8.2 Application Code

`app.py`:

```python
import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, Response, jsonify, request, stream_with_context

app = Flask(__name__)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def log_event(payload):
    print(json.dumps(payload), flush=True)


@app.get("/")
def index():
    return jsonify(
        {
            "status": "ok",
            "service_name": os.getenv("SERVICE_NAME", "unknown"),
            "revision": os.getenv("CONTAINER_APP_REVISION", os.getenv("WEBSITE_INSTANCE_ID", "unknown")),
            "timestamp_utc": utc_now(),
        }
    )


@app.get("/delay")
def delay():
    request_id = request.headers.get("x-request-id", str(uuid4()))
    duration = int(request.args.get("duration", "60"))

    log_event(
        {
            "event": "delay_start",
            "request_id": request_id,
            "duration_seconds": duration,
            "timestamp_utc": utc_now(),
            "service_name": os.getenv("SERVICE_NAME", "unknown"),
        }
    )

    time.sleep(duration)

    log_event(
        {
            "event": "delay_complete",
            "request_id": request_id,
            "duration_seconds": duration,
            "timestamp_utc": utc_now(),
        }
    )

    return jsonify(
        {
            "request_id": request_id,
            "mode": "delay",
            "duration_seconds": duration,
            "completed_utc": utc_now(),
        }
    )


@app.get("/stream")
def stream():
    request_id = request.headers.get("x-request-id", str(uuid4()))
    duration = int(request.args.get("duration", "300"))
    interval = int(request.args.get("interval", "30"))

    @stream_with_context
    def generate():
        start = time.monotonic()
        elapsed = 0

        log_event(
            {
                "event": "stream_start",
                "request_id": request_id,
                "duration_seconds": duration,
                "interval_seconds": interval,
                "timestamp_utc": utc_now(),
            }
        )

        yield f"start request_id={request_id} ts={utc_now()}\n"

        while elapsed + interval < duration:
            time.sleep(interval)
            elapsed = round(time.monotonic() - start)
            log_event(
                {
                    "event": "stream_chunk",
                    "request_id": request_id,
                    "elapsed_seconds": elapsed,
                    "timestamp_utc": utc_now(),
                }
            )
            yield f"chunk elapsed={elapsed} ts={utc_now()}\n"

        remaining = max(duration - round(time.monotonic() - start), 0)
        if remaining:
            time.sleep(remaining)

        log_event(
            {
                "event": "stream_complete",
                "request_id": request_id,
                "duration_seconds": duration,
                "timestamp_utc": utc_now(),
            }
        )
        yield f"complete request_id={request_id} ts={utc_now()}\n"

    return Response(generate(), mimetype="text/plain")


@app.get("/sse")
def sse():
    request_id = request.headers.get("x-request-id", str(uuid4()))
    duration = int(request.args.get("duration", "300"))
    interval = int(request.args.get("interval", "30"))

    @stream_with_context
    def generate():
        start = time.monotonic()
        elapsed = 0

        log_event(
            {
                "event": "sse_start",
                "request_id": request_id,
                "duration_seconds": duration,
                "interval_seconds": interval,
                "timestamp_utc": utc_now(),
            }
        )

        yield f"event: started\ndata: {{\"request_id\": \"{request_id}\", \"timestamp_utc\": \"{utc_now()}\"}}\n\n"

        while elapsed + interval < duration:
            time.sleep(interval)
            elapsed = round(time.monotonic() - start)
            log_event(
                {
                    "event": "sse_chunk",
                    "request_id": request_id,
                    "elapsed_seconds": elapsed,
                    "timestamp_utc": utc_now(),
                }
            )
            yield f"event: progress\ndata: {{\"elapsed_seconds\": {elapsed}, \"timestamp_utc\": \"{utc_now()}\"}}\n\n"

        remaining = max(duration - round(time.monotonic() - start), 0)
        if remaining:
            time.sleep(remaining)

        log_event(
            {
                "event": "sse_complete",
                "request_id": request_id,
                "duration_seconds": duration,
                "timestamp_utc": utc_now(),
            }
        )
        yield f"event: complete\ndata: {{\"request_id\": \"{request_id}\", \"timestamp_utc\": \"{utc_now()}\"}}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

`requirements.txt`:

```text
flask==3.0.3
gunicorn==23.0.0
```

### 8.3 Container Image

`Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "app:app"]
```

Build the image in ACR:

```bash
az acr build \
  --registry "$ACR_NAME" \
  --resource-group "$RG" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  --file Dockerfile .
```

### 8.4 Deploy App Service

```bash
ACR_LOGIN_SERVER=$(az acr show --resource-group "$RG" --name "$ACR_NAME" --query loginServer --output tsv)
ACR_USERNAME=$(az acr credential show --resource-group "$RG" --name "$ACR_NAME" --query username --output tsv)
ACR_PASSWORD=$(az acr credential show --resource-group "$RG" --name "$ACR_NAME" --query "passwords[0].value" --output tsv)

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --name "$WEBAPP_NAME" \
  --deployment-container-image-name "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"

az webapp config container set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --container-image-name "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  --container-registry-url "https://$ACR_LOGIN_SERVER" \
  --container-registry-user "$ACR_USERNAME" \
  --container-registry-password "$ACR_PASSWORD"

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --settings WEBSITES_PORT=8080 SERVICE_NAME=appservice

az webapp log config \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME" \
  --docker-container-logging filesystem
```

### 8.5 Deploy Container Apps

```bash
az containerapp create \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --environment "$ACA_ENV_NAME" \
  --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars SERVICE_NAME=containerapps
```

Capture FQDNs used during testing:

```bash
APP_URL="https://$(az webapp show --resource-group "$RG" --name "$WEBAPP_NAME" --query defaultHostName --output tsv)"
ACA_URL="https://$(az containerapp show --resource-group "$RG" --name "$ACA_NAME" --query properties.configuration.ingress.fqdn --output tsv)"

printf 'APP_URL=%s\nACA_URL=%s\n' "$APP_URL" "$ACA_URL"
```

### 8.6 Test Execution

Warm up each endpoint once before measurement:

```bash
curl --silent "$APP_URL/"
curl --silent "$ACA_URL/"
```

#### Scenario A — Non-streaming delay

Run the following durations for each service: `60 120 180 240 300`.

```bash
for SERVICE_URL in "$APP_URL" "$ACA_URL"; do
  for DURATION in 60 120 180 240 300; do
    REQUEST_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
    START_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    curl --no-buffer --verbose \
      --max-time 420 \
      --header "x-request-id: $REQUEST_ID" \
      --write-out "\nstatus=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n" \
      "$SERVICE_URL/delay?duration=$DURATION"

    printf 'service=%s request_id=%s mode=delay duration=%s started_utc=%s\n' \
      "$SERVICE_URL" "$REQUEST_ID" "$DURATION" "$START_UTC"
  done
done
```

#### Scenario B — Chunked streaming every 30 seconds

Target at least `300` and `360` seconds to test survival beyond the hypothesized ingress timeout.

```bash
for SERVICE_URL in "$APP_URL" "$ACA_URL"; do
  for DURATION in 300 360; do
    REQUEST_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

    curl --no-buffer --verbose \
      --max-time 480 \
      --header "x-request-id: $REQUEST_ID" \
      --write-out "\nstatus=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n" \
      "$SERVICE_URL/stream?duration=$DURATION&interval=30"
  done
done
```

#### Scenario C — SSE every 30 seconds

```bash
for SERVICE_URL in "$APP_URL" "$ACA_URL"; do
  for DURATION in 300 360; do
    REQUEST_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

    curl --no-buffer --verbose \
      --max-time 480 \
      --header "Accept: text/event-stream" \
      --header "x-request-id: $REQUEST_ID" \
      --write-out "\nstatus=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n" \
      "$SERVICE_URL/sse?duration=$DURATION&interval=30"
  done
done
```

#### Scenario D — Repeatability

Repeat every service/mode/duration combination three times. Preserve raw client transcripts and platform logs for each run. If a disconnect occurs, immediately pull application logs using the same `x-request-id`.

### 8.7 Data Collection

App Service logs:

```bash
az webapp log tail \
  --resource-group "$RG" \
  --name "$WEBAPP_NAME"
```

Container Apps console logs:

```bash
az containerapp logs show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --type console \
  --follow false

az containerapp logs show \
  --resource-group "$RG" \
  --name "$ACA_NAME" \
  --type system \
  --follow false
```

Log Analytics example queries:

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(6h)
| where Log_s has_any ("delay_start", "delay_complete", "stream_chunk", "stream_complete", "sse_chunk", "sse_complete")
| project TimeGenerated, Log_s
| order by TimeGenerated asc
```

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(6h)
| project TimeGenerated, Reason_s, Log_s
| order by TimeGenerated asc
```

Record evidence in a table like this:

| Run | Service | Mode | Duration | Interval | HTTP status | TTFB | Total connected | Chunks/events received | Outcome |
|-----|---------|------|----------|----------|-------------|------|-----------------|------------------------|---------|
| 1 | App Service | delay | 240 | n/a | | | | 0 | |
| 2 | App Service | stream | 300 | 30 | | | | | |
| 3 | App Service | sse | 300 | 30 | | | | | |
| 4 | Container Apps | delay | 240 | n/a | | | | 0 | |
| 5 | Container Apps | stream | 300 | 30 | | | | | |
| 6 | Container Apps | sse | 300 | 30 | | | | | |

### 8.8 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- **App Service /delay** should succeed through 180 seconds and fail near 230 seconds for 240-second and 300-second requests.
- **Container Apps /delay** should succeed through 180 seconds and fail near 240 seconds for 300-second requests.
- **/stream** and **/sse** should remain connected past 300 seconds on both services if each 30-second emission resets the idle timer.
- The server logs should show `delay_complete` even in some failed client cases, indicating server-side work can continue after ingress disconnect.
- If streaming does not prevent disconnect, the cut-off should still cluster near the same ingress idle window despite chunks/events being emitted.

## 10. Results

Executed on: 2026-05-01, Korea Central. App Service P1v3 Linux (`app-ingress-idle-15852.azurewebsites.net`), Container Apps Consumption (`ca-ingress-idle-23299.redsand-be4f5b04.koreacentral.azurecontainerapps.io`). Single request per configuration; 1 warm-up request per service before measurement.

### 10.1 Non-streaming delay results (Scenario A)

| Service | Requested duration | HTTP status | Total connected (s) | Outcome |
|---------|--------------------|-------------|---------------------|---------|
| App Service | 60 s | 200 | 60.08 | **Success** |
| Container Apps | 60 s | 200 | 60.07 | **Success** |
| App Service | 120 s | 200 | 120.09 | **Success** |
| Container Apps | 120 s | 200 | 120.07 | **Success** |
| App Service | 180 s | 200 | 180.11 | **Success** |
| Container Apps | 180 s | 200 | 180.07 | **Success** |
| App Service | 240 s | 504 | 240.08 | **Disconnected at ~240 s** |
| Container Apps | 240 s | 504 | 240.09 | **Disconnected at ~240 s** |
| App Service | 300 s | 499 | 240.11 | **Disconnected at ~240 s** |
| Container Apps | 300 s | 504 | 240.07 | **Disconnected at ~240 s** |

Both services terminated the idle connection at approximately 240 seconds. App Service returned `499` for the 300 s request (client closed or ingress reset) and `504` for the 240 s request; Container Apps returned `504` consistently. The 180 s requests succeeded; the 240 s and 300 s requests failed at the same elapsed time (~240 s), not at the requested duration.

### 10.2 Chunked streaming results (Scenario B)

Streaming interval: 30 seconds.

| Service | Requested duration | HTTP status | Total connected (s) | Chunks received | Outcome |
|---------|--------------------|-------------|---------------------|-----------------|---------|
| App Service | 300 s | 200 | 300.11 | 9 | **Success** |
| Container Apps | 300 s | 200 | 300.08 | 9 | **Success** |
| App Service | 360 s | 200 | 360.10 | 11 | **Success** |
| Container Apps | 360 s | 200 | 360.08 | 11 | **Success** |

All chunked-streaming requests succeeded, including those exceeding the 240 s idle cutoff observed in Scenario A. Chunks arrived at the client approximately every 30 seconds throughout the connection.

### 10.3 SSE results (Scenario C)

Streaming interval: 30 seconds.

| Service | Requested duration | HTTP status | Total connected (s) | Events received | Outcome |
|---------|--------------------|-------------|---------------------|-----------------|---------|
| App Service | 300 s | 200 | 300.09 | 9 | **Success** |
| Container Apps | 300 s | 200 | 300.07 | 9 | **Success** |
| App Service | 360 s | 200 | 360.09 | 11 | **Success** |
| Container Apps | 360 s | 200 | 360.08 | 11 | **Success** |

SSE requests produced identical results to chunked streaming. Both services sustained SSE connections to 360 s without disconnection.

### 10.4 App Service vs Container Apps comparison

| Dimension | App Service | Container Apps |
|-----------|-------------|----------------|
| Non-streaming cutoff | ~240 s | ~240 s |
| Disconnect status (at cutoff) | 499 or 504 | 504 |
| Streaming success at 300 s | Yes (chunked + SSE) | Yes (chunked + SSE) |
| Streaming success at 360 s | Yes (chunked + SSE) | Yes (chunked + SSE) |

Both services showed the same effective idle timeout window (~240 s) and the same streaming-survival behavior. The hypothesis that App Service would cut at ~230 s was not confirmed — both cut at ~240 s.

### 10.5 Client transcript sample

App Service, delay 240 s (disconnected):

```
HTTP/1.1 504
total time: 240.079324 s
```

App Service, stream 360 s (success):

```
start request_id=... ts=...
chunk elapsed=30 ts=...
chunk elapsed=60 ts=...
...
chunk elapsed=330 ts=...
complete request_id=... ts=...
status=200 ttfb=0.152 total=360.101
```

## 11. Interpretation

### H1 — App Service terminates idle requests at ~230 s: NOT CONFIRMED — observed cutoff was ~240 s in this single-run configuration [Measured, single run]

The hypothesis predicted ~230 s. All non-streaming requests at 240 s and 300 s were terminated at approximately 240 s elapsed — not 230 s **[Measured, single run]**. Requests at 180 s completed successfully. The observed cutoff in this test is ~240 s, not ~230 s, so the specific ~230 s hypothesis is not confirmed by this data. Whether the platform imposes exactly 240 s, whether there is run-to-run variance, and whether other regions or SKUs differ was not measured (Scenario D not executed) **[Unknown]**.

### H2 — Container Apps terminates idle requests at ~240 s: CONFIRMED in this single-run configuration [Measured, single run]

Container Apps terminated non-streaming connections at ~240 s, matching the hypothesis **[Measured, single run]**. This matches the App Service observed cutoff exactly in this run. Repeatability and generalizability across regions and plan types were not tested.

### H3 — Chunked streaming every 30 s survives beyond the idle cutoff: CONFIRMED [Observed]

Chunked streaming at 30 s intervals succeeded at 300 s and 360 s on both App Service and Container Apps **[Observed]**. The results are consistent with periodic outbound bytes preventing the idle disconnect — each chunk was emitted well before the ~240 s cutoff window could accumulate **[Inferred]**. Whether a longer streaming interval (e.g., 180 s or 210 s) would also survive was not tested **[Unknown]**.

### H4 — SSE every 30 s produces the same outcome as chunked streaming: CONFIRMED [Observed]

SSE requests produced the same outcome as chunked streaming — both survived to 300 s and 360 s on both services **[Observed]**. Whether the underlying mechanism is identical (i.e., the same ingress timer reset behavior) was not directly verified; the results are outcome-equivalent in this test **[Inferred]**.

### H5 — Without streaming, the ingress connection closes before the application response completes: CONFIRMED [Inferred]

In all Scenario A failures, the client received a `504`/`499` disconnect at ~240 s while the application was still sleeping (the `/delay` endpoint sends no response until the full sleep completes). The ingress terminated the connection before the application could respond **[Inferred from endpoint design and timing — backend logs were not directly captured post-disconnect to confirm server execution continued]**.

## 12. What this proves

These results apply specifically to:

- App Service P1v3, Linux, `koreacentral`, container-based deployment
- Container Apps Consumption, `koreacentral`, 0.5 vCPU / 1 GiB, single replica
- Python 3.11 Flask with Gunicorn (`--timeout 0`), single run per configuration

**Proved [Measured/Observed in this single-run configuration]:**

1. Non-streaming HTTP requests were terminated at approximately **240 seconds** on both App Service (P1v3 Linux, `koreacentral`) and Container Apps (Consumption, `koreacentral`) — not the ~230 s previously cited for App Service. This is a single-run measurement; run-to-run variance and generalizability to other SKUs/regions are unknown **[Measured, single run]**.
2. Chunked transfer encoding with 30 s emission intervals sustained connections to **360 s** on both services without disconnection **[Observed]**.
3. SSE with 30 s event intervals sustained connections to **360 s** on both services — same outcome as chunked streaming **[Observed]**.
4. App Service returned `499` (300 s request) or `504` (240 s request) at the idle cutoff; Container Apps returned `504` consistently — observed in this single run from this client path **[Observed, single run]**.
5. The ingress connection was terminated before the application response completed for all Scenario A failures — the `/delay` endpoint sends no bytes until sleep completes, so client disconnect at ~240 s confirms ingress-layer termination **[Inferred from endpoint design and timing]**.

## 13. What this does NOT prove

- The exact timeout for every App Service SKU, region, worker type, or Windows plan — only P1v3 Linux in `koreacentral` was tested
- Whether the ~240 s cutoff is stable across runs — single measurement per configuration; no repeatability data collected (Scenario D not executed)
- The timeout for internal ingress paths, private endpoints, Front Door, Application Gateway, API Management, or customer-managed reverse proxies
- Whether a streaming interval longer than 30 s (e.g., 180 s or 210 s) would also survive — only 30 s interval was tested
- Whether the `X-Accel-Buffering: no` header (set on SSE responses) affected the result for App Service — not isolated
- Whether the effective idle timer resets on *any* byte emitted or only on complete chunk boundaries
- Whether upstream client proxies, enterprise firewalls, or browser connections would impose shorter effective limits

## 14. Support takeaway

1. **"The server kept working but the client disconnected"**: Compare the client disconnect timestamp with the application's completion log (`delay_complete` / `stream_complete`). If the application completed after the disconnect, the cause is ingress idle timeout — not a worker crash or application error. Ask the customer for the exact request duration at failure.

2. **Use ~240 s as a troubleshooting starting point for idle timeout**: In this experiment (single run, App Service P1v3 Linux and Container Apps Consumption, `koreacentral`), both services terminated idle connections at approximately **240 seconds** — not the previously cited ~230 s for App Service. Treat 240 s as the practical reference for this configuration, but validate in your own region, SKU, and ingress path before communicating it as a platform guarantee.

3. **Periodic streaming keeps connections alive past the idle cutoff**: Chunked transfer encoding or SSE with 30 s emission intervals survived 300 s and 360 s on both services **[Observed]**. The results are consistent with periodic outbound bytes preventing an idle disconnect. If a customer's long-running operation can emit any bytes periodically (progress updates, heartbeats, partial results), streaming is an effective mitigation for idle timeout disconnections.

4. **Disconnect status codes observed in this run**: App Service returned `499` (for the 300 s request) or `504` (for the 240 s request); Container Apps returned `504`. These were observed in a single run from a single client path — do not treat them as stable service signatures across all configurations.

5. **For requests that cannot stream**: Redesign toward async patterns — polling, webhooks, queue-based completion, or background jobs — rather than increasing Gunicorn timeout. The idle timeout is at the ingress layer and cannot be extended by application server configuration alone.

## 15. Reproduction notes

- Keep Gunicorn timeout disabled (`--timeout 0`) or comfortably above the maximum test duration to avoid application-server false positives.
- Use `curl --no-buffer`; buffered clients can hide intermediate chunks and make streaming look ineffective.
- Keep replicas warm (`min-replicas 1` for Container Apps) to avoid cold-start latency contaminating timeout measurements.
- Run from a client path without additional proxies that may impose their own idle timeout.
- If a 240-second request finishes successfully in one run but fails in another, inspect exact chunk timestamps and client/proxy path differences before attributing the variance to Azure ingress.

## 16. Related guide / official docs

- [Azure App Service documentation](https://learn.microsoft.com/azure/app-service/)
- [Azure Container Apps documentation](https://learn.microsoft.com/azure/container-apps/)
- [Use Server-Sent Events in Flask patterns](https://developer.mozilla.org/docs/Web/API/Server-sent_events)
- [Existing cross-cutting experiment: Managed Identity RBAC Propagation vs Token Cache](../mi-rbac-propagation/overview.md)
- [Existing cross-cutting experiment: Private Endpoint Cutover and DNS Negative Caching](../pe-dns-negative-cache/overview.md)
