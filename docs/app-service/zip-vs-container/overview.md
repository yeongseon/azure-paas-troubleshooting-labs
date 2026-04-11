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

# Zip Deploy vs Custom Container Behavior

!!! info "Status: Planned"

## 1. Question

How do deployment method differences (zip deploy vs. custom container) affect startup time, file system behavior, and troubleshooting signal availability on App Service Linux?

## 2. Why this matters

Customers migrating between deployment methods sometimes encounter behavioral differences that are not documented. An app that works with zip deploy may behave differently in a custom container — different file system layout, different environment variable handling, different log locations. Support engineers handling "it worked before I switched to containers" tickets need to understand these differences.

## 3. Customer symptom

"My app works with zip deploy but fails with custom container" or "Startup takes much longer after switching to container deployment."

## 4. Hypothesis

For identical application code on the same App Service plan, deployment method changes the startup and diagnostics profile: custom container deployments will show different startup timing components, file system semantics, and troubleshooting surface compared with zip deploy.

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

- Application code (identical across both methods)
- App Service SKU and plan
- Runtime version

**Observed:**

- Startup time (cold start to first successful response)
- File system layout and writable paths
- Environment variable exposure
- Available diagnostic tools (Kudu, SSH, log stream)
- Log format and location differences

**Independent run definition**: Fresh deployment of one method, cold restart, and one complete startup-plus-verification capture cycle.

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: Exclude first deployment cache-population cycle; compare subsequent cold restarts under identical conditions.

**Primary metric and meaningful-effect threshold**: Time to first successful response; meaningful effect is >=20% relative difference between methods.

**Comparison method**: Bootstrap confidence interval on per-run startup medians with directional consistency across runs.

## 7. Instrumentation

- Application Insights request telemetry and custom startup checkpoints
- App Service platform logs and container startup logs
- Kudu/SSH inspection for file system and environment verification
- Azure Monitor metrics for restart events, CPU, and memory during startup windows
- External probe script recording first-success timestamp and HTTP readiness behavior

## 8. Procedure

### 8.1 Infrastructure setup

Create a dedicated resource group in `koreacentral`, two Linux plans (`B1`, `P1v3`), one zip-deploy app and one container app per SKU, and one ACR instance for container image storage.

```bash
RG="rg-zip-vs-container-lab"
LOCATION="koreacentral"

PLAN_B1="plan-zvc-b1"
PLAN_P1V3="plan-zvc-p1v3"

ZIP_APP_B1="app-zvc-zip-b1"
ZIP_APP_P1V3="app-zvc-zip-p1v3"
CONTAINER_APP_B1="app-zvc-container-b1"
CONTAINER_APP_P1V3="app-zvc-container-p1v3"

ACR_NAME="acrzvclab"
IMAGE_NAME="zvc-node20"
IMAGE_TAG="v1"

az group create --name "$RG" --location "$LOCATION"

az appservice plan create --resource-group "$RG" --name "$PLAN_B1" --location "$LOCATION" --is-linux --sku B1
az appservice plan create --resource-group "$RG" --name "$PLAN_P1V3" --location "$LOCATION" --is-linux --sku P1v3

az webapp create --resource-group "$RG" --plan "$PLAN_B1" --name "$ZIP_APP_B1" --runtime "NODE|20-lts"
az webapp create --resource-group "$RG" --plan "$PLAN_P1V3" --name "$ZIP_APP_P1V3" --runtime "NODE|20-lts"

az acr create --resource-group "$RG" --name "$ACR_NAME" --sku Basic --location "$LOCATION"
az acr update --name "$ACR_NAME" --admin-enabled true
```

### 8.2 Application code

Prepare one Node.js 20 Express app used for both methods. Include startup checkpoints and inspection endpoints.

```javascript
const express = require("express");
const fs = require("fs");

const app = express();
const startup = {
  processStartTs: new Date().toISOString(),
  importDoneTs: new Date().toISOString(),
  listenTs: null,
  firstRequestTs: null
};

function safeList(path) {
  try {
    return fs.readdirSync(path).slice(0, 50);
  } catch {
    return [];
  }
}

app.get("/health", (_req, res) => {
  if (!startup.firstRequestTs) {
    startup.firstRequestTs = new Date().toISOString();
  }
  res.json({ status: "ok", startup });
});

app.get("/env", (_req, res) => {
  res.json({
    WEBSITE_SITE_NAME: process.env.WEBSITE_SITE_NAME || null,
    WEBSITE_INSTANCE_ID: process.env.WEBSITE_INSTANCE_ID || null,
    WEBSITE_RUN_FROM_PACKAGE: process.env.WEBSITE_RUN_FROM_PACKAGE || null,
    WEBSITES_PORT: process.env.WEBSITES_PORT || null,
    NODE_ENV: process.env.NODE_ENV || null
  });
});

app.get("/fs", (_req, res) => {
  res.json({
    cwd: process.cwd(),
    rootEntries: safeList("/"),
    homeEntries: safeList("/home"),
    tmpEntries: safeList("/tmp")
  });
});

const port = process.env.PORT || 8080;
app.listen(port, () => {
  startup.listenTs = new Date().toISOString();
  console.log(JSON.stringify({ event: "listen", ...startup }));
});
```

### 8.3 Deploy

Deploy the same app by two methods.

1) Zip deploy to the zip apps:

```bash
RG="rg-zip-vs-container-lab"

az webapp deploy --resource-group "$RG" --name "$ZIP_APP_B1" --src-path "./app.zip" --type zip
az webapp deploy --resource-group "$RG" --name "$ZIP_APP_P1V3" --src-path "./app.zip" --type zip
```

2) Build/push custom container to ACR and create container apps:

```bash
RG="rg-zip-vs-container-lab"
ACR_NAME="acrzvclab"
IMAGE_NAME="zvc-node20"
IMAGE_TAG="v1"

az acr build --registry "$ACR_NAME" --image "$IMAGE_NAME:$IMAGE_TAG" .

ACR_SERVER=$(az acr show --resource-group "$RG" --name "$ACR_NAME" --query loginServer --output tsv)

az webapp create --resource-group "$RG" --plan "$PLAN_B1" --name "$CONTAINER_APP_B1" --deployment-container-image-name "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG"
az webapp create --resource-group "$RG" --plan "$PLAN_P1V3" --name "$CONTAINER_APP_P1V3" --deployment-container-image-name "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG"
```

Configure container registry credentials for both container apps:

```bash
RG="rg-zip-vs-container-lab"
ACR_NAME="acrzvclab"
ACR_SERVER=$(az acr show --resource-group "$RG" --name "$ACR_NAME" --query loginServer --output tsv)
ACR_USER=$(az acr credential show --name "$ACR_NAME" --query username --output tsv)
ACR_PASS=$(az acr credential show --name "$ACR_NAME" --query passwords[0].value --output tsv)

az webapp config container set --resource-group "$RG" --name "$CONTAINER_APP_B1" --container-image-name "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG" --container-registry-url "https://$ACR_SERVER" --container-registry-user "$ACR_USER" --container-registry-password "$ACR_PASS"
az webapp config container set --resource-group "$RG" --name "$CONTAINER_APP_P1V3" --container-image-name "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG" --container-registry-url "https://$ACR_SERVER" --container-registry-user "$ACR_USER" --container-registry-password "$ACR_PASS"
```

### 8.4 Test execution

For each configuration (`zip-B1`, `zip-P1v3`, `container-B1`, `container-P1v3`), run five restart-based cold-start measurements.

```bash
RG="rg-zip-vs-container-lab"
APP_NAME="$ZIP_APP_B1"  # Replace per configuration

for run in 1 2 3 4 5; do
  az webapp restart --resource-group "$RG" --name "$APP_NAME"
  START_TS=$(date -u +"%s")

  until curl --silent --fail "https://${APP_NAME}.azurewebsites.net/health" > /tmp/health.json; do
    sleep 2
  done

  END_TS=$(date -u +"%s")
  echo "run=${run},startup_seconds=$((END_TS-START_TS))"
done
```

After each successful startup, collect:

- `GET /env` output for runtime environment variable differences.
- `GET /fs` output for writable path and file layout differences.
- SSH/Kudu observations for deployment artifacts and diagnostic access surfaces.

### 8.5 Data collection

Record outputs in a per-run matrix with the following dimensions:

- Startup time (`seconds`) for each of five restarts.
- Filesystem observations (root layout, `/home`, `/tmp`, write behavior).
- Environment variable set differences (`WEBSITE_RUN_FROM_PACKAGE`, `WEBSITES_PORT`, related container vars).
- Diagnostic tool availability (`SSH`, `Kudu API/console`, platform/container logs).

Compute median and spread for startup time per configuration and compare zip vs container within the same SKU (`B1`, `P1v3`). Use the same timestamp window for platform metrics and application checkpoints.

### 8.6 Cleanup

Delete all resources once measurements and artifacts are exported.

```bash
RG="rg-zip-vs-container-lab"
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Custom container and zip deploy reach healthy state through different startup sequences and timing envelopes.
- Writable path behavior and mounted volume visibility differ between deployment methods.
- Troubleshooting artifacts (log locations, access surfaces) differ even when application code is unchanged.
- Startup latency spread is higher for the method with more initialization steps.

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

- Keep image size and dependency set fixed when comparing custom container runs.
- Force cold restarts before each measured run to avoid warm-state carryover.
- Use the same health endpoint and readiness criteria for both deployment methods.
- Record log source paths during each run because path conventions differ by method.

## 16. Related guide / official docs

- [Microsoft Learn: Deploy a custom container](https://learn.microsoft.com/en-us/azure/app-service/quickstart-custom-container)
- [Microsoft Learn: Zip deploy](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
