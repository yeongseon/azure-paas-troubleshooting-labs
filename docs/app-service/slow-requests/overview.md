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

# Slow Requests Under Pressure

!!! info "Status: Planned"

## 1. Question

When an App Service worker is under memory or CPU pressure, how do slow requests manifest in telemetry, and can we distinguish frontend (ARR) timeout from worker-side processing delay from downstream dependency latency?

## 2. Why this matters

"Slow requests" is one of the most common support symptoms, but the root cause can originate at three different layers: the platform frontend/load balancer (ARR), the application worker, or a downstream dependency. Each layer produces different diagnostic signals, and misidentifying the layer wastes investigation time.

Support engineers need a reliable method to determine which layer is responsible based on available telemetry.

## 3. Customer symptom

"Some requests take 30+ seconds and then timeout" or "We see 504 errors but our app should respond in under a second."

## 4. Hypothesis

Under controlled delay injection, telemetry will show distinguishable patterns for each bottleneck layer: worker-side delay will inflate request duration without matching dependency duration, dependency-side delay will inflate dependency spans with correlated request delay, and frontend timeout behavior will produce timeout signatures that differ from normal long-running worker responses.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 and P1v3 |
| Region | Korea Central |
| Runtime | Node.js 20 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Delay injection point (worker, dependency, thread pool)
- Delay duration
- Concurrent request load

**Observed:**

- Application Insights request duration vs. dependency duration
- ARR timeout logs (230-second default)
- HTTP status codes (504 vs. 500 vs. 200 slow)
- Time-to-first-byte vs. total response time

**Independent run definition**: Fresh app restart, fixed load profile, fixed delay scenario, and one complete capture window per scenario.

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: Exclude the first 2 minutes after restart for each run before collecting comparison data.

**Primary metric and meaningful-effect threshold**: p95 end-to-end request duration; meaningful effect is >=20% relative shift between scenarios.

**Comparison method**: Bootstrap confidence interval on per-run p95 deltas, with directional consistency check across runs.

## 7. Instrumentation

- Application Insights requests, dependencies, exceptions, and operation correlation fields
- Azure Monitor metrics for CPU percentage, memory working set, and HTTP queue indicators
- App Service diagnostics and web server logs for timeout and upstream status signals
- Synthetic load generator (k6) with scenario labels and synchronized timestamps
- Application-level structured logs for injected delay markers

## 8. Procedure

### 8.1 Infrastructure setup

Create the baseline infrastructure in `koreacentral` on the `B1` plan.

```bash
RG="rg-slow-requests-lab"
LOCATION="koreacentral"
PLAN_NAME="plan-slow-requests-b1"
APP_NAME="app-slow-requests-$RANDOM"
WORKSPACE_NAME="log-slow-requests"
APPINSIGHTS_NAME="appi-slow-requests"

az group create --name "$RG" --location "$LOCATION"

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --sku B1 \
  --is-linux

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$WORKSPACE_NAME" \
  --location "$LOCATION"

az monitor app-insights component create \
  --app "$APPINSIGHTS_NAME" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --workspace "$WORKSPACE_NAME" \
  --application-type web

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --name "$APP_NAME" \
  --runtime "NODE|20-lts"
```

After the baseline run set is complete, repeat the same procedure with a second plan using `--sku P1v3` and a separate app name so `B1` and `P1v3` datasets stay isolated.

### 8.2 Application code

Implement a Node.js 20 Express app with four endpoints.

```javascript
import express from "express";
import crypto from "node:crypto";

const app = express();
const port = process.env.PORT || 8080;

function logEvent(event, scenario, requestId, extra = {}) {
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      event,
      scenario,
      requestId,
      ...extra
    })
  );
}

function busyWait(ms) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    Math.sqrt(Math.random());
  }
}

app.get("/health", (req, res) => {
  res.status(200).send("ok");
});

app.get("/delay/worker", (req, res) => {
  const requestId = req.headers["x-ms-request-id"] || crypto.randomUUID();
  const ms = Number(req.query.ms || 5000);
  logEvent("entry", "worker", requestId, { ms });
  logEvent("delay-start", "worker", requestId, { ms });
  busyWait(ms);
  logEvent("delay-end", "worker", requestId, { ms });
  logEvent("response-send", "worker", requestId, { status: 200 });
  res.status(200).json({ scenario: "worker", delayMs: ms });
});

app.get("/delay/dependency", async (req, res) => {
  const requestId = req.headers["x-ms-request-id"] || crypto.randomUUID();
  const ms = Number(req.query.ms || 5000);
  logEvent("entry", "dependency", requestId, { ms });
  logEvent("delay-start", "dependency", requestId, { ms });
  await new Promise((resolve) => setTimeout(resolve, ms));
  logEvent("delay-end", "dependency", requestId, { ms });
  logEvent("response-send", "dependency", requestId, { status: 200 });
  res.status(200).json({ scenario: "dependency", delayMs: ms });
});

app.get("/delay/threadpool", async (req, res) => {
  const requestId = req.headers["x-ms-request-id"] || crypto.randomUUID();
  const ms = Number(req.query.ms || 5000);
  logEvent("entry", "threadpool", requestId, { ms });
  logEvent("delay-start", "threadpool", requestId, { ms });
  await new Promise((resolve) => setTimeout(resolve, ms));
  logEvent("delay-end", "threadpool", requestId, { ms });
  logEvent("response-send", "threadpool", requestId, { status: 200 });
  res.status(200).json({ scenario: "threadpool", delayMs: ms });
});

app.listen(port, () => {
  console.log(JSON.stringify({ ts: new Date().toISOString(), event: "startup", port }));
});
```

Use the following endpoint intent during testing:

- `/delay/worker?ms=5000`: CPU-bound busy loop.
- `/delay/dependency?ms=5000`: simulated downstream latency.
- `/delay/threadpool?ms=5000`: high-concurrency blocking simulation to pressure worker thread handling.
- `/health`: immediate baseline response.

### 8.3 Deploy

Deploy from the app source directory using `az webapp up`, then connect Application Insights and verify app settings.

```bash
az webapp up \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --plan "$PLAN_NAME" \
  --runtime "NODE|20-lts" \
  --location "$LOCATION"

APPINSIGHTS_CONNECTION_STRING=$(az monitor app-insights component show \
  --app "$APPINSIGHTS_NAME" \
  --resource-group "$RG" \
  --query connectionString \
  --output tsv)

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=$APPINSIGHTS_CONNECTION_STRING"

az webapp restart --resource-group "$RG" --name "$APP_NAME"
```

### 8.4 Test execution

For each scenario (`worker`, `dependency`, `threadpool`), execute 5 independent runs with the same load profile.

1. Warm the app for 2 minutes and exclude this period from comparison.
2. Run k6 with 10 concurrent virtual users for 3 minutes.
3. Keep scenario-specific endpoint and delay fixed during one run.
4. Cool down for 2 minutes between runs.
5. Repeat until 5 runs are complete per scenario and per SKU.

```javascript
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    constant_load: {
      executor: "constant-vus",
      vus: 10,
      duration: "3m"
    }
  }
};

const baseUrl = __ENV.BASE_URL;
const path = __ENV.SCENARIO_PATH;

export default function () {
  const response = http.get(`${baseUrl}${path}`);
  check(response, { "status is 200 or 504": (r) => r.status === 200 || r.status === 504 });
  sleep(1);
}
```

```bash
BASE_URL="https://$APP_NAME.azurewebsites.net"

k6 run --env BASE_URL="$BASE_URL" --env SCENARIO_PATH="/delay/worker?ms=5000" scripts/slow-requests.js
k6 run --env BASE_URL="$BASE_URL" --env SCENARIO_PATH="/delay/dependency?ms=5000" scripts/slow-requests.js
k6 run --env BASE_URL="$BASE_URL" --env SCENARIO_PATH="/delay/threadpool?ms=5000" scripts/slow-requests.js
```

ARR timeout boundary validation:

```bash
k6 run --env BASE_URL="$BASE_URL" --env SCENARIO_PATH="/delay/worker?ms=240000" scripts/slow-requests.js
```

Capture per-run `p95` from the k6 summary and store it with `{sku, scenario, run_number}` labels.

### 8.5 Data collection

Collect telemetry from Application Insights and App Service diagnostics for each run window.

```kusto
let runStart = datetime(<run-start-utc>);
let runEnd = datetime(<run-end-utc>);
requests
| where timestamp between (runStart .. runEnd)
| where url has "/delay/"
| extend scenario = case(
    url has "/delay/worker", "worker",
    url has "/delay/dependency", "dependency",
    url has "/delay/threadpool", "threadpool",
    "unknown")
| summarize p50=percentile(duration, 50), p95=percentile(duration, 95), p99=percentile(duration, 99), count() by scenario, resultCode
| order by scenario asc
```

```kusto
let runStart = datetime(<run-start-utc>);
let runEnd = datetime(<run-end-utc>);
dependencies
| where timestamp between (runStart .. runEnd)
| summarize depP50=percentile(duration, 50), depP95=percentile(duration, 95), depCount=count() by target, success
| order by depP95 desc
```

```kusto
let runStart = datetime(<run-start-utc>);
let runEnd = datetime(<run-end-utc>);
requests
| where timestamp between (runStart .. runEnd)
| where url has "/delay/"
| summarize total=count(), status200=countif(resultCode == "200"), status502=countif(resultCode == "502"), status504=countif(resultCode == "504") by bin(timestamp, 1m)
| order by timestamp asc
```

Correlate request-level duration with dependency duration and frontend timeout indicators to separate:

- Worker delay pattern (high request duration, low dependency duration).
- Dependency delay pattern (request and dependency durations increase together).
- Timeout boundary pattern (ARR-related timeout status behavior, including 504/502 transitions where present).

### 8.6 Cleanup

Delete all lab resources after exporting required logs and result tables.

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Worker-delay scenario shows increased request duration with minimal dependency-duration change.
- Dependency-delay scenario shows dependency spans tracking request slowdowns and preserved worker health metrics.
- Thread-exhaustion/front-end stress scenario increases timeout-like outcomes and queue-related latency patterns.
- Telemetry signatures remain directionally consistent across repeated runs for each injected scenario.

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

- Keep one injected delay source active at a time to avoid overlapping signals.
- Pin load profile and request mix across runs so layer-specific comparisons stay valid.
- Align all logs to UTC and retain a run identifier in each request for trace stitching.
- Restart the app between run sets when changing major delay scenarios.

## 16. Related guide / official docs

- [Microsoft Learn: Troubleshoot slow app performance](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-performance-degradation)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
