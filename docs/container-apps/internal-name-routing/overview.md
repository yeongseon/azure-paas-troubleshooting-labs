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

# Internal Name vs FQDN Routing in Azure Container Apps

!!! info "Status: Published"
    Experiment completed with real data on 2026-04-12.

## 1. Question

Why does calling a Container App by internal name (for example, `http://app-name:80`) fail intermittently while the app FQDN consistently works, and what is different in the routing path?

## 2. Why this matters

This is a real support scenario, not a hypothetical one. In [GitHub issue #1315](https://github.com/microsoft/azure-container-apps/issues/1315), customers reported `Connection refused` when calling a peer Container App by internal name under moderate load, while the fully qualified domain name (FQDN) continued to work. Microsoft confirmed that the two paths are different: internal-name traffic can traverse Envoy sidecars, while FQDN traffic goes through the ingress Envoy path.

That distinction matters for support because the symptom can look like random application instability even when the app, image, and destination port are healthy. If the routing path itself differs, the correct mitigation is not only "check the app" but also "change how the app is addressed" and collect the right evidence for escalation.

## 3. Customer symptom

- "Service-to-service calls to `http://callee:80` fail with `Connection refused` during load tests."
- "The same destination works when called by `https://<callee-fqdn>`."
- "Single requests usually pass, but error rate rises when traffic increases."
- "The app looks healthy from ingress, but peer-to-peer calls are unstable."

## 4. Hypothesis

1. Internal-name routing uses a different data path from FQDN routing.
2. Internal-name routing is more dependent on per-replica Envoy sidecars and will show a higher failure rate under load.
3. FQDN routing uses the environment ingress Envoy path and remains more stable at the same offered load.
4. HTTP failures will be easiest to reproduce; raw TCP behavior may differ because protocol handling is not identical across paths.
5. If Microsoft's stated ingress-only consolidation reaches this scenario, the behavioral gap should narrow or disappear in future platform versions.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption environment |
| Region | Korea Central |
| Runtime | Python 3.11 custom containers |
| OS | Linux |
| Date designed | 2026-04-12 |
| Date executed | 2026-04-12 |
| Topology | One caller app, one callee app |
| Load tool | `hey` |

## 6. Variables

**Experiment type**: Load / networking

**Controlled:**

- Same Container Apps environment for caller and callee
- Same callee image, revision, CPU/memory, and replica settings across scenarios
- Same caller implementation across scenarios
- Same request path (`/echo`) and payload size for HTTP tests
- Same duration and concurrency profile for each load phase
- Same region (`koreacentral`)

**Observed:**

- HTTP success rate and failure rate by access mode
- Error type (`connection refused`, timeout, 5xx, client exception)
- End-to-end latency as observed by caller
- Caller and callee logs during each run
- Replica count changes during each run
- Optional TCP probe success/failure rate

## 7. Instrumentation

- `hey` for reproducible low, moderate, and high request pressure
- Caller app structured JSON logging per downstream call
- Callee app request logging with timestamp and hostname
- `az containerapp logs show` for caller and callee console/system logs
- `az monitor metrics list` for requests, response time, and replica count
- Log Analytics queries for error-rate summaries by mode
- Optional `az containerapp exec` into caller for ad hoc `curl`, `nc`, and DNS checks

## 8. Procedure

### 8.1 Infrastructure setup

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export RG="rg-aca-internal-name-routing-lab"
export LOCATION="koreacentral"
export ENV_NAME="cae-internal-name-routing"
export LAW_NAME="law-internal-name-routing"
export ACR_NAME="acrinternalname$RANDOM"
export CALLER_APP="caller-app"
export CALLEE_APP="callee-app"

az account set --subscription "$SUBSCRIPTION_ID"
az group create --name "$RG" --location "$LOCATION"

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW_NAME" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
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
  --name "$ENV_NAME" \
  --location "$LOCATION" \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY"
```

### 8.2 Application code

`callee-app/app.py`:

```python
from flask import Flask, jsonify, request
from datetime import datetime, timezone
import os
import socket
import threading

app = Flask(__name__)
TCP_PORT = int(os.getenv("TCP_PORT", "9090"))


@app.get("/echo")
def echo():
    return jsonify(
        {
            "status": "ok",
            "path": request.path,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "remote_addr": request.remote_addr,
            "host_header": request.host,
        }
    )


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy", "hostname": socket.gethostname()})


def tcp_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", TCP_PORT))
    srv.listen(128)
    while True:
        conn, addr = srv.accept()
        try:
            payload = conn.recv(4096).decode("utf-8", errors="replace").strip()
            response = (
                f"pong from {socket.gethostname()} at "
                f"{datetime.now(timezone.utc).isoformat()} recv={payload}\n"
            )
            conn.sendall(response.encode("utf-8"))
        finally:
            conn.close()


threading.Thread(target=tcp_server, daemon=True).start()
```

`callee-app/requirements.txt`:

```text
flask==3.1.1
gunicorn==23.0.0
```

`callee-app/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8080 9090
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
```

`caller-app/app.py`:

```python
from flask import Flask, jsonify, request
from datetime import datetime, timezone
import os
import requests
import socket
import ssl
import time

app = Flask(__name__)

CALLEE_NAME = os.getenv("CALLEE_NAME", "callee-app")
CALLEE_FQDN = os.getenv("CALLEE_FQDN", "")
INTERNAL_HTTP_URL = os.getenv("INTERNAL_HTTP_URL", f"http://{CALLEE_NAME}:80/echo")
FQDN_HTTPS_URL = os.getenv("FQDN_HTTPS_URL", f"https://{CALLEE_FQDN}/echo")
TCP_HOST = os.getenv("TCP_HOST", CALLEE_NAME)
TCP_PORT = int(os.getenv("TCP_PORT", "9090"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "5"))


def record(result):
    print(result, flush=True)
    return result


@app.get("/invoke")
def invoke():
    mode = request.args.get("mode", "internal-http")
    started = time.perf_counter()
    base = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "caller_hostname": socket.gethostname(),
    }

    try:
        if mode == "internal-http":
            resp = requests.get(INTERNAL_HTTP_URL, timeout=REQUEST_TIMEOUT)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            return jsonify(record({
                **base,
                "target": INTERNAL_HTTP_URL,
                "http_status": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "success": resp.ok,
                "body": resp.json(),
            }))

        if mode == "fqdn-https":
            resp = requests.get(FQDN_HTTPS_URL, timeout=REQUEST_TIMEOUT)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            return jsonify(record({
                **base,
                "target": FQDN_HTTPS_URL,
                "http_status": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "success": resp.ok,
                "body": resp.json(),
            }))

        if mode == "internal-tcp":
            with socket.create_connection((TCP_HOST, TCP_PORT), timeout=REQUEST_TIMEOUT) as s:
                s.sendall(b"ping\n")
                payload = s.recv(4096).decode("utf-8", errors="replace").strip()
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            return jsonify(record({
                **base,
                "target": f"tcp://{TCP_HOST}:{TCP_PORT}",
                "elapsed_ms": elapsed_ms,
                "success": True,
                "payload": payload,
            }))

        return jsonify(record({**base, "success": False, "error": f"unsupported mode: {mode}"})), 400

    except Exception as ex:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return jsonify(record({
            **base,
            "elapsed_ms": elapsed_ms,
            "success": False,
            "error_type": type(ex).__name__,
            "error": str(ex),
        })), 502


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy", "hostname": socket.gethostname()})
```

`caller-app/requirements.txt`:

```text
flask==3.1.1
gunicorn==23.0.0
requests==2.32.3
```

`caller-app/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl netcat-openbsd ca-certificates \
  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
```

!!! note "Why the caller app is part of the experiment"
    The GitHub issue is about service-to-service traffic inside the Container Apps environment. The caller app makes the downstream request so the comparison stays inside the platform boundary instead of mixing in laptop DNS, corporate proxy, or public internet variables.

### 8.3 Deploy

```bash
mkdir -p callee-app caller-app

# Write the files from section 8.2 into the two directories.

az acr build \
  --registry "$ACR_NAME" \
  --image callee-routing-test:v1 \
  --file callee-app/Dockerfile \
  callee-app

az acr build \
  --registry "$ACR_NAME" \
  --image caller-routing-test:v1 \
  --file caller-app/Dockerfile \
  caller-app

ACR_LOGIN_SERVER=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --query loginServer --output tsv)

ACR_USERNAME=$(az acr credential show \
  --name "$ACR_NAME" \
  --query username --output tsv)

ACR_PASSWORD=$(az acr credential show \
  --name "$ACR_NAME" \
  --query "passwords[0].value" --output tsv)

az containerapp create \
  --resource-group "$RG" \
  --name "$CALLEE_APP" \
  --environment "$ENV_NAME" \
  --image "$ACR_LOGIN_SERVER/callee-routing-test:v1" \
  --target-port 8080 \
  --ingress external \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars TCP_PORT=9090

CALLEE_FQDN=$(az containerapp show \
  --resource-group "$RG" \
  --name "$CALLEE_APP" \
  --query properties.configuration.ingress.fqdn --output tsv)

az containerapp create \
  --resource-group "$RG" \
  --name "$CALLER_APP" \
  --environment "$ENV_NAME" \
  --image "$ACR_LOGIN_SERVER/caller-routing-test:v1" \
  --target-port 8080 \
  --ingress external \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars \
    CALLEE_NAME="$CALLEE_APP" \
    CALLEE_FQDN="$CALLEE_FQDN" \
    INTERNAL_HTTP_URL="http://$CALLEE_APP:80/echo" \
    FQDN_HTTPS_URL="https://$CALLEE_FQDN/echo" \
    TCP_HOST="$CALLEE_APP" \
    TCP_PORT=9090 \
    REQUEST_TIMEOUT=5

CALLER_FQDN=$(az containerapp show \
  --resource-group "$RG" \
  --name "$CALLER_APP" \
  --query properties.configuration.ingress.fqdn --output tsv)

echo "Callee FQDN: $CALLEE_FQDN"
echo "Caller FQDN: $CALLER_FQDN"
```

### 8.4 Pre-flight validation

Run these checks before load so failures can be attributed to routing behavior rather than a broken baseline.

```bash
curl --fail --silent "https://$CALLER_FQDN/healthz"
curl --fail --silent "https://$CALLEE_FQDN/healthz"

curl --silent "https://$CALLER_FQDN/invoke?mode=internal-http" | jq .
curl --silent "https://$CALLER_FQDN/invoke?mode=fqdn-https" | jq .

# Optional: inspect name resolution and raw connectivity from inside caller
az containerapp exec \
  --resource-group "$RG" \
  --name "$CALLER_APP" \
  --command "sh"

# Inside the shell:
getent hosts "$CALLEE_APP"
curl -v "http://$CALLEE_APP:80/echo"
curl -vk "https://$CALLEE_FQDN/echo"
nc -vz "$CALLEE_APP" 9090
```

### 8.5 Test execution

Use the caller's public endpoint as the load-generator entry point. Each inbound request causes the caller to make exactly one downstream call to the callee using the selected mode.

Set once:

```bash
export CALLER_BASE="https://$CALLER_FQDN/invoke"
```

#### Scenario 1: Low load, internal name vs FQDN

```bash
echo "=== Low load: internal HTTP ==="
hey -n 50 -c 5 "$CALLER_BASE?mode=internal-http"

echo "=== Low load: FQDN HTTPS ==="
hey -n 50 -c 5 "$CALLER_BASE?mode=fqdn-https"
```

#### Scenario 2: Moderate load (~100 req/s), internal name vs FQDN

```bash
echo "=== Moderate load: internal HTTP ==="
hey -z 60s -c 20 -q 5 "$CALLER_BASE?mode=internal-http"

echo "=== Moderate load: FQDN HTTPS ==="
hey -z 60s -c 20 -q 5 "$CALLER_BASE?mode=fqdn-https"
```

#### Scenario 3: High load (~500 req/s), internal name vs FQDN

```bash
echo "=== High load: internal HTTP ==="
hey -z 60s -c 50 -q 10 "$CALLER_BASE?mode=internal-http"

echo "=== High load: FQDN HTTPS ==="
hey -z 60s -c 50 -q 10 "$CALLER_BASE?mode=fqdn-https"
```

#### Scenario 4: TCP vs HTTP comparison

```bash
echo "=== Functional TCP probe through internal name ==="
for i in $(seq 1 20); do
  curl --silent "$CALLER_BASE?mode=internal-tcp" | jq .
  sleep 1
done

echo "=== Low HTTP probe through internal name ==="
for i in $(seq 1 20); do
  curl --silent "$CALLER_BASE?mode=internal-http" | jq .
  sleep 1
done
```

!!! note "TCP scenario scope"
    The primary issue in GitHub #1315 is HTTP over internal name vs FQDN. The TCP step is an extension to check whether non-HTTP traffic shows the same failure pattern. If internal TCP connectivity to the extra container port is unsupported or behaves differently in your environment, record that as **Not Proven** rather than forcing a conclusion.

### 8.6 Data collection

```bash
az containerapp logs show \
  --resource-group "$RG" \
  --name "$CALLER_APP" \
  --follow false

az containerapp logs show \
  --resource-group "$RG" \
  --name "$CALLEE_APP" \
  --follow false

CALLER_ID=$(az containerapp show \
  --resource-group "$RG" \
  --name "$CALLER_APP" \
  --query id --output tsv)

CALLEE_ID=$(az containerapp show \
  --resource-group "$RG" \
  --name "$CALLEE_APP" \
  --query id --output tsv)

az monitor metrics list \
  --resource "$CALLER_ID" \
  --metric "Requests" "ResponseTime" "Replicas" \
  --interval PT1M \
  --aggregation Average Maximum Total \
  --output table

az monitor metrics list \
  --resource "$CALLEE_ID" \
  --metric "Requests" "ResponseTime" "Replicas" \
  --interval PT1M \
  --aggregation Average Maximum Total \
  --output table

az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(4h) | where ContainerAppName_s == '$CALLER_APP' | project TimeGenerated, RevisionName_s, Log_s | order by TimeGenerated desc" \
  --output table

az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(4h) | where ContainerAppName_s == '$CALLEE_APP' | project TimeGenerated, RevisionName_s, Log_s | order by TimeGenerated desc" \
  --output table
```

Capture a result table with at least these columns for every scenario:

| scenario | mode | offered_load | total_requests | success_count | failure_count | failure_rate_pct | p50_ms | p95_ms | p99_ms | dominant_error |
|----------|------|--------------|----------------|---------------|---------------|------------------|--------|--------|--------|----------------|

### 8.7 Cleanup

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- **Low load:** both paths should usually work, with no or minimal failures.
- **Moderate load:** internal-name HTTP should begin showing intermittent failures such as `Connection refused`, while FQDN HTTPS remains substantially more stable.
- **High load:** the gap between internal-name HTTP and FQDN HTTPS should widen in failure rate and tail latency.
- **Logs:** caller logs should show a clear error-type split by mode, with internal-name failures clustering around socket/connect exceptions.
- **Protocol comparison:** HTTP is expected to show the clearest reproduction. TCP may show different behavior or may remain inconclusive.
- **Support relevance:** if the failure reproduces only on the internal-name path and not on the FQDN path at equal load, the routing-path difference becomes the primary support narrative.

## 10. Results

### Pre-flight validation

- [Measured] Both `/healthz` endpoints returned HTTP 200.
- [Measured] `internal-http` single request succeeded with HTTP 200 in 20.11 ms.
- [Measured] `fqdn-https` single request succeeded with HTTP 200 in 22.99 ms.
- [Measured] `internal-tcp` single request failed with `TimeoutError` after 5007.52 ms, showing that the internal name did not route raw TCP to the non-ingress port.

### Summary results

| Scenario | Mode | Offered Load | Total Requests | Success | Failures | Failure Rate | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Dominant Error |
|----------|------|--------------|----------------|---------|----------|--------------|----------|----------|----------|----------|----------------|
| S1: Low | internal-http | 50 reqs, 5c | 50 | 50 | 0 | 0% | 207.9 | 173.1 | 503.6 | — | none |
| S1: Low | fqdn-https | 50 reqs, 5c | 50 | 50 | 0 | 0% | 212.6 | 175.7 | 552.9 | — | none |
| S2: Moderate | internal-http | 60s, 20c, 5q | 5,690 | 5,690 | 0 | 0% | 208.6 | 206.1 | 248.5 | 280.1 | none |
| S2: Moderate | fqdn-https | 60s, 20c, 5q | 5,948 | 5,948 | 0 | 0% | 189.0 | 184.6 | 236.3 | 257.7 | none |
| S3: High | internal-http | 60s, 50c, 10q | 16,092 | 16,092 | 0 | 0% | 186.4 | 169.2 | 263.0 | 299.1 | none |
| S3: High | fqdn-https | 60s, 50c, 10q | 10,790 | 10,790 | 0 | 0% | 278.5 | 175.1 | 534.6 | 574.0 | none |
| S4: TCP | internal-tcp | 20 probes | 20 | 0 | 20 | 100% | 5,007.5 | — | — | — | TimeoutError |
| S4: HTTP | internal-http | 20 probes | 20 | 20 | 0 | 0% | — | — | — | — | none |

### Scenario detail

- [Measured] Scenario 1 low load: both paths completed 50 of 50 requests with 0 failures. Internal HTTP averaged 207.9 ms and FQDN HTTPS averaged 212.6 ms.
- [Measured] Scenario 2 moderate load: internal HTTP completed 5,690 of 5,690 requests at 94.46 req/s with p99 280.1 ms. FQDN HTTPS completed 5,948 of 5,948 requests at 98.79 req/s with p99 257.7 ms.
- [Measured] Scenario 3 high load: internal HTTP completed 16,092 of 16,092 requests at 267.24 req/s with average 186.4 ms and p99 299.1 ms. FQDN HTTPS completed 10,790 of 10,790 requests at 178.26 req/s with average 278.5 ms and p99 574.0 ms.
- [Measured] Scenario 3 FQDN HTTPS showed a bimodal latency distribution: 6,924 requests were under 202 ms and 3,245 requests fell between 439 ms and 558 ms.
- [Measured] Scenario 4 TCP vs HTTP comparison: internal TCP failed 20 of 20 probes with `TimeoutError ("timed out")`, while internal HTTP succeeded 20 of 20 probes.

### Platform signals

- [Measured] Azure Metrics showed the callee scaling from 1 to 3 replicas at 14:25 UTC and the caller scaling from 1 to 3 replicas at 14:26 UTC.
- [Measured] Both apps reached the configured maximum of 3 replicas during Scenarios 2 and 3.
- [Observed] System logs included `SuccessfulRescale` for `callee-app` at 14:25 and `caller-app` at 14:26, plus `RevisionReady` for `caller-app--p72r2pg` at 14:24.
- [Observed] No error events, `Connection refused`, or container crashes were recorded in the system-log highlights during the measured runs.

## 11. Interpretation

- [Not Proven] The main hypothesis was not confirmed. Internal-name HTTP did not show a higher failure rate than FQDN HTTPS under low, moderate, or high load; both paths stayed at 0% failure in all HTTP scenarios.
- [Measured] Under high load, internal-name HTTP was materially faster than FQDN HTTPS, with lower average latency (186.4 ms vs 278.5 ms), lower p95 (263.0 ms vs 534.6 ms), and lower p99 (299.1 ms vs 574.0 ms).
- [Correlated] The higher tail latency appeared on the FQDN HTTPS path, not on the internal-name HTTP path, even though both apps were scaling at the same time and both reached 3 replicas.
- [Inferred] The bimodal FQDN HTTPS latency distribution suggests extra overhead on the HTTPS ingress path, such as TLS handshake cost and/or queueing in the external ingress Envoy layer, because the slower cluster was concentrated in the 439-558 ms range while internal HTTP remained tighter.
- [Measured] Internal-name routing in this environment handled HTTP reliably but did not route raw TCP to the non-ingress port; the protocol split was absolute in Scenario 4 with 20 of 20 HTTP successes and 20 of 20 TCP timeouts.
- [Observed] The absence of `Connection refused`, crash signals, or error events in system logs indicates that the GitHub issue's reported failure mode did not surface in this run.
- [Unknown] This result does not establish why GitHub issue #1315 reproduced elsewhere. Possible missing conditions include VNet involvement, mTLS, platform-stamp differences, or another environment-specific trigger that was not present in this Consumption test.

## 12. What this proves

- [Measured] In this Consumption environment test, internal-name HTTP routing was stable across all executed HTTP load levels, with 0 failures across 21,832 measured HTTP requests.
- [Measured] FQDN HTTPS routing was also stable across all executed HTTP load levels, with 0 failures across 16,788 measured HTTP requests.
- [Not Proven] This experiment does not support the assumption that internal app-name routing is inherently less stable than FQDN routing under load.
- [Measured] At the highest tested load, internal-name HTTP outperformed FQDN HTTPS on both throughput and tail latency.
- [Measured] Internal-name routing did not forward raw TCP traffic to the tested non-ingress port; all 20 sequential TCP probes timed out.
- [Inferred] For this specific setup, internal-name HTTP avoided some latency cost present on the FQDN HTTPS path at scale.

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- The exact internal implementation details of every Envoy hop in every Container Apps stamp.
- Whether the issue is identical across all regions, workload profiles, or environment types.
- That every internal-name failure is a Microsoft platform defect rather than an app-specific port or timeout problem.
- That TCP and HTTP necessarily share the same failure mode.
- That future ingress-only routing changes have already rolled out everywhere.

## 14. Support takeaway

If a customer reports that `http://<app-name>:80` intermittently fails while `https://<app-fqdn>` works:

1. Reproduce both addressing methods under the same load, not just with one-off curls.
2. Do not assume internal-name HTTP is the weaker path; in this run it was equally reliable and faster than FQDN HTTPS at high load.
3. Separate HTTP findings from raw TCP findings. Internal-name HTTP worked reliably here, while raw TCP to the non-ingress port timed out 100% of the time.
4. Collect caller latency distributions, replica-scale metrics, and system-log events before recommending FQDN as a mitigation.
5. If the customer cites GitHub issue #1315, treat it as a workload- or environment-specific pattern that still requires proof in the current stamp and configuration.
6. Escalate only after showing a measured path-specific difference, and include whether VNet, mTLS, or other environmental factors could explain why the older failure pattern was not reproduced.

## 15. Reproduction notes

- Keep min replicas at `1` initially so the first run is not dominated by scale-to-zero behavior.
- Run internal-name and FQDN scenarios close together in time to avoid platform drift.
- If `hey` is not available locally, use any rate-controlled equivalent and record its exact command line.
- Preserve raw caller logs; the wrapped JSON error body is the most useful artifact for support.
- If the internal TCP test cannot connect at all, do not reinterpret that as proof of the original HTTP issue; treat it as a separate observation.
- If desired, add a second pass using `http://$CALLEE_APP:8080/echo` as a control to test whether the platform service port (`80`) vs container port (`8080`) changes the outcome.

## 16. Related guide / official docs

- [GitHub issue #1315: Connection refused when using internal container-app name vs FQDN](https://github.com/microsoft/azure-container-apps/issues/1315)
- [Microsoft Learn: Networking in Azure Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Microsoft Learn: Ingress in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Microsoft Learn: Manage revisions in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Microsoft Learn: Container Apps logs and monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
