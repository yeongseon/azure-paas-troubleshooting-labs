---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-04-12"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Burst Scaling Queueing Before Replica Add

!!! info "Status: Published"
    Experiment completed with real data on 2026-04-12. Tested 7 configurations covering cold start, warm burst baseline, concurrency thresholds (5/10/20/50), polling intervals (10s/30s/60s), and cooldown period impact.

## 1. Question

Under sudden HTTP burst traffic, how much queueing happens before Azure Container Apps adds replicas, and which HTTP scaling settings actually reduce `5xx` rates and tail latency during scale-out?

## 2. Why this matters

Customers often interpret burst-time `502`/`503` responses or very high `p95`/`p99` latency as evidence that Container Apps "could not handle load," even when average load is low and steady-state throughput is acceptable. In practice, the confusing part is the **transition window** between the moment traffic surges and the moment new replicas become available.

This matters for support because:

- many workloads are mostly idle, then receive webhook, campaign, or API burst traffic
- `minReplicas=1` is commonly assumed to solve all burst issues, even though it only removes scale-from-zero delay
- the default HTTP scaler threshold (`concurrentRequests=10`) may fit steady traffic but react too slowly to short spikes
- customers often tune `cooldownPeriod` expecting faster scale-out, even though it primarily affects scale-in timing
- tail latency and `5xx` responses during the first 10-60 seconds can be more important than average throughput

The experiment is intended to separate:

1. cold-start contribution when the app begins at `0` replicas
2. warm burst queueing when the app begins at `1` replica
3. the effect of `concurrentRequests` threshold on scale trigger sensitivity
4. the effect of `pollingInterval` on how quickly scaling reacts to the burst
5. the non-effect of `cooldownPeriod` on the initial scale-out decision

## 3. Customer symptom

Typical ticket phrasing:

- "Short traffic spikes cause timeouts before autoscale catches up."
- "Container Apps eventually scales out, but users already got `503` or very slow responses."
- "`minReplicas=1` helped cold starts but did not stop burst failures."
- "We lowered `cooldownPeriod`, but burst latency did not improve."
- "What should we tune first: min replicas, concurrent requests, or polling interval?"

## 4. Hypothesis

1. **Default HTTP scaling** with `concurrentRequests=10` may not react quickly enough for short bursts, causing transient queueing on the initial replica before additional replicas are ready.
2. **`pollingInterval`** is a major contributor to burst response lag; lower values such as `10s` should reduce time-to-scale compared with `30s` or `60s`.
3. **`cooldownPeriod`** affects how long replicas remain after traffic falls, but should not materially improve initial scale-out speed.
4. **`minReplicas > 0`** removes scale-from-zero cold start, but does not by itself eliminate queueing during a burst that exceeds one replica's capacity.
5. **Lower `concurrentRequests` thresholds** (for example `5`) should trigger scale-out earlier than `10`, `20`, or `50`, reducing `p99` latency and `5xx` rate at the cost of more aggressive scaling.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 custom container |
| OS | Linux |
| Test app | HTTP service with configurable per-request latency and request timing headers |
| Ingress | External, target port `8080` |
| Scaling | HTTP rule with configurable `concurrentRequests`; environment-level `pollingInterval` and `cooldownPeriod` |
| Load tools | `hey` or `wrk` from external Linux VM / Cloud Shell |
| Logging | Log Analytics + Container Apps system/console logs + Azure Monitor metrics |
| Date tested | 2026-04-12 |

## 6. Variables

**Experiment type**: Performance / scaling behavior comparison

**Controlled:**

- same Container Apps environment and region
- same app image and code
- same CPU / memory allocation per replica
- same target port and ingress mode
- same maximum replica limit unless explicitly changed
- same burst duration, request payload size, and client location for comparable runs
- same baseline artificial server latency (for example `250 ms`) unless noted otherwise

**Independent variables:**

- starting replica count: `0` vs `1`
- HTTP scaler `concurrentRequests`: `5`, `10`, `20`, `50`
- environment `pollingInterval`: `10`, `30`, `60` seconds
- environment `cooldownPeriod`: baseline `300` seconds, optional comparison `60` seconds
- burst profile: short spike, step burst, sustained burst

**Observed:**

- time from burst start to first additional replica creation
- time from burst start to first additional replica becoming ready
- replica count over time
- HTTP status distribution (`200`, `429`, `502`, `503`, client timeout)
- `p50`, `p95`, `p99`, and max latency during the burst window
- request queueing signal inferred from app-side wait time and latency inflation
- scale-related system log messages
- app-side timestamps showing when each replica began serving requests

**Independent run definition**: one clean deployment or configuration state, followed by one burst test after confirming the intended starting replica count and idle/warm condition

**Planned runs per configuration**: minimum `5` independent runs

**Warm-up exclusion rule**: exclude pre-burst verification requests from latency analysis; include all burst requests

**Primary metrics**: time to second replica ready, burst-window `p99` latency, burst-window `5xx` rate

**Meaningful effect threshold**:

- time-to-scale change of `>= 10s`
- `p99` latency change of `>= 25%`
- absolute `5xx` rate change of `>= 1 percentage point`

## 7. Instrumentation

Planned evidence sources:

- **External load generator**: `hey` for repeatable concurrent HTTP bursts; optional `wrk` for higher-rate bursts
- **ContainerAppSystemLogs_CL**: revision lifecycle, replica creation, scaling events, environment-level events
- **ContainerAppConsoleLogs_CL**: app log markers for request arrival, service start, and per-replica identifiers
- **Azure CLI**: environment configuration, revision inspection, replica listing
- **Azure Monitor metrics**: request count, response code breakdown, latency, replica count if exposed in the selected metric namespace

Recommended application log markers:

- `APP_START`
- `REQUEST_START`
- `REQUEST_END`
- `REPLICA_ID`
- `ARTIFICIAL_DELAY_MS`
- `INFLIGHT_COUNT`

### Test application example

```python
import os
import time
import socket
from datetime import datetime, timezone
from flask import Flask, jsonify, request

app = Flask(__name__)
HOSTNAME = socket.gethostname()
APP_START_MONO = time.monotonic()
APP_START_UTC = datetime.now(timezone.utc).isoformat()
BASE_DELAY_MS = int(os.getenv("BASE_DELAY_MS", "250"))
EXTRA_DELAY_MS = int(os.getenv("EXTRA_DELAY_MS", "0"))
INFLIGHT = 0

@app.route("/")
def index():
    global INFLIGHT
    request_start = time.monotonic()
    request_start_utc = datetime.now(timezone.utc).isoformat()
    INFLIGHT += 1
    inflight_at_start = INFLIGHT

    try:
        time.sleep((BASE_DELAY_MS + EXTRA_DELAY_MS) / 1000)
        return jsonify({
            "status": "ok",
            "hostname": HOSTNAME,
            "app_start_utc": APP_START_UTC,
            "request_start_utc": request_start_utc,
            "response_utc": datetime.now(timezone.utc).isoformat(),
            "service_time_ms": BASE_DELAY_MS + EXTRA_DELAY_MS,
            "inflight_at_start": inflight_at_start,
            "uptime_seconds": round(time.monotonic() - APP_START_MONO, 3)
        })
    finally:
        INFLIGHT -= 1
```

### Load test scripts

#### Short burst with `hey`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
TOTAL_REQUESTS="${2:-400}"
CONCURRENCY="${3:-100}"
OUTDIR="${4:-results/hey-short-burst}"

mkdir -p "$OUTDIR"

hey \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENCY" \
  -disable-keepalive \
  -o csv \
  "$URL" > "$OUTDIR/hey.csv"
```

#### Sustained burst with `wrk`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
DURATION="${2:-90s}"
CONNECTIONS="${3:-200}"
THREADS="${4:-4}"
OUTDIR="${5:-results/wrk-sustained-burst}"

mkdir -p "$OUTDIR"

wrk \
  --latency \
  -t "$THREADS" \
  -c "$CONNECTIONS" \
  -d "$DURATION" \
  "$URL" | tee "$OUTDIR/wrk.txt"
```

#### Step-burst pattern using `curl`

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
OUTFILE="${2:-results/step-burst.csv}"

mkdir -p "$(dirname "$OUTFILE")"
printf 'phase,ts_utc,http_code,time_total,errormsg\n' > "$OUTFILE"

run_phase() {
  local phase="$1"
  local requests_per_phase="$2"
  local parallelism="$3"

  seq "$requests_per_phase" | xargs -I{} -P "$parallelism" bash -c '
    ts_utc="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")"
    result="$({ curl -skS "$0" -o /dev/null -w "%{http_code},%{time_total},%{errormsg}" --max-time 15; } 2>&1 || true)"
    printf "%s,%s,%s\n" "$1" "$ts_utc" "$result"
  ' "$URL" "$phase" >> "$OUTFILE"
}

run_phase warmup 20 2
sleep 10
run_phase burst_25 100 25
sleep 15
run_phase burst_100 400 100
sleep 15
run_phase burst_200 800 200
```

### Replica / metric collection helpers

```bash
#!/usr/bin/env bash
set -euo pipefail

RG="$1"
APP="$2"
OUTFILE="${3:-results/replicas.csv}"

mkdir -p "$(dirname "$OUTFILE")"
printf 'ts_utc,replica_count,replicas\n' > "$OUTFILE"

while true; do
  ts_utc="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")"
  replicas_json="$(az containerapp replica list --resource-group "$RG" --name "$APP" --output json)"
  replica_count="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' <<< "$replicas_json")"
  replicas_flat="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(";".join(sorted(x.get("name","unknown") for x in data)))' <<< "$replicas_json")"
  printf '%s,%s,%s\n' "$ts_utc" "$replica_count" "$replicas_flat" >> "$OUTFILE"
  sleep 2
done
```

### Kusto queries

```kusto
// Scaling / replica lifecycle timeline
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-burst-scaling"
| where TimeGenerated between (datetime(2026-04-12T00:00:00Z) .. datetime(2026-04-12T01:00:00Z))
| project TimeGenerated, RevisionName_s, ReplicaName_s, Reason_s, Log_s
| order by TimeGenerated asc
```

```kusto
// Application-side request markers and replica identifiers
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-burst-scaling"
| where TimeGenerated between (datetime(2026-04-12T00:00:00Z) .. datetime(2026-04-12T01:00:00Z))
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated asc
```

```kusto
// Error-focused view during the burst window
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-burst-scaling"
| where Log_s has_any ("scale", "replica", "failed", "503", "502", "timeout")
| project TimeGenerated, ReplicaName_s, Reason_s, Log_s
| order by TimeGenerated asc
```

## 8. Procedure

### 8.1 Infrastructure setup

```bash
# Resource group
az group create \
  --name rg-aca-burst-scaling-lab \
  --location koreacentral

# Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group rg-aca-burst-scaling-lab \
  --workspace-name law-aca-burst-scaling \
  --location koreacentral

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group rg-aca-burst-scaling-lab \
  --workspace-name law-aca-burst-scaling \
  --query customerId -o tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group rg-aca-burst-scaling-lab \
  --workspace-name law-aca-burst-scaling \
  --query primarySharedKey -o tsv)

# Container Apps environment
az containerapp env create \
  --name cae-burst-scaling-lab \
  --resource-group rg-aca-burst-scaling-lab \
  --location koreacentral \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY"

# ACR
az acr create \
  --name acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --sku Basic \
  --admin-enabled true \
  --location koreacentral
```

### 8.2 Build and push the test image

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
```

```bash
az acr build \
  --registry acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --image burst-scaling-app:v1 \
  --file Dockerfile .
```

### 8.3 Deploy baseline Container App

```bash
ACR_USER=$(az acr credential show \
  --name acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --query username -o tsv)

ACR_PASS=$(az acr credential show \
  --name acrburstscalinglab \
  --resource-group rg-aca-burst-scaling-lab \
  --query "passwords[0].value" -o tsv)

az containerapp create \
  --name ca-burst-scaling \
  --resource-group rg-aca-burst-scaling-lab \
  --environment cae-burst-scaling-lab \
  --image acrburstscalinglab.azurecr.io/burst-scaling-app:v1 \
  --registry-server acrburstscalinglab.azurecr.io \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 10 \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars BASE_DELAY_MS=250 EXTRA_DELAY_MS=0
```

Record the public URL:

```bash
APP_URL=$(az containerapp show \
  --name ca-burst-scaling \
  --resource-group rg-aca-burst-scaling-lab \
  --query properties.configuration.ingress.fqdn -o tsv)
APP_URL="https://${APP_URL}/"
```

### 8.4 Environment-level scaler timing variants

Container Apps environment settings must be adjusted between scenario groups.

```bash
# Example: set polling interval to 10s and cooldown to 300s
az containerapp env update \
  --name cae-burst-scaling-lab \
  --resource-group rg-aca-burst-scaling-lab \
  --keda-config polling-interval=10 cooldown-period=300

# Example: revert to 30s polling interval
az containerapp env update \
  --name cae-burst-scaling-lab \
  --resource-group rg-aca-burst-scaling-lab \
  --keda-config polling-interval=30 cooldown-period=300
```

If the CLI syntax for `--keda-config` changes, capture the exact command version used in the final execution notes.

### 8.5 App-level scaling variants

For each `concurrentRequests` threshold, update the app and wait for the revision to stabilize.

```bash
az containerapp update \
  --name ca-burst-scaling \
  --resource-group rg-aca-burst-scaling-lab \
  --min-replicas 1 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 5
```

Repeat for `10`, `20`, and `50`.

### 8.6 Scenario matrix

| Scenario | Start state | `concurrentRequests` | `pollingInterval` | `cooldownPeriod` | Burst pattern | Goal |
|---|---|---:|---:|---:|---|---|
| 1 | `minReplicas=0`, verified 0 replicas | 10 | 30s | 300s | short burst | cold start + scale-out combined |
| 2 | `minReplicas=1`, warm single replica | 10 | 30s | 300s | short burst | warm burst baseline |
| 3 | `minReplicas=1`, warm single replica | 5 / 10 / 20 / 50 | 30s | 300s | short burst | concurrency threshold comparison |
| 4 | `minReplicas=1`, warm single replica | 10 | 10s / 30s / 60s | 300s | short burst | polling interval comparison |
| 5 | `minReplicas=1`, warm single replica | 10 | 30s | 60s / 300s | short burst | prove cooldown affects scale-in, not initial scale-out |
| 6 | `minReplicas=1`, warm single replica | best two thresholds | best polling interval | 300s | sustained burst | see whether short-burst gains persist |

### 8.7 Execution sequence per independent run

1. Apply the intended environment and app scaling configuration.
2. Wait until the latest revision is healthy and the previous scenario's traffic has ceased.
3. For start-from-zero scenarios, confirm zero replicas with `az containerapp replica list`.
4. For warm scenarios, send a few low-rate requests and confirm exactly one active replica if possible.
5. Start the replica polling helper at `2s` intervals.
6. Start one load script (`hey`, `wrk`, or step burst) and capture raw output.
7. Immediately after the burst, export system and console logs for the matching time window.
8. Record:
    - burst start timestamp
    - first non-200 timestamp
    - first second-replica observed timestamp
    - first second-replica ready/serving timestamp
    - last non-200 timestamp
9. Allow the app to settle, then stop polling and archive all outputs in a scenario/run-specific folder.
10. Repeat until at least `5` independent runs exist for the configuration.

## 9. Expected signal

- **Scenario 1 (0 replicas)** should show the worst user experience because cold start and queueing overlap; latency will be dominated by first replica startup plus scale-out lag.
- **Scenario 2 (1 replica)** should avoid the cold-start penalty but still show elevated `p99` latency and possible `503`/timeout responses while the first replica is saturated.
- **Lower `concurrentRequests` thresholds** should produce earlier replica growth, lower `p99`, and lower `5xx` rates.
- **Shorter `pollingInterval`** should shift the first scale event earlier by roughly one polling cycle relative to slower settings.
- **Changing `cooldownPeriod` alone** should not materially change the timestamp of the first scale-out event under the same burst profile.

## 10. Results

### 10.1 Scenario summary table

Measured burst profile for all scenarios unless noted otherwise: `400` requests, `100` concurrent, keepalive disabled, artificial service time `250 ms`, `0.5 CPU`, `1 GiB`, max replicas `10`.

| Scenario | Start | `concurrentRequests` | `pollingInterval` | `cooldownPeriod` | Total Reqs | Success | Failures | Failure % | Avg (ms) | `p50` (ms) | `p95` (ms) | `p99` (ms) | RPS |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S1: Cold start | 0 replicas | 10 | 30s | 300s | 400 | 300 | 100 | 25.0% | 5,255 | 2,415 | 13,821 | 14,332 | 10.69 |
| S2: Warm baseline | 1 replica | 10 | 30s | 300s | 400 | 400 | 0 | 0.0% | 724 | 703 | 969 | 992 | 127.97 |
| S3a: threshold = 5 | 1 replica | 5 | 30s | 300s | 400 | 400 | 0 | 0.0% | 745 | 717 | 988 | 1,734 | 82.23 |
| S3b: threshold = 20 | 1 replica | 20 | 30s | 300s | 400 | 400 | 0 | 0.0% | 774 | 737 | 966 | 1,712 | 72.16 |
| S3c: threshold = 50 | 1 replica | 50 | 30s | 300s | 400 | 400 | 0 | 0.0% | 772 | 732 | 982 | 1,113 | 53.75 |
| S4a: poll = 10s | 1 replica | 10 | 10s | 300s | 400 | 400 | 0 | 0.0% | 814 | 706 | 1,726 | 1,739 | 100.46 |
| S4b: poll = 60s | 1 replica | 10 | 60s | 300s | 400 | 400 | 0 | 0.0% | 750 | 725 | 992 | 1,005 | 123.72 |
| S5: cooldown = 60s | 1 replica | 10 | 30s | 60s | 400 | 400 | 0 | 0.0% | 760 | 720 | 1,022 | 1,755 | 101.28 |

### 10.2 Scenario details

- **S1: Cold start**
    - Burst start: `14:51:19 UTC`
    - [Measured] `300/400` requests succeeded and `100/400` timed out (`25.0%` failure rate).
    - [Measured] Average latency was `5,255 ms`; `p50` was `2,415 ms`; `p95` was `13,821 ms`; `p99` was `14,332 ms`; slowest request was `14,336 ms`.
    - [Measured] Throughput was `10.69` requests/sec.
    - [Observed] System logs showed scale to `5` replicas at `14:51:25 UTC` (`6s` after burst start) and scale to `10` replicas at `14:51:40 UTC` (`21s` after burst start).
    - [Observed] Timed-out requests reported `context deadline exceeded (Client.Timeout exceeded while awaiting headers)`.
- **S2: Warm baseline**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `724 ms`; `p50` was `703 ms`; `p95` was `969 ms`; `p99` was `992 ms`.
    - [Measured] Throughput was `127.97` requests/sec and total burst time was `3.13s`, versus `37.42s` for S1.
- **S3a: `concurrentRequests=5`**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `745 ms`; `p50` was `717 ms`; `p95` was `988 ms`; `p99` was `1,734 ms`.
    - [Measured] Throughput was `82.23` requests/sec and total burst time was `4.86s`.
- **S3b: `concurrentRequests=20`**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `774 ms`; `p50` was `737 ms`; `p95` was `966 ms`; `p99` was `1,712 ms`.
    - [Measured] Throughput was `72.16` requests/sec and total burst time was `5.54s`.
- **S3c: `concurrentRequests=50`**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `772 ms`; `p50` was `732 ms`; `p95` was `982 ms`; `p99` was `1,113 ms`.
    - [Measured] Throughput was `53.75` requests/sec and total burst time was `7.44s`.
- **S4a: `pollingInterval=10s`**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `814 ms`; `p50` was `706 ms`; `p95` was `1,726 ms`; `p99` was `1,739 ms`.
    - [Measured] Throughput was `100.46` requests/sec and total burst time was `3.98s`.
- **S4b: `pollingInterval=60s`**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `750 ms`; `p50` was `725 ms`; `p95` was `992 ms`; `p99` was `1,005 ms`.
    - [Measured] Throughput was `123.72` requests/sec and total burst time was `3.23s`.
- **S5: `cooldownPeriod=60s`**
    - [Measured] `400/400` requests succeeded with `0` failures.
    - [Measured] Average latency was `760 ms`; `p50` was `720 ms`; `p95` was `1,022 ms`; `p99` was `1,755 ms`.
    - [Measured] Throughput was `101.28` requests/sec and total burst time was `3.95s`.

### 10.3 Raw artifacts preserved

- `hey` outputs for all burst scenarios
- Kusto query results for system and console logs
- scaling timeline showing replica increases during the cold-start scenario
- CLI snapshots for scaling configuration and replica state

## 11. Interpretation

- [Measured] Cold start was the only tested scenario with user-visible failures: S1 had `25.0%` timeouts, while every warm-start scenario completed `400/400` requests successfully.
- [Correlated] The switch from `minReplicas=0` to `minReplicas=1` aligned with the elimination of burst failures and with a large latency reduction from `14,332 ms` `p99` in S1 to `992 ms` `p99` in S2.
- [Observed] In S1, scale-out started after the burst had already begun: system logs showed scale to `5` replicas `6s` after burst start and to `10` replicas `21s` after burst start.
- [Inferred] For this short burst shape, the dominant penalty window was image pull plus container startup after scale-from-zero, not HTTP scaler threshold tuning on an already warm replica.
- [Measured] Changing `concurrentRequests` from `5` to `20` to `50` did not change success rate; all three scenarios had `0.0%` failures. Latency stayed within a relatively narrow band for averages (`745-774 ms`) and `p95` (`966-988 ms`), with some `p99` variation (`1,113-1,734 ms`).
- [Not Proven] Lower `concurrentRequests` thresholds materially improved short-burst outcomes for this workload. The expected earlier trigger sensitivity did not produce a measurable reliability advantage during a burst that finished in `4.86-7.44s`.
- [Measured] Changing `pollingInterval` from `10s` to `60s` also produced `0.0%` failures in both tests. Average latency and `p99` varied, but neither setting changed the burst outcome from success to failure.
- [Not Proven] Shorter `pollingInterval` materially improved this short-burst scenario. The tested burst completed in `3.23-3.98s`, which is shorter than even the first polling cycle.
- [Measured] `cooldownPeriod=60s` and `cooldownPeriod=300s` both completed with `0.0%` failures and similar latency characteristics, with no evidence that cooldown changed initial burst protection.
- [Inferred] The warm single replica absorbed `100` concurrent clients despite only `8` gunicorn threads because requests were buffered before service completion rather than immediately rejected.
- [Strongly Suggested] For short, steep HTTP bursts on Azure Container Apps, keeping at least one warm replica is the highest-impact control for reducing timeout risk.

## 12. What this proves

- [Measured] In this workload, `minReplicas=0` caused a measurable cold-start failure window: `100` of `400` requests timed out and `p99` reached `14,332 ms`.
- [Observed] Extra replicas were added after burst onset in the cold-start case, with scale events logged at `+6s` and `+21s` from burst start.
- [Correlated] Keeping one warm replica removed the measured timeout failures for the same burst profile, reducing the dominant customer-visible issue from timeouts to queueing latency.
- [Measured] Lowering or raising `concurrentRequests` across `5`, `10`, `20`, and `50` did not change success rate for this short burst; all warm scenarios completed without `5xx` or timeout failures.
- [Not Proven] Adjusting `concurrentRequests` materially changes short-burst protection for this specific app shape. The data does not show a reliability improvement from more aggressive thresholds.
- [Measured] Changing `pollingInterval` between `10s` and `60s` did not materially alter short-burst success for this test because the burst completed before the scaler interval could matter operationally.
- [Measured] Changing `cooldownPeriod` from `300s` to `60s` did not improve initial scale-out behavior.
- [Inferred] Azure Container Apps ingress buffered excess warm-burst requests effectively enough to avoid `502`/`503` responses under this test, even when concurrency at the client far exceeded app worker thread count.

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- behavior for non-HTTP scalers such as Service Bus, Kafka, or custom KEDA triggers
- behavior for workloads with very different startup costs, CPU profiles, or upstream dependency latency
- platform-wide guarantees for all regions, environments, or future Container Apps releases
- exact internal implementation details of the managed Envoy / KEDA integration beyond what is externally observable
- the best production setting for every customer cost/performance tradeoff

## 14. Support takeaway

- If the symptom is **first burst after idle**, treat `minReplicas=0` as the primary risk factor first. This experiment measured `25.0%` timeouts only in the cold-start scenario.
- If the symptom is **short burst with an already warm app**, do not assume that lowering `concurrentRequests` or `pollingInterval` will help. In this test, those settings did not change reliability for a burst that finished within a few seconds.
- Do not position `cooldownPeriod` as a burst-protection knob. The `60s` cooldown run behaved like the `300s` baseline during initial scale-out.
- Capture both the **request timeline** and the **system scaling timeline**. The useful support story here was the combination of client timeouts plus observed scale events at `+6s` and `+21s`.
- For similar short-burst workloads, start guidance with **keep one warm replica**, then evaluate whether remaining pain is acceptable queueing latency rather than autoscale failure.

## 15. Reproduction notes

- Keep client location stable; cross-region client variance can mask burst-time effects.
- Disable keep-alive for the short-burst test if the goal is to maximize concurrency pressure at ingress.
- Use a deliberately modest app service time (for example `250 ms`) so the first replica can saturate under burst load without the app being unrealistically slow.
- For scale-from-zero scenarios, confirm zero replicas immediately before the burst; waiting too long after verification can invalidate the run.
- Preserve exact CLI versions and command syntax, especially if `az containerapp env update --keda-config` behavior changes.
- If `hey` and `wrk` disagree substantially, prefer the raw per-request artifact that best matches the customer traffic pattern under investigation.

## 16. Related guide / official docs

- [Azure Container Apps scaling](https://learn.microsoft.com/azure/container-apps/scale-app)
- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/scale-app#http)
- [Azure Container Apps environment](https://learn.microsoft.com/azure/container-apps/environment)
- [Azure Monitor for Container Apps](https://learn.microsoft.com/azure/container-apps/log-monitoring)
- [Scale-to-Zero First Request 503/Timeout](../scale-to-zero-502/overview.md)
- [Revision Update Downtime During Container Apps Deployments](../revision-update-downtime/overview.md)
