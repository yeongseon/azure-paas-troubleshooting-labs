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

!!! info "Status: Draft - Awaiting Execution"
    Experiment design completed, but Azure resources have not been created and no runtime data has been collected yet.

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
| Date tested | Not yet tested |

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

Not executed yet.

Populate this section after running the matrix in section 8.

Suggested subsections:

- 10.1 Non-streaming delay results by duration
- 10.2 Chunked streaming results
- 10.3 SSE results
- 10.4 App Service vs Container Apps comparison
- 10.5 Sample client transcript and server log correlation

## 11. Interpretation

Not executed yet.

When data is available, interpret using explicit evidence tags:

- **Observed**: exact disconnect signatures and log timestamps
- **Measured**: cutoff windows and successful completion durations
- **Inferred**: whether emitted bytes reset ingress idle timers
- **Not Proven**: any conclusion about undocumented internal proxy implementation details

## 12. What this proves

After execution, this experiment should be able to prove only the following types of statements, if supported by evidence:

- the observed idle cutoff window for App Service under this exact configuration
- the observed idle cutoff window for Container Apps under this exact configuration
- whether 30-second chunked streaming preserved the connection beyond the non-streaming cutoff
- whether 30-second SSE preserved the connection beyond the non-streaming cutoff

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- the timeout for every App Service SKU, region, worker type, or Windows plan
- the timeout for internal ingress paths, private endpoints, Front Door, Application Gateway, API Management, or customer-managed reverse proxies
- whether all streaming intervals work; only the tested cadence(s) are covered
- whether upstream libraries, browsers, or enterprise proxies introduce shorter client-side idle limits

## 14. Support takeaway

Planned support guidance this experiment should validate:

- For long-running synchronous HTTP endpoints, treat ~230s on App Service and ~240s on Container Apps as suspected ingress idle timeout boundaries until evidence says otherwise.
- If the operation legitimately exceeds that window, redesign toward streaming progress, polling, webhooks, queue-based async completion, or background job patterns.
- When a customer says "the server kept working but the client disconnected," compare client disconnect time with application completion logs to distinguish ingress timeout from worker crash.
- Ask whether any progress bytes are emitted. A streaming response that flushes periodically may survive where a silent delayed response fails.

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
