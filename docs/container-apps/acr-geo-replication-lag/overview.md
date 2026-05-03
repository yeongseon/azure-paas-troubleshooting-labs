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

# ACR Geo-Replication Lag: Stale Image Pulled from Remote Replica

!!! info "Status: Planned"

## 1. Question

When Azure Container Registry geo-replication is configured and a new image is pushed to the primary region, there is a replication lag to secondary regions. If Container Apps pulls the image from the nearest geo-replicated registry during this lag window, it may pull an older image layer. What is the observable behavior during the replication lag, and how can it be detected and mitigated?

## 2. Why this matters

Teams use ACR geo-replication to reduce image pull latency for Container Apps in remote regions. When a new container image is deployed and ACR is still replicating to the secondary replica, Container Apps may pull a mix of old and new image layers, or the latest tag may point to an older manifest. This causes new revisions to start with the wrong application version — a silent rollout failure where the platform reports success but the wrong code is running.

## 3. Customer symptom

"New deployment shows the old version of the application" or "Some replicas run the new version but others run the old version" or "Deployment reports success but the application behavior hasn't changed."

## 4. Hypothesis

- H1: After pushing a new image tag to ACR, the primary region updates the manifest immediately. The geo-replicated secondary may lag by 30 seconds to several minutes depending on image size and network conditions.
- H2: During the lag window, a `docker pull <registry>.azurecr.io/<image>:latest` from a Container Apps environment in the secondary region may receive the old image (the secondary hasn't received the new manifest yet).
- H3: Using immutable image tags (SHA256 digest) rather than mutable tags (`:latest`, `:v2`) prevents pulling a stale image: a digest-pinned image either exists in the replica (and is correct) or fails to pull entirely (clear failure), rather than silently returning an old image.
- H4: The ACR replication status is visible in the registry's **Geo-replication** blade; replication events are logged in ACR diagnostic logs.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps (with Azure Container Registry, geo-replicated) |
| SKU / Plan | Consumption |
| Region | Korea Central (primary), Japan East (secondary replica) |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Reliability

**Controlled:**

- ACR Premium (geo-replication enabled) with Korea Central as primary, Japan East as replica
- Container app in Japan East region pulling from the geo-replicated registry
- Image push timing and pull timing relative to replication

**Observed:**

- Image version reported by the container after deployment
- Time delta between push completion and replica sync
- ACR replication lag duration

**Scenarios:**

- S1: Pull immediately after push → observe whether stale or new image
- S2: Pull 5 minutes after push → observe consistency
- S3: Use digest-pinned tag → no stale pull possible

## 7. Instrumentation

- `az acr replication list` and `az acr replication show` for replication status
- Container app response showing image build timestamp or version
- ACR diagnostic logs for replication events
- ACR geo-replication status dashboard in the portal

## 8. Procedure

_To be defined during execution._

### Sketch

1. Push image v1 to ACR; verify both regions replicated; deploy container app in Japan East pulling from ACR.
2. Push image v2 to ACR immediately.
3. S1: Within 30 seconds of push, trigger a new Container Apps revision in Japan East; observe which version starts.
4. S2: Wait 5 minutes; trigger another revision; verify v2 is now running.
5. S3: Push image v3 using digest pinning (`containerapp update --image <registry>.azurecr.io/<image>@sha256:<digest>`); verify correct version without replication race.

## 9. Expected signal

- S1: Container may start with v1 (stale) if Japan East replica hasn't received v2 yet; application version endpoint returns "v1".
- S2: Japan East replica has v2; container starts with v2.
- S3: Digest-pinned deployment either starts correctly (digest exists) or fails to pull (clear error), never silently wrong.

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

- ACR geo-replication is a Premium SKU feature.
- Replication lag depends on image size; large images (GBs) may take minutes to replicate.
- Best practice: use image digest in production deployments; tag-based deployments are vulnerable to race conditions.
- `az acr import` can be used to force-copy a specific image to a replica without waiting for replication.

## 16. Related guide / official docs

- [Geo-replication in Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-geo-replication)
- [Container image tags and digests](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-image-tag-version)
