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

# Scaling Rule Conflicts: HTTP, CPU, and Queue Scalers

!!! info "Status: Draft - Awaiting Execution"
    Experiment designed but not yet executed. This draft targets real Azure Container Apps scaling issue patterns reported in GitHub issues [#468](https://github.com/microsoft/azure-container-apps/issues/468), [#536](https://github.com/microsoft/azure-container-apps/issues/536), and [#972](https://github.com/microsoft/azure-container-apps/issues/972): mixed scaling rules behaving unexpectedly, scale-out being driven by one signal while another appears ignored, and scale-in failing when connections or metrics remain artificially active.

## 1. Question

How do multiple Azure Container Apps scaling rules interact in practice? Specifically:

- what happens when **HTTP scaling** and **CPU scaling** are configured together
- what happens when **HTTP scaling** and a **queue-driven KEDA scaler** are configured together
- why does **scale-in sometimes not happen** even after user traffic or queue backlog appears to be gone

## 2. Why this matters

This is a frequent support pattern because customers often assume multiple scale rules combine intuitively: HTTP handles request bursts, CPU handles heavy work, and queue scalers handle background load. In reality, the observed behavior is often surprising:

- HTTP traffic appears to stop scaling once CPU scaling is added
- the app scales out correctly but stays over-provisioned long after load stops
- tuning `cooldownPeriod` appears ineffective because the scaler never actually sees an inactive state
- `activation*` thresholds are misunderstood, causing scalers to remain active or never activate at all

Support engineers need evidence to answer three recurring questions:

1. whether HTTP ingress scaling and KEDA-driven custom scaling are handled by the same control path
2. whether multiple rules are truly additive or whether one rule dominates practical behavior
3. whether failed scale-in is a platform cooldown problem, an active-connection problem, or a metric-threshold problem

## 3. Customer symptom

Typical ticket phrasing:

- "HTTP autoscaling stopped working after I added a CPU rule."
- "The app scales out, but never scales back in."
- "`cooldownPeriod` is set, but replicas remain high forever."
- "Queue length is zero, yet the app still does not scale down."
- "Everything looks idle except for a few long-lived HTTP/2 clients."

## 4. Hypothesis

1. **HTTP scaling** uses a different internal mechanism than KEDA external/custom scalers, even though both surface as scale rules in Container Apps.
2. When **HTTP** and **CPU** rules coexist, practical control will often be dominated by the non-HTTP rule once replicas are already active, making HTTP behavior appear ignored.
3. When **HTTP** and **queue-based KEDA** rules coexist, scale-out may be driven by whichever signal reaches its threshold first, but scale-in will wait until **all active signals** fall below deactivation conditions.
4. **HTTP/2 keep-alive or long-lived streams** can block scale-in even after meaningful user traffic stops because the ingress layer still considers connections active.
5. Lowering **`cooldownPeriod`** alone will not help if metrics never cross back below the effective activation/deactivation boundary.
6. Misconfigured **`activationValue` / `activationMessageCount` / threshold values** frequently create false scale-in expectations.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 custom container |
| OS | Linux |
| App shape | Single HTTP app with normal, CPU-heavy, long-lived connection, and queue helper endpoints |
| Queue service | Azure Service Bus queue |
| Ingress | External, target port `8080`, HTTP/2 enabled for dedicated scenarios |
| Scale rules under test | HTTP, CPU, Azure Service Bus queue |
| Logging | Log Analytics + Container Apps system/console logs |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config / behavior comparison across scaling-rule combinations

**Controlled:**

- same Container Apps environment and region
- same application image and revision baseline
- same CPU/memory sizing unless intentionally changed for threshold sensitivity
- same request generator cadence per scenario
- same queue producer rate per scenario
- same observation window for scale-out and scale-in
- same Log Analytics workspace and KQL queries

**Independent variables:**

- scaling rule set: HTTP only, CPU only, HTTP+CPU, HTTP+Service Bus
- HTTP concurrency threshold
- CPU utilization threshold
- Service Bus message count threshold
- `cooldownPeriod` and `pollingInterval`
- `activationMessageCount` on queue rule
- client connection mode: short-lived HTTP/1.1 vs persistent HTTP/2

**Observed:**

- replica count over time
- revision/replica activation and termination timestamps
- HTTP status, latency, and concurrency seen by the test client
- CPU usage during `/cpu` endpoint execution
- Service Bus queue depth and dequeue rate
- KEDA/system log events related to scaler activation/deactivation
- whether scale-in occurs, and how long after load removal

## 7. Instrumentation

Planned evidence sources:

- **ContainerAppSystemLogs_CL** for scaling decisions, replica lifecycle, and scaler-related warnings
- **ContainerAppConsoleLogs_CL** for app-level markers (`REQUEST_START`, `CPU_WORK_START`, `STREAM_OPEN`, `STREAM_CLOSE`, `QUEUE_SEND`)
- **Azure CLI** for current scale rule configuration, replica inventory, and revision state
- **Azure Monitor metrics** for CPU and replica count
- **Service Bus metrics** and queue length inspection for backlog-driven scenarios
- **Synthetic load scripts** for HTTP/1.1, HTTP/2, CPU-heavy requests, and queue message generation

Recommended application log markers:

- `REQUEST_NORMAL`
- `REQUEST_CPU_HEAVY`
- `STREAM_OPEN`
- `STREAM_CLOSE`
- `QUEUE_ENQUEUE`
- `QUEUE_DEQUEUE`

### Log Analytics queries

```kusto
// Scaling and replica lifecycle timeline
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-scale-rule-conflicts"
| project TimeGenerated, RevisionName_s, ReplicaName_s, Reason_s, Log_s
| order by TimeGenerated asc
```

```kusto
// Application-side markers from the test app
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-scale-rule-conflicts"
| project TimeGenerated, RevisionName_s, Log_s
| where Log_s has_any ("REQUEST_", "CPU_WORK_", "STREAM_", "QUEUE_")
| order by TimeGenerated asc
```

```kusto
// Suspected scaler / cooldown related entries
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "ca-scale-rule-conflicts"
| where Log_s has_any ("scale", "KEDA", "cooldown", "HTTP", "cpu", "servicebus")
| project TimeGenerated, Reason_s, Log_s, ReplicaName_s
| order by TimeGenerated asc
```

## 8. Procedure

### 8.1 Infrastructure setup

```bash
# Resource group
az group create \
  --name rg-aca-scale-rule-conflicts-lab \
  --location koreacentral

# Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --workspace-name law-aca-scale-rule-conflicts \
  --location koreacentral

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --workspace-name law-aca-scale-rule-conflicts \
  --query customerId -o tsv)

LAW_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --workspace-name law-aca-scale-rule-conflicts \
  --query primarySharedKey -o tsv)

# Container Apps environment
az containerapp env create \
  --name cae-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --location koreacentral \
  --logs-workspace-id "$LAW_ID" \
  --logs-workspace-key "$LAW_KEY"

# Azure Container Registry
az acr create \
  --name acrscaleruleconflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --sku Basic \
  --admin-enabled true \
  --location koreacentral

# Service Bus namespace and queue for KEDA-backed queue scenarios
az servicebus namespace create \
  --name sbscaleruleconflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --location koreacentral \
  --sku Standard

az servicebus queue create \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --namespace-name sbscaleruleconflicts \
  --name work-items

SB_CONNECTION_STRING=$(az servicebus namespace authorization-rule keys list \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --namespace-name sbscaleruleconflicts \
  --name RootManageSharedAccessKey \
  --query primaryConnectionString -o tsv)
```

### 8.2 Test application

The app must expose four behaviors in a single revision so that only scaling rules change between scenarios:

- `/` — lightweight normal endpoint
- `/cpu?seconds=30` — CPU-heavy endpoint that spins for a controllable duration
- `/stream?seconds=300` — long-lived streaming endpoint for persistent connection tests
- `/enqueue?count=100` — helper endpoint that sends messages to Service Bus for queue scenarios

#### app.py

```python
import json
import math
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request
from azure.servicebus import ServiceBusClient, ServiceBusMessage

app = Flask(__name__)

SB_CONNECTION_STRING = os.environ.get("SERVICEBUS_CONNECTION_STRING")
SB_QUEUE_NAME = os.environ.get("SERVICEBUS_QUEUE_NAME", "work-items")


def log_event(event, **kwargs):
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    print(json.dumps(payload), flush=True)


@app.route("/")
def index():
    log_event("REQUEST_NORMAL")
    return jsonify({"status": "ok", "mode": "normal"})


@app.route("/cpu")
def cpu_heavy():
    seconds = float(request.args.get("seconds", "30"))
    stop_at = time.monotonic() + seconds
    iterations = 0
    log_event("CPU_WORK_START", seconds=seconds)
    value = 0.0001
    while time.monotonic() < stop_at:
        value = math.sqrt(value + 123.456789)
        iterations += 1
    log_event("CPU_WORK_END", seconds=seconds, iterations=iterations)
    return jsonify({"status": "ok", "mode": "cpu", "seconds": seconds, "iterations": iterations})


@app.route("/stream")
def stream():
    seconds = int(request.args.get("seconds", "300"))
    interval = int(request.args.get("interval", "5"))
    log_event("STREAM_OPEN", seconds=seconds, interval=interval)

    def generate():
        started = time.monotonic()
        try:
            while time.monotonic() - started < seconds:
                yield f"data: heartbeat {datetime.now(timezone.utc).isoformat()}\\n\\n"
                time.sleep(interval)
        finally:
            log_event("STREAM_CLOSE", seconds=seconds)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/enqueue", methods=["POST"])
def enqueue():
    count = int(request.args.get("count", "100"))
    if not SB_CONNECTION_STRING:
        return jsonify({"error": "SERVICEBUS_CONNECTION_STRING not configured"}), 500

    with ServiceBusClient.from_connection_string(SB_CONNECTION_STRING) as client:
        with client.get_queue_sender(SB_QUEUE_NAME) as sender:
            for i in range(count):
                sender.send_messages(ServiceBusMessage(f"msg-{i}"))

    log_event("QUEUE_ENQUEUE", count=count)
    return jsonify({"status": "ok", "enqueued": count})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

#### worker.py

```python
import json
import os
import time
from datetime import datetime, timezone

from azure.servicebus import ServiceBusClient

SB_CONNECTION_STRING = os.environ["SERVICEBUS_CONNECTION_STRING"]
SB_QUEUE_NAME = os.environ.get("SERVICEBUS_QUEUE_NAME", "work-items")


def log_event(event, **kwargs):
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    print(json.dumps(payload), flush=True)


with ServiceBusClient.from_connection_string(SB_CONNECTION_STRING) as client:
    receiver = client.get_queue_receiver(queue_name=SB_QUEUE_NAME, max_wait_time=5)
    with receiver:
        while True:
            messages = receiver.receive_messages(max_message_count=10, max_wait_time=5)
            if not messages:
                log_event("QUEUE_IDLE")
                time.sleep(2)
                continue

            for message in messages:
                log_event("QUEUE_DEQUEUE", message_id=str(message.message_id))
                time.sleep(2)
                receiver.complete_message(message)
```

#### requirements.txt

```text
flask==3.1.0
gunicorn==23.0.0
azure-servicebus==7.14.2
```

#### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py worker.py ./
EXPOSE 8080
CMD ["sh", "-c", "python worker.py & gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 0 app:app"]
```

### 8.3 Build and push image

```bash
az acr build \
  --registry acrscaleruleconflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --image scale-rule-conflicts:v1 \
  --file Dockerfile .
```

### 8.4 Baseline deployment

```bash
ACR_USER=$(az acr credential show \
  --name acrscaleruleconflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --query username -o tsv)

ACR_PASS=$(az acr credential show \
  --name acrscaleruleconflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --query "passwords[0].value" -o tsv)

az containerapp create \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --environment cae-scale-rule-conflicts \
  --image acrscaleruleconflicts.azurecr.io/scale-rule-conflicts:v1 \
  --registry-server acrscaleruleconflicts.azurecr.io \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 10 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars SERVICEBUS_CONNECTION_STRING="$SB_CONNECTION_STRING" SERVICEBUS_QUEUE_NAME=work-items \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 10

APP_URL=$(az containerapp show \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --query properties.configuration.ingress.fqdn -o tsv)
```

### 8.5 Scenario matrix

| Scenario | Scale rules | Primary load source | Expected discriminator |
|---|---|---|---|
| 1. HTTP only | HTTP concurrency only | `GET /` burst | Baseline for normal HTTP scale-out/scale-in |
| 2. CPU only | CPU rule only | `GET /cpu` | Baseline for KEDA-style resource scaling |
| 3. HTTP + CPU | Both HTTP and CPU | mixed `/` + `/cpu` | Determine whether HTTP scaling appears subordinated or ignored |
| 4. HTTP + Service Bus | HTTP + Service Bus queue | `/` burst + queue backlog | Determine whether both signals can keep replicas active |
| 5. HTTP/2 scale-in | HTTP rule only or HTTP + CPU | long-lived `/stream` clients | Determine whether active connections prevent scale-in |

### 8.6 Scale rule update commands per scenario

#### Scenario 1: HTTP only

```bash
az containerapp update \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --min-replicas 0 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 10
```

#### Scenario 2: CPU only

```bash
az containerapp update \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --scale-rule-name cpu-rule \
  --scale-rule-type cpu \
  --scale-rule-metadata type=Utilization value=60
```

#### Scenario 3: HTTP + CPU

Use YAML because multiple scale rules are easier to express explicitly.

```yaml
properties:
  template:
    scale:
      minReplicas: 0
      maxReplicas: 10
      rules:
        - name: http-rule
          http:
            metadata:
              concurrentRequests: "10"
        - name: cpu-rule
          custom:
            type: cpu
            metadata:
              type: Utilization
              value: "60"
```

```bash
az containerapp show \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --output yaml > scenario-http-cpu.yaml

# Replace the scale block with the YAML above, then apply:
az containerapp update \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --yaml scenario-http-cpu.yaml
```

#### Scenario 4: HTTP + Service Bus queue

```yaml
properties:
  configuration:
    secrets:
      - name: sb-connection
        value: <service-bus-connection-string>
  template:
    scale:
      minReplicas: 0
      maxReplicas: 10
      rules:
        - name: http-rule
          http:
            metadata:
              concurrentRequests: "10"
        - name: sb-rule
          custom:
            type: azure-servicebus
            auth:
              - secretRef: sb-connection
                triggerParameter: connection
            metadata:
              namespace: sbscaleruleconflicts
              queueName: work-items
              messageCount: "5"
              activationMessageCount: "0"
```

```bash
az containerapp show \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --output yaml > scenario-http-sb.yaml

# Replace the scale block and secret value, then apply:
az containerapp update \
  --name ca-scale-rule-conflicts \
  --resource-group rg-aca-scale-rule-conflicts-lab \
  --yaml scenario-http-sb.yaml
```

#### Scenario 5: cooldown and activation retest

Repeat Scenarios 3 and 4 with these controlled variations:

- reduce `cooldownPeriod` to `30`
- increase `cooldownPeriod` to `300`
- change queue `activationMessageCount` from `0` to `5`
- change HTTP load from short-lived requests to long-lived `/stream` clients

### 8.7 Load scripts

#### Short-lived HTTP burst

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
TOTAL="${2:-200}"
CONCURRENCY="${3:-40}"

seq "$TOTAL" | xargs -P "$CONCURRENCY" -I{} \
  curl -skS "https://$URL/" -o /dev/null -w '%{http_code} %{time_total}\n'
```

#### CPU-heavy traffic

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
REQUESTS="${2:-20}"
SECONDS_PER_REQUEST="${3:-30}"
PARALLEL="${4:-10}"

seq "$REQUESTS" | xargs -P "$PARALLEL" -I{} \
  curl -skS "https://$URL/cpu?seconds=$SECONDS_PER_REQUEST" -o /dev/null -w '%{http_code} %{time_total}\n'
```

#### Queue backlog creation

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
COUNT="${2:-200}"

curl -skS -X POST "https://$URL/enqueue?count=$COUNT"
```

#### Long-lived HTTP/2 clients

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="$1"
CLIENTS="${2:-5}"
SECONDS="${3:-300}"

for n in $(seq 1 "$CLIENTS"); do
  curl --http2 -skN "https://$URL/stream?seconds=$SECONDS&interval=5" \
    > "stream-client-$n.log" 2>&1 &
done

wait
```

### 8.8 Per-scenario execution steps

For each scenario:

1. Apply the intended scale-rule configuration.
2. Confirm the active revision and scale rule block with `az containerapp show`.
3. Wait for the app to scale to baseline (`0` or `1` replicas as configured).
4. Start the relevant load script.
5. Record replica count every 15 seconds with `az containerapp replica list`.
6. Stop the load source and continue observing for at least 15 minutes.
7. Query system and console logs immediately after the observation window.
8. Repeat at least three independent runs per scenario.

## 9. Expected signal

- **Scenario 1: HTTP only** should scale out during request bursts and scale in after requests stop and active connections disappear.
- **Scenario 2: CPU only** should scale out only when `/cpu` traffic drives sustained CPU above threshold; scale-in should follow after CPU drops and cooldown expires.
- **Scenario 3: HTTP + CPU** should reveal whether CPU activity keeps replicas active even after HTTP burst traffic is gone, making HTTP scale-in appear broken.
- **Scenario 4: HTTP + Service Bus** should show whether queue backlog or lingering worker activity keeps replicas alive after front-end traffic stops.
- **Scenario 5: HTTP/2** should show that long-lived connections delay or block scale-in even with low request rate.
- Retesting with altered `cooldownPeriod` should show little or no effect when the scaler remains logically active.

## 10. Results

Pending execution.

Capture the following tables during execution.

### 10.1 Replica timeline summary

| Scenario | Run | First scale-out time | Peak replicas | Load stop time | Scale-in complete time | Scale-in blocked? |
|---|---|---|---|---|---|---|
| HTTP only | 1 | | | | | |
| CPU only | 1 | | | | | |
| HTTP + CPU | 1 | | | | | |
| HTTP + Service Bus | 1 | | | | | |
| HTTP/2 keep-alive | 1 | | | | | |

### 10.2 Dominant-signal observations

| Scenario | HTTP traffic present | CPU above threshold | Queue backlog present | Expected inactive point | Actual inactive point |
|---|---|---|---|---|---|
| HTTP + CPU | | | n/a | | |
| HTTP + Service Bus | | n/a | | | |
| HTTP/2 keep-alive | | optional | n/a | | |

### 10.3 Representative log excerpts

- system log excerpt showing scale-out trigger
- system log excerpt showing failed or delayed scale-in
- console log excerpt showing `STREAM_OPEN` without `STREAM_CLOSE`
- queue worker logs showing `QUEUE_IDLE` despite lingering replicas

## 11. Interpretation

Pending execution. Interpret results using explicit evidence tags.

Planned interpretation questions:

1. **Observed / Measured**: Did HTTP-only and CPU-only baselines behave normally on their own?
2. **Observed / Inferred**: In mixed-rule scenarios, did one metric remain active and therefore prevent overall scale-in?
3. **Observed / Strongly Suggested**: Did HTTP/2 streams correlate with blocked scale-in despite near-zero request volume?
4. **Not Proven / Unknown**: If HTTP scaling appears ignored, is the cause controller precedence, metric sampling cadence, or threshold design?

## 12. What this proves

After execution, this experiment should be able to prove only the following kinds of claims:

- whether the tested rule combinations in this environment scaled out as expected
- whether scale-in required all active signals to become inactive
- whether long-lived HTTP/2 connections correlated with delayed scale-in
- whether `cooldownPeriod` changes alone changed behavior when metrics remained active

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- the exact internal Azure control-plane implementation behind HTTP scaling
- that all Container Apps regions or environments behave identically
- that Event Hub scaling bugs are identical to Service Bus scaling behavior
- that every apparent conflict is a platform bug rather than a threshold-design issue

Issue [#972](https://github.com/microsoft/azure-container-apps/issues/972) is included as motivation for queue-scaler scale-down anomalies, but this design uses **Service Bus** for easier controlled reproduction. Any similarity to Event Hub behavior would be **correlated**, not automatically equivalent.

## 14. Support takeaway

For cases involving unexpected Container Apps scaling behavior, support engineers should check:

1. whether multiple scale signals are configured and which one is still active
2. whether the customer expects `cooldownPeriod` to override an active metric
3. whether HTTP/2, SSE, gRPC, or other long-lived connections are keeping ingress activity alive
4. whether queue scaler `activation*` values and thresholds are aligned with actual idle conditions
5. whether the customer has baseline evidence from single-rule testing before combining rules

Practical triage order:

- reproduce with **HTTP only**
- reproduce with **CPU only** or **queue only**
- combine rules only after each single-rule baseline is understood
- inspect active connections and scaler thresholds before escalating as a platform defect

## 15. Reproduction notes

- Keep **revision mode fixed** during all runs to avoid mixing revision-transition behavior with scaling behavior.
- Use **the same image and same environment** for every scenario.
- Wait long enough after stopping load; scale-in investigations often fail because observation stops too early.
- For HTTP/2 tests, prefer clients that keep connections open intentionally; short curl bursts may not reproduce the issue.
- Record exact rule configuration for every run because small threshold differences can completely change conclusions.
- If scale rules must be edited through YAML, archive the exact applied YAML alongside captured logs.

## 16. Related guide / official docs

- [Azure Container Apps scaling](https://learn.microsoft.com/azure/container-apps/scale-app)
- [Azure Container Apps KEDA scaling concepts](https://learn.microsoft.com/azure/container-apps/scale-app#scale-rules)
- [Azure Container Apps manage revisions](https://learn.microsoft.com/azure/container-apps/revisions)
- [Azure Service Bus scaler in KEDA](https://keda.sh/docs/latest/scalers/azure-service-bus/)
- [GitHub issue #468](https://github.com/microsoft/azure-container-apps/issues/468)
- [GitHub issue #536](https://github.com/microsoft/azure-container-apps/issues/536)
- [GitHub issue #972](https://github.com/microsoft/azure-container-apps/issues/972)
- [Revision Update Downtime During Container Apps Deployments](../revision-update-downtime/overview.md)
- [Scale-to-Zero First Request 503/Timeout](../scale-to-zero-502/overview.md)
