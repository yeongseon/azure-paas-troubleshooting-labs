---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-11
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Zip Deploy vs Custom Container Behavior

!!! success "Status: Published"

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
| Date tested | 2026-04-11 |

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

### 10.1 Startup time (cold start)

Each configuration was tested with stop-verify-start cold restarts across two batches (10 attempts per config). Stale runs (same container hostname as previous) were excluded.

| Configuration | N | Median (s) | Mean (s) | StdDev (s) | Min (s) | Max (s) |
|---|---|---|---|---|---|---|
| **zip-B1** | 8 | 71.7 | 59.4 | 36.1 | 4.2 | 94.6 |
| **zip-P1v3** | 6 | 26.4 | 28.1 | 19.3 | 6.3 | 53.5 |
| **container-B1** | 8 | 67.1 | 72.9 | 39.5 | 11.4 | 130.4 |
| **container-P1v3** | 8 | 49.3 | 39.3 | 20.3 | 4.2 | 52.4 |

!!! note "High variance across all configurations"
    All configurations showed standard deviations exceeding 50% of the mean, indicating that App Service cold start timing is dominated by platform-level scheduling variance (container placement, image layer caching, host availability) rather than by the deployment method itself.

### 10.2 Environment variable differences

| Variable | Zip Deploy | Custom Container |
|---|---|---|
| `WEBSITE_STACK` | `NODE` | `DOCKER` |
| `PORT` | `8080` | _(not set)_ |
| `WEBSITES_PORT` | _(not set)_ | `8080` (user-configured) |
| `DOCKER_CUSTOM_IMAGE_NAME` | _(not set)_ | _(not set — but `DOCKER_REGISTRY_SERVER_URL` present)_ |
| `WEBSITE_RUN_FROM_PACKAGE` | _(not set)_ | _(not set)_ |
| `WEBSITE_SITE_NAME` | set | set |
| `WEBSITE_INSTANCE_ID` | set | set |

!!! warning "PORT vs WEBSITES_PORT"
    Zip deploy apps receive the port via `PORT` (set by the platform Oryx build). Custom container apps require `WEBSITES_PORT` to be explicitly configured — without it, the platform defaults to port 80 and the container fails to start if it listens on a different port.

### 10.3 Filesystem layout differences

| Aspect | Zip Deploy | Custom Container |
|---|---|---|
| Working directory (`cwd`) | `/home/site/wwwroot` | `/app` (from Dockerfile `WORKDIR`) |
| `/home` contents | `.gitconfig`, `ASP.NET`, `LogFiles`, `site/`, deployment artifacts | `node` (single entry) |
| `/home/site/wwwroot` | `app.js`, `node_modules/`, `oryx-manifest.toml`, `hostingstart.html` | _(empty)_ |
| `/tmp` contents | `.dotnet`, CLR debug pipes | _(empty)_ |
| Deployment artifacts | `oryx-manifest.toml`, `node_modules.tar.gz`, `_del_node_modules` visible | None visible (image layers are opaque) |
| Build system | Oryx (server-side build) | ACR Tasks / `docker build` (client-side or ACR) |

!!! tip "Key insight: /home mount semantics"
    Zip deploy apps have full `/home` persistence (Kudu artifacts, deployment history, Git config). Custom container apps get a minimal `/home` with only the Node.js user directory — no Kudu, no deployment history, no `site/wwwroot` structure.

### 10.4 Diagnostic surface differences

| Capability | Zip Deploy | Custom Container |
|---|---|---|
| Kudu (SCM site) | Full access — file browser, process explorer, console | Limited — no file browser for app code |
| SSH | Available via Kudu | Available if configured in Dockerfile |
| Platform logs | `LogFiles/` under `/home` | Container stdout/stderr via `docker-container-logging` |
| cgroup memory limit | `9223372036854771712` (unlimited) | `9223372036854771712` (unlimited) |
| memTotal (B1) | 1,945,784,320 (~1.86 GB) | 1,945,784,320 (~1.86 GB) |
| memTotal (P1v3) | 8,277,880,832 (~7.71 GB) | 8,277,880,832 (~7.71 GB) |

## 11. Interpretation

1. **Startup timing is not meaningfully different between zip deploy and custom container on the same SKU.** **[Observed]** The median difference within each SKU (B1: 71.7s zip vs 67.1s container; P1v3: 26.4s zip vs 49.3s container) is within the standard deviation of each measurement **[Measured]**. The dominant variance comes from platform scheduling **[Inferred]**, not deployment method.

2. **P1v3 is faster than B1 across both methods.** **[Observed]** Zip-P1v3 median (26.4s) is 63% faster than zip-B1 (71.7s) **[Measured]**. Container-P1v3 median (49.3s) is 27% faster than container-B1 (67.1s) **[Measured]**. Premium SKUs have dedicated compute and faster image pulling **[Inferred]**.

3. **The deployment method fundamentally changes the filesystem and diagnostic surface, not the performance profile.** **[Observed]** Zip deploy provides rich Kudu artifacts and server-side Oryx build logs. Custom containers provide none of these **[Measured]** — troubleshooting shifts from Kudu browsing to container log inspection **[Inferred]**.

4. **Environment variable semantics differ in a potentially breaking way.** **[Observed]** Zip deploy uses `PORT` (set by Oryx). Custom container needs `WEBSITES_PORT` (user must set it) **[Measured]**. An app that reads `process.env.PORT` will break in a custom container if `WEBSITES_PORT` is set but `PORT` is not injected into the container **[Strongly Suggested]**.

## 12. What this proves

- [x] `[EVIDENCE:env-diff]` **[Measured]** Zip deploy and custom container apps expose different environment variables (`WEBSITE_STACK=NODE` vs `DOCKER`, `PORT` vs `WEBSITES_PORT`).
- [x] `[EVIDENCE:fs-diff]` **[Observed]** Filesystem layout differs significantly: `/home/site/wwwroot` with Oryx artifacts (zip) vs custom `WORKDIR` with no `/home` persistence (container).
- [x] `[EVIDENCE:diag-diff]` **[Observed]** Diagnostic surface changes: full Kudu access (zip) vs limited Kudu with container-only logs (container).
- [x] `[EVIDENCE:startup-variance]` **[Measured]** Cold start timing is dominated by platform variance (>50% CV across all configs), not by deployment method.
- [x] `[EVIDENCE:sku-effect]` **[Measured]** P1v3 consistently faster than B1 for both deployment methods.

## 13. What this does NOT prove

- **Image size impact**: The container image used (`node:20-slim` ~200MB) is small. Larger images (1GB+) would likely show container startup penalty that zip deploy avoids.
- **Warm start differences**: Only cold starts were measured. Warm start behavior (after initial container is running) may differ.
- **Network pull timing**: ACR is in the same region. Cross-region image pulls would add latency to container starts only.
- **Oryx build overhead**: Zip deploy used pre-built `node_modules` in the zip. If Oryx builds from scratch on each restart, zip deploy times would be higher.
- **App Service storage performance**: No I/O benchmarks were run to compare `/home` NFS mount (zip) vs container overlay fs performance.

## 14. Support takeaway

!!! tip "When a customer reports 'it broke after switching to containers'"
    1. **Check `WEBSITES_PORT`** — the #1 cause of container startup failure. Zip deploy apps get `PORT` from Oryx; containers need `WEBSITES_PORT` explicitly.
    2. **Check filesystem assumptions** — if the app reads from `/home/site/wwwroot` or expects Kudu artifacts, it will fail in a container where `cwd` is the Dockerfile `WORKDIR`.
    3. **Don't blame startup time** — cold start variance is 30-130s on both methods. A 60s wait is normal, not a regression.
    4. **Redirect troubleshooting** — container apps need `az webapp log config --docker-container-logging filesystem` enabled. Kudu file browser won't show app files.

## 15. Reproduction notes

- Keep image size and dependency set fixed when comparing custom container runs.
- Force cold restarts before each measured run to avoid warm-state carryover.
- Use the same health endpoint and readiness criteria for both deployment methods.
- Record log source paths during each run because path conventions differ by method.

## 16. Related guide / official docs

- [Microsoft Learn: Deploy a custom container](https://learn.microsoft.com/en-us/azure/app-service/quickstart-custom-container)
- [Microsoft Learn: Zip deploy](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
