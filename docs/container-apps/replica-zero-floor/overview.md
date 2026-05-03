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

# Minimum Replica Count Zero Floor: Cold Start After Idle Scale-Down

!!! info "Status: Planned"

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
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance / Platform behavior

**Controlled:**

- Container image size: small (200MB Python slim) and large (2GB simulated)
- `minReplicas: 0`
- Init container present/absent

**Observed:**

- Time from request arrival to first response byte
- Breakdown of cold start phases (image pull, init, app start, readiness)
- Effect of container image size on pull time

**Scenarios:**

- S1: Small image (200MB), no init container, cold start → baseline
- S2: Large image (2GB), no init container → image pull impact
- S3: Small image with 10-second init container → startup delay added
- S4: Small image, `minReplicas: 1` → no cold start (warm instance)

## 7. Instrumentation

- Client-side timer from request initiation to first response byte
- Container Apps revision scaling events (timestamp of scale-from-zero trigger)
- `ContainerAppSystemLogs` for container start events with timestamps
- Container startup time from health check pass timestamp

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python app with `minReplicas: 0`; let it scale to zero (wait 5+ minutes with no traffic).
2. S1: Send request; time from initiation to response; repeat 5 times; record mean and variance.
3. S2: Build and deploy a 2GB image (padded with dummy layers); repeat cold start timing.
4. S3: Add init container with `sleep 10`; redeploy; repeat cold start timing.
5. S4: Change to `minReplicas: 1`; verify first request is warm (<1s latency).

## 9. Expected signal

- S1: Cold start approximately 5-15 seconds for small image.
- S2: Cold start approximately 30-60 seconds for 2GB image (image pull dominated).
- S3: Cold start = S1 + 10s (init container adds directly to total).
- S4: No cold start; first request served immediately (<1s).

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

- Container Apps scales to zero after approximately 5 minutes of no traffic (Consumption plan).
- Image pull time depends on whether layers are cached at the node level. First cold start may be slower than subsequent ones due to cache warming.
- Use Azure Container Registry in the same region as Container Apps to minimize image pull latency.

## 16. Related guide / official docs

- [Scale rules in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Container Apps performance tuning](https://learn.microsoft.com/en-us/azure/container-apps/scale-app#cold-start-considerations)
