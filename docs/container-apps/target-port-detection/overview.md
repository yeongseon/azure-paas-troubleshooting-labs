---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-10
    cli_version: "2.73.0"
    core_tools_version: null
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Target Port Auto-Detection Trap

!!! info "Status: Published"
    Experiment completed with real data collected on 2026-04-10 from Azure Container Apps Consumption (koreacentral).
    Seven test configurations across 3 container images. Key finding: auto-detection works even **without** the `EXPOSE` directive — the platform scans listening ports at runtime, not Dockerfile metadata.

## 1. Question

When deploying a Container App without explicitly specifying the target port, does the platform auto-detect the correct port? What failure modes occur when `targetPort` is wrong? And does the `EXPOSE` directive in Dockerfile matter for auto-detection?

## 2. Why this matters

Container Apps ingress routes external traffic to a specific TCP port inside the container. If `targetPort` doesn't match the port the application actually listens on, requests fail — but the container itself shows as **running and healthy** in logs. This mismatch is one of the most common deployment issues on Container Apps because:

1. **The container appears healthy.** Gunicorn logs show `Listening at: http://0.0.0.0:8080`, and the container never crashes.
2. **No clear error message.** Depending on the failure mode, users see either a **timeout** (HTTP 000) or a **503 with "Connection refused"** — neither mentions "wrong port."
3. **StartUp probes fail silently.** The system logs show `Probe of StartUp failed with status code: 1`, but most users never check system logs.
4. **Auto-detection exists but is deployment-method-dependent.** `az containerapp up` supports `targetPort=0` (auto-detect), but `az containerapp create` **requires** an explicit `--target-port`.

```text
┌─────────────────────────────────────────────────────────────┐
│  Container Apps Ingress (Envoy Proxy)                       │
│                                                             │
│  External HTTPS ──► Envoy ──► targetPort:80 ──► Container   │
│                                    ▲                        │
│                                    │ WRONG!                 │
│                          App listens on :8080               │
│                                                             │
│  Result: timeout (Envoy waits) or 503 (connection refused)  │
└─────────────────────────────────────────────────────────────┘
```

## 3. Customer symptom

- "My container is running and logs show it's listening on port 8080, but I get timeouts."
- "The app works locally in Docker but not on Container Apps."
- "I deployed with `az containerapp up` and it worked, but when I recreated with `az containerapp create`, it broke."
- "My revision is stuck in 'Activating' and never transitions to 'Running'."

## 4. Hypothesis

**H1 — Auto-detection from EXPOSE**: When `targetPort` is omitted (set to 0), the platform reads the `EXPOSE` directive from the Dockerfile to determine the port.

**H2 — EXPOSE required**: Without `EXPOSE`, auto-detection fails and the platform falls back to a default port (e.g., 80).

**H3 — Wrong port = 502/503**: An explicitly wrong `targetPort` produces a 502 or 503 error, not a timeout.

**H4 — Container health unaffected**: The container shows as running/healthy even when targetPort mismatches.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask 3.1.3 + Gunicorn 25.3.0) |
| OS | Linux |
| Container Environment | `cae-target-port` |
| ACR | `ca43d23d0adeacr` (auto-created by `az containerapp up`) |
| Date tested | 2026-04-10 |
| CLI version | 2.73.0 |

## 6. Variables

**Experiment type**: Config (single run per configuration)

**Controlled:**

- Container image: 3 variants (EXPOSE 8080, EXPOSE 9999, no EXPOSE — all Flask/Gunicorn)
- Target port configuration: auto-detect (0), explicit correct, explicit wrong
- Deployment method: `az containerapp create` vs `az containerapp up --source`

**Observed:**

- HTTP response: status code, response time, response body
- Revision state: `runningState`, `healthState`
- StartUp probe results: pass/fail count from system logs
- Recovery behavior: time to recover after fixing targetPort

## 7. Instrumentation

- **Azure CLI**: `az containerapp show`, `az containerapp revision list` for port and revision state
- **curl**: HTTP requests to the ingress FQDN with `--max-time 30` timeout
- **System logs**: `az containerapp logs show --type system` for probe results
- **Container logs**: `az containerapp logs show` for application startup output

### Test Images

Three Flask applications, identical except for port configuration:

```dockerfile
# Image 1: port-app-8080 (EXPOSE 8080)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "app:app"]
```

```dockerfile
# Image 2: port-app-9999 (EXPOSE 9999)
# Same as above but EXPOSE 9999 and gunicorn binds 0.0.0.0:9999
```

```dockerfile
# Image 3: port-no-expose (NO EXPOSE directive)
# Same as port-app-9999 but without EXPOSE line
# Gunicorn binds 0.0.0.0:9999
```

Each app returns `{"status": "ok", "port": <configured_port>, "hostname": "<container_hostname>"}` on `/`.

## 8. Procedure

### Test Matrix

| Test | Image | Deploy Method | targetPort Config | Effective targetPort | Purpose |
|------|-------|---------------|-------------------|---------------------|---------|
| T1 | port-8080 (EXPOSE 8080) | `az containerapp create` | 8080 (explicit correct) | 8080 | Baseline: correct port works |
| T2 | port-8080 (EXPOSE 8080) | `az containerapp create` | 80 (explicit wrong) | 80 | Wrong port failure mode |
| T3 | port-9999 (EXPOSE 9999) | `az containerapp up --source` | omitted (auto-detect) | 0 | Auto-detect WITH EXPOSE |
| T4 | port-9999 (EXPOSE 9999) | `az containerapp ingress update` | 8080 (explicit wrong) | 8080 | Wrong port on running app |
| T5 | port-no-expose (no EXPOSE) | `az containerapp up --source` | omitted (auto-detect) | 0 | Auto-detect WITHOUT EXPOSE |
| T6 | port-no-expose (no EXPOSE) | `az containerapp ingress update` | 9999 (explicit correct) | 9999 | Explicit correct on no-EXPOSE |
| T2-R | port-8080 (EXPOSE 8080) | `az containerapp ingress update` | 8080 (fix from 80) | 8080 | Recovery after wrong port |

### Execution Steps

1. **Build images** in ACR using `az acr build`
2. **T1**: Create app with `--target-port 8080`, verify HTTP 200
3. **T2**: Delete app, recreate with `--target-port 80`, observe failure mode
4. **T3**: Delete app, deploy with `az containerapp up --source` (port-9999 image with EXPOSE 9999), no `--target-port` → observe auto-detection
5. **T4**: Update T3 app's ingress to `--target-port 8080`, observe failure mode on running app
6. **T5**: Delete app, deploy with `az containerapp up --source` (no-EXPOSE image), no `--target-port` → observe auto-detection
7. **T6**: Update T5 app's ingress to `--target-port 9999`, verify HTTP 200
8. **T2-R**: From T2 state, fix ingress to `--target-port 8080`, measure recovery time

## 9. Expected signal

- T1, T6: HTTP 200 — explicit correct port always works
- T2: 502 or 503 — wrong port on fresh deploy
- T3: HTTP 200 if EXPOSE works for auto-detection; failure if not
- T4: 502 or 503 — wrong port on running app
- T5: Failure expected — no EXPOSE means no auto-detection source
- T2-R: HTTP 200 after recovery, with measurable activation delay

## 10. Results

### Summary Table

| Test | Image | targetPort | HTTP Code | Response Time | Revision State | Finding |
|------|-------|-----------|-----------|---------------|----------------|---------|
| **T1** | port-8080 | 8080 ✓ | **200** | 60-65 ms | Running / Healthy | ✅ Correct port works |
| **T2** | port-8080 | 80 ✗ | **000 (timeout)** | 30.0 s | Activating / None | ❌ Timeout, stuck activating |
| **T3** | port-9999 (EXPOSE) | 0 (auto) | **200** | 8.1 s → 55 ms | Running / Healthy | ✅ Auto-detect works with EXPOSE |
| **T4** | port-9999 | 8080 ✗ | **503** | 250-500 ms | Running / Healthy | ❌ Connection refused |
| **T5** | no-expose | 0 (auto) | **200** | 65-68 ms | Running / Healthy | ✅ **Auto-detect works WITHOUT EXPOSE** |
| **T6** | no-expose | 9999 ✓ | **200** | 56-63 ms | Running / Healthy | ✅ Explicit correct works |
| **T2-R** | port-8080 | 8080 (fix) | **200** | 13.5 s → 61 ms | Running / Healthy | ✅ Recovery works |

### T1: Explicit Correct Port (Baseline)

```bash
az containerapp create \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --environment cae-target-port \
  --image ca43d23d0adeacr.azurecr.io/port-app-8080:v1 \
  --ingress external \
  --target-port 8080
```

```text
HTTP_CODE:200 TIME:0.065s SIZE:49
{"hostname":"unknown","port":8080,"status":"ok"}
```

!!! success "Result"
    HTTP 200 on all attempts. Revision immediately healthy. **Baseline confirmed.**

### T2: Explicit Wrong Port (Fresh Deploy)

```bash
az containerapp create \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --environment cae-target-port \
  --image ca43d23d0adeacr.azurecr.io/port-app-8080:v1 \
  --ingress external \
  --target-port 80   # WRONG — app listens on 8080
```

```text
# All 3 attempts:
HTTP_CODE:000 TIME:30.001s SIZE:0   # Timeout
HTTP_CODE:000 TIME:30.001s SIZE:0
HTTP_CODE:000 TIME:30.002s SIZE:0
```

Revision state:

```json
{
  "runningState": "Activating",
  "healthState": "None",
  "replicas": 1
}
```

Container logs show the app is running normally:

```text
[2026-04-10 13:44:00 +0000] [1] [INFO] Starting gunicorn 25.3.0
[2026-04-10 13:44:00 +0000] [1] [INFO] Listening at: http://0.0.0.0:8080 (1)
[2026-04-10 13:44:00 +0000] [1] [INFO] Using worker: sync
```

System logs show **190 consecutive StartUp probe failures**:

```text
Type: Warning
Msg: "Probe of StartUp failed with status code: 1"
Reason: ProbeFailed
Count: 190  (1 per second for ~3 minutes)
```

!!! danger "Result"
    **Timeout (HTTP 000), not 502/503.** Revision stuck in `Activating` indefinitely. Ingress holds the connection open waiting for a backend that never responds on port 80. StartUp probe fails 190+ times. The container itself is running and healthy — gunicorn is listening on 8080.

### T3: Auto-Detection WITH EXPOSE (az containerapp up)

```bash
az containerapp up \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --environment cae-target-port \
  --source /tmp/port-app-9999 \
  --ingress external
  # No --target-port specified
```

API shows `targetPort: 0` (auto-detect mode):

```json
{"targetPort": 0}
```

```text
HTTP_CODE:200 TIME:8.064s SIZE:49   # First request (cold start)
{"hostname":"unknown","port":9999,"status":"ok"}

HTTP_CODE:200 TIME:0.055s SIZE:49   # Subsequent
```

!!! success "Result"
    **Auto-detection works.** `targetPort=0` correctly routes to port 9999 (matching EXPOSE 9999). First request slow (8s cold start), then fast (~55ms). **H1 confirmed.**

### T4: Explicit Wrong Port on Running App

Starting from T3's running app (port-9999 image, currently working with auto-detect):

```bash
az containerapp ingress update \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --target-port 8080   # WRONG — app listens on 9999
```

```text
HTTP_CODE:503 TIME:0.335s SIZE:190
upstream connect error or disconnect/reset before headers.
retried and the latest reset reason: remote connection failure,
transport failure reason: delayed connect error: Connection refused
```

!!! danger "Result"
    **503 with "Connection refused" — fast failure (~250-500ms).** This differs from T2 (timeout on fresh deploy). The difference: T4 changed the port on an already-running revision, so Envoy immediately gets "connection refused" when trying port 8080. T2 was a fresh deploy where the revision never activated.

### T5: Auto-Detection WITHOUT EXPOSE ⭐

```bash
az containerapp up \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --environment cae-target-port \
  --source /tmp/port-app-no-expose \
  --ingress external
  # No --target-port, AND no EXPOSE in Dockerfile
```

API shows `targetPort: 0`:

```json
{"targetPort": 0}
```

```text
HTTP_CODE:200 TIME:0.067s SIZE:49
{"hostname":"unknown","port":9999,"status":"ok"}

HTTP_CODE:200 TIME:0.068s SIZE:49
HTTP_CODE:200 TIME:0.065s SIZE:49
```

!!! success "Major Finding"
    **Auto-detection works even WITHOUT the EXPOSE directive.** The platform detected port 9999 purely by scanning which port the application opened at runtime. This **disproves H2** — EXPOSE is NOT required. Container Apps auto-detection operates at the network layer (listening socket scan), not at the Dockerfile metadata layer.

### T6: Explicit Correct Port on No-EXPOSE Image

```bash
az containerapp ingress update \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --target-port 9999
```

```text
HTTP_CODE:200 TIME:0.063s SIZE:49
{"hostname":"unknown","port":9999,"status":"ok"}
```

!!! success "Result"
    Explicit correct port works regardless of EXPOSE presence. **Expected baseline.**

### T2-Recovery: Fixing Wrong Port

Starting from T2's broken state (port-8080 image, targetPort=80, revision stuck in Activating):

```bash
az containerapp ingress update \
  --name ca-port-test \
  --resource-group rg-target-port-lab \
  --target-port 8080   # Fix to correct port
```

```text
HTTP_CODE:200 TIME:13.507s SIZE:49   # First request — new replica activation
{"hostname":"unknown","port":8080,"status":"ok"}

HTTP_CODE:200 TIME:0.061s SIZE:49    # Subsequent
HTTP_CODE:200 TIME:0.064s SIZE:49
```

Revision state transition:

```text
Before fix: runningState=Activating, healthState=None
After fix:  runningState=Running, healthState=Healthy
```

!!! success "Result"
    **Recovery works.** Fixing `targetPort` creates a new replica that activates in ~13.5s. The old replica with 190 failed probes is terminated (`ManuallyStopped`). Subsequent requests are fast (~60ms).

## 11. Interpretation

### Hypothesis Evaluation

| Hypothesis | Verdict | Evidence |
|-----------|---------|----------|
| **H1**: Auto-detect reads EXPOSE | **Partially wrong** | Auto-detect works **[Observed]**, but NOT because of EXPOSE — T5 proves it works without EXPOSE too **[Measured]** |
| **H2**: EXPOSE required for auto-detect | **Disproved** ❌ | T5: no EXPOSE, targetPort=0, HTTP 200 **[Observed]**. Platform scans listening ports at runtime **[Inferred]** |
| **H3**: Wrong port = 502/503 | **Partially correct** | T4 gives 503 **[Observed]**, but T2 gives **timeout** (HTTP 000) **[Observed]** — failure mode depends on deployment state **[Inferred]** |
| **H4**: Container health unaffected | **Confirmed** ✅ | T2: container logs show healthy gunicorn **[Observed]**, but StartUp probe fails 190 times **[Measured]** |

### Two Distinct Failure Modes

The experiment revealed that **wrong targetPort produces different symptoms depending on deployment state**:

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Wrong targetPort Failure Modes                                      │
│                                                                      │
│  Case 1: Fresh deploy (T2)                                           │
│  ┌─────────────┐     ┌──────────────────────────┐                   │
│  │ New revision │────▶│ Revision stuck Activating │                   │
│  │ targetPort=80│     │ StartUp probe fails ×190  │                   │
│  └─────────────┘     │ HTTP: timeout (000)        │                   │
│                      └──────────────────────────┘                   │
│                                                                      │
│  Case 2: Port change on running app (T4)                             │
│  ┌─────────────┐     ┌──────────────────────────┐                   │
│  │ Running rev  │────▶│ Envoy gets conn refused   │                   │
│  │ change to    │     │ HTTP: 503 (250-500ms)     │                   │
│  │ targetPort=  │     │ Envoy error: "upstream     │                   │
│  │ 8080 (wrong) │     │  connect error"           │                   │
│  └─────────────┘     └──────────────────────────┘                   │
└──────────────────────────────────────────────────────────────────────┘
```

**Why the difference?**

- **Fresh deploy**: The revision is brand new. The StartUp probe fires against the wrong port and never succeeds **[Observed]**. The revision never transitions from `Activating` to `Running` **[Observed]**. Ingress has no healthy backend → holds the connection open → **timeout** **[Inferred]**.
- **Running app**: The revision is already `Running` with active replicas. Envoy proxy attempts to connect to the new port but immediately gets "connection refused" **[Observed]** → **503 in ~300ms** **[Measured]**.

### Auto-Detection Mechanism

The experiment proves that Container Apps auto-detection (`targetPort=0`) does **not** rely on the Dockerfile `EXPOSE` directive **[Observed]**. Instead, it appears to scan the container's listening sockets at runtime **[Inferred]**:

1. Container starts and opens a TCP listener on port 9999
2. The platform detects the listening socket
3. Ingress routes traffic to the detected port

This explains why `az containerapp up --source` works reliably even for non-standard ports — it builds from source, starts the container, detects the port dynamically **[Inferred]**.

!!! warning "Auto-detect is deployment-method-dependent"
    - `az containerapp up --source`: Supports auto-detect (`targetPort=0`)
    - `az containerapp create --image`: **Requires** explicit `--target-port`
    - `az containerapp ingress update`: **Requires** explicit `--target-port`

    Auto-detection is only available at initial creation time via `az containerapp up` **[Observed]**.

## 12. What this proves

!!! abstract "Evidence-backed conclusions"

    1. **`EXPOSE` is irrelevant for auto-detection.** The platform scans listening ports at runtime, not Dockerfile metadata **[Inferred]**. T3 (with EXPOSE) and T5 (without EXPOSE) both succeeded equally **[Observed]**.

    2. **Wrong targetPort on fresh deploy = timeout + stuck Activating.** Not 502/503 — the revision never activates because StartUp probes fail on the wrong port **[Observed]**. Users see a 30-second timeout followed by no response (HTTP 000) **[Measured]**.

    3. **Wrong targetPort on running app = 503 Connection refused.** Fast failure (250-500ms) with Envoy error message **[Measured]**.

    4. **Container appears healthy even with wrong port.** Gunicorn logs show normal startup **[Observed]**. The mismatch is only visible in system logs (StartUp probe failures) **[Observed]**.

    5. **Recovery is fast after port correction.** Fixing `targetPort` creates a new replica that activates in ~13.5 seconds **[Measured]**.

    6. **Auto-detect is deployment-method-dependent.** Only `az containerapp up` supports `targetPort=0` **[Observed]**. `az containerapp create` requires explicit `--target-port` **[Observed]**.

## 13. What this does NOT prove

- **Multi-port containers**: If a container listens on multiple ports, which one does auto-detection pick? (Not tested — our images had a single listener.)
- **Non-HTTP protocols**: Does auto-detection work for TCP-only or gRPC containers?
- **Azure Portal behavior**: The Portal may have different auto-detection logic than the CLI.
- **Framework-specific defaults**: Whether the platform has special handling for known frameworks (Express on 3000, ASP.NET on 8080) beyond socket scanning.
- **Startup order**: If the app takes 30+ seconds to start listening, does auto-detection still catch it?

## 14. Support takeaway

!!! tip "Triage checklist for port mismatch issues"

    **If customer reports timeouts on a fresh Container Apps deployment:**

    1. Check `targetPort` in ingress config: `az containerapp show --name <app> --resource-group <rg> --query properties.configuration.ingress.targetPort`
    2. Check container logs for the actual listening port: `az containerapp logs show --name <app> --resource-group <rg>`
    3. Compare the two — if they don't match, that's the root cause
    4. Check system logs for probe failures: `az containerapp logs show --name <app> --resource-group <rg> --type system`
    5. Fix: `az containerapp ingress update --name <app> --resource-group <rg> --target-port <correct_port>`

    **Key signals:**

    | Signal | Indicates |
    |--------|-----------|
    | Revision stuck in `Activating` | Wrong targetPort on fresh deploy |
    | `Probe of StartUp failed with status code: 1` in system logs | Port mismatch (probe uses targetPort) |
    | Container log shows `Listening at: http://0.0.0.0:XXXX` but targetPort differs | Root cause confirmed |
    | HTTP 503 + "upstream connect error...Connection refused" | Wrong targetPort on running revision |
    | HTTP 000 (timeout) on fresh deploy | Wrong targetPort, revision never activated |

    **Common customer mistakes:**

    1. Using `az containerapp create` without `--target-port` → ingress not configured
    2. Copying `--target-port 80` from examples when app listens on different port
    3. Deploying with `az containerapp up` (auto-detect works), then recreating with `az containerapp create` (auto-detect NOT available) → breaks
    4. Assuming EXPOSE in Dockerfile is sufficient → `az containerapp create` ignores EXPOSE

## 15. Reproduction notes

- Auto-detection via `az containerapp up --source` creates a **new ACR** in the resource group for image storage
- When switching images across ACRs, registry credentials must match or be updated
- Revision deactivation + reactivation can cause unexpected state transitions (old revision may re-serve traffic if new revision fails)
- `targetPort=0` in the API response means auto-detect mode is active; it's not a literal port 0
- StartUp probe failures accumulate at ~1/second, reaching 190 failures in ~3 minutes with wrong port
- Recovery from wrong port creates a new replica; the old replica with failed probes is terminated with reason `ManuallyStopped`
- Test window: 2026-04-10T13:34:00Z to 2026-04-10T13:53:30Z

## 16. Related guide / official docs

- [Ingress in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview) — official ingress configuration reference including targetPort
- [Deploy Azure Container Apps with the az containerapp up command](https://learn.microsoft.com/en-us/azure/container-apps/containerapp-up) — documents the `az containerapp up` flow including auto-detection
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes) — startup, liveness, and readiness probe behavior
- [Azure Container Apps image configuration](https://learn.microsoft.com/en-us/azure/container-apps/containers) — container image requirements
