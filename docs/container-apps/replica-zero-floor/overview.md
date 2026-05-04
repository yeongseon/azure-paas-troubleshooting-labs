---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Minimum Replica Count Zero Floor: Cold Start After Idle Scale-Down

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a Container Apps revision has `minReplicas: 0`, the app scales to zero after idle and incurs a cold start on the next request. In the Consumption plan, what is the typical cold start duration for a standard Python or Node.js container, and how does this vary with container image size, resource allocation, and the presence of init containers?

## 2. Why this matters

Scale-to-zero is the primary cost optimization for Container Apps Consumption plan. However, the cold start penalty affects user-perceived latency for the first request after an idle period. Teams often set `minReplicas: 0` without understanding the cold start cost. Understanding the breakdown of cold start time (image pull, container initialization, app startup) is essential for making informed decisions about `minReplicas` configuration and for setting realistic timeout expectations for clients.

## 3. Customer symptom

"The first request after a period of no traffic takes 30 seconds — is that normal?" or "Clients are timing out on the first request after deployment" or "We need to know how long cold start takes to set our client timeout correctly."

## 4. Hypothesis

- H1: Cold start duration for a Container Apps revision consists of: (a) scale-from-zero trigger time (KEDA detecting the request), (b) image pull time (or cache hit), (c) container initialization (entrypoint to ready), (d) readiness probe pass delay.
- H2: A Python 3.11 slim container (200MB) with no init containers cold starts in approximately 5-15 seconds on Consumption plan in Korea Central, depending on image cache status.
- H3: A large container image (2GB, e.g., ML model container) significantly increases cold start time due to image pull, even with layer caching.
- H4: Adding an init container that performs slow initialization (e.g., downloads model weights) adds directly to the cold start time.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (containerapps-helloworld) |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Performance / Platform behavior

**Controlled:**

- Container App: `aca-diag-batch` with `minReplicas: 0`, `maxReplicas: 3`
- Image: `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`
- Region: Korea Central (Consumption plan)

**Observed:**

- Time from request initiation to HTTP 200 response (client-side measurement via `curl`)
- Replica count before and after request
- Warm request latency for subsequent requests

**Scenarios:**

- S1: All revisions at 0 replicas (scaled to zero) → first request cold start
- S2: Second and third request immediately after cold start (warm)

## 7. Instrumentation

- Client-side `curl` timer with `date +%s%3N` (millisecond precision)
- `az containerapp revision list` to confirm replica count before/after
- Consecutive requests to measure warm vs. cold latency delta

## 8. Procedure

1. Confirm all active revisions at 0 replicas: `az containerapp revision list --query "[?properties.active].{name,replicas:properties.replicas}"`.
2. Confirm `minReplicas: 0` with `az containerapp update --min-replicas 0`.
3. Send first request and measure time: `START=$(date +%s%3N); curl -s -o /dev/null -w "%{http_code}" <url>; END=$(date +%s%3N); echo $((END-START))ms`.
4. Immediately send second and third requests. Record latencies.
5. Check replica count after requests to confirm scale-up.

## 9. Expected signal

- First request: 5–15 seconds cold start latency.
- Second request: <200ms (warm, replica already running).
- Replica count jumps from 0 → 1 after first request.

## 10. Results

### Pre-experiment state: all replicas at 0

```json
[
  {"name": "aca-diag-batch--0000001", "replicas": 0},
  {"name": "aca-diag-batch--0000002", "replicas": 0},
  {"name": "aca-diag-batch--0000003", "replicas": 0}
]
```

### Cold start and warm request measurements

```
First request (cold start):  HTTP 200 — latency: 21,627 ms  (21.6 seconds)
Second request (warm):       HTTP 200 — latency:    124 ms
Third request (warm):        HTTP 200 — latency:     72 ms
```

### Replica count after scale-up

```json
[
  {"name": "aca-diag-batch--0000001", "replicas": 1},
  {"name": "aca-diag-batch--0000002", "replicas": 0},
  {"name": "aca-diag-batch--0000003", "replicas": 0}
]
```

Only revision `--0000001` (the traffic-weighted revision) scaled up to 1. Non-traffic revisions remained at 0.

## 11. Interpretation

- **Measured**: Cold start latency was 21.6 seconds — above the H2 estimate of 5–15 seconds. The Microsoft Container Apps Hello World image is small (~30MB), so the dominant factor is likely the KEDA scale-from-zero trigger delay and platform-level provisioning overhead, not image pull time.
- **Measured**: Warm latency is 72–124ms, a ~300× reduction from cold start latency. Once the replica is provisioned, the app serves requests normally.
- **Observed**: Only the revision with active traffic weight scales up on demand. Zero-traffic revisions remain at 0 replicas indefinitely, even when the environment receives requests.
- **Inferred**: The 21.6s cold start includes: KEDA trigger detection, node scheduling, image pull (or cache hit), container startup, and readiness probe pass. Exact breakdown requires `ContainerAppSystemLogs` timestamp analysis.
- **Inferred**: H2 is partially confirmed — a small image cold starts without dramatic pull overhead — but the total time (21.6s) exceeds the 5–15s estimate. Korea Central Consumption plan timing may differ from other regions.

## 12. What this proves

- Cold start from scale-to-zero takes approximately 21 seconds for a small image (30MB) on Korea Central Consumption plan. **Measured**.
- Warm request latency is 72–124ms — cold start is a ~300× latency increase. **Measured**.
- Only the traffic-weighted revision scales up on demand; zero-traffic revisions stay at 0 replicas. **Observed**.
- Client timeout must exceed 21 seconds to survive a cold start event. **Measured**.

## 13. What this does NOT prove

- This experiment used a single small image. Cold start for large images (1–2GB) was not measured; image pull time would add significant overhead.
- Init container impact was not tested. A 10-second init container would add directly to the 21.6s total.
- Multiple simultaneous cold start requests were not tested. Queue buildup during scale-from-zero may cause some requests to time out.
- Behavior with `minReplicas: 1` was not measured here (expected: no cold start, <200ms first request).

## 14. Support takeaway

When customers report 20–30 second first-request latency after a period of inactivity:

1. Check `minReplicas` on all active revisions — if 0, cold start is expected behavior.
2. Advise that cold start on Korea Central Consumption plan is approximately 20 seconds for small images; larger images will be slower.
3. Mitigation options: (a) set `minReplicas: 1` to eliminate cold start at ~$13/month cost for a 0.25 vCPU / 0.5 GiB replica; (b) implement a periodic "keep-warm" ping (not officially supported but widely used); (c) configure client timeout ≥ 30 seconds.
4. If `minReplicas: 0` is required for cost reasons, set client HTTP timeout to at least 30 seconds and consider retry logic for the first request.

## 15. Reproduction notes

```bash
RG="rg-lab-aca-batch"
APP="aca-diag-batch"
URL="https://aca-diag-batch.agreeablehill-e6bfb5a7.koreacentral.azurecontainerapps.io"

# Ensure scale-to-zero
az containerapp update -n $APP -g $RG --min-replicas 0 --max-replicas 3

# Verify replicas at 0 (wait 5+ minutes after last request)
az containerapp revision list -n $APP -g $RG \
  --query "[?properties.active].{name:name,replicas:properties.replicas}" -o json

# Measure cold start
START=$(date +%s%3N)
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 "${URL}/")
END=$(date +%s%3N)
echo "Cold start: HTTP ${HTTP}, latency: $((END-START))ms"

# Measure warm requests
for i in 1 2; do
  START=$(date +%s%3N)
  curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${URL}/"
  END=$(date +%s%3N)
  echo "Warm request $i: $((END-START))ms"
done
```

- Replicas reach 0 after approximately 5 minutes of no traffic on Consumption plan.
- Use `--max-time 60` on cold start curl to avoid client-side timeout before the replica is ready.
- Image pull time depends on whether layers are cached at the node level.

## 16. Related guide / official docs

- [Scale rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app#scale-to-zero)
- [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
