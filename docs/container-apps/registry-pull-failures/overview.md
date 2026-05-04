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

# Container Registry Pull Failures: Authentication, Rate Limiting, and Private Registry Access

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a Container App fails to pull its container image — due to an incorrect registry credential, an expired managed identity token for a private ACR, or a Docker Hub rate limit — how does the failure manifest in system logs and replica provisioning events, and how does the error message differ across failure types?

## 2. Why this matters

Container image pull failures are a top cause of Container App deployment failures, but the error messages are inconsistent. An authentication failure against ACR, a rate limit from Docker Hub, and a network-level failure reaching a private registry all produce provisioning failures that look similar in the Azure portal ("Container failed to start"). The `ContainerAppSystemLogs` entries for each failure type differ in the `Message` field, but support engineers must know which patterns to look for to distinguish them. Image pull failures are also silent when the previous revision is still running — the new revision silently stays unprovisioned.

## 3. Customer symptom

"I deployed a new revision but it never became active" or "My Container App used to pull from Docker Hub but now it fails intermittently" or "I updated my ACR credential but the app still can't pull the image."

## 4. Hypothesis

- H1: When ACR authentication fails (wrong password, expired service principal, revoked managed identity role), the replica provisioning fails with a message in `ContainerAppSystemLogs` that includes "unauthorized" or "authentication required". The previous revision continues serving traffic if traffic splitting is configured; if there is no previous active revision, the app returns 503.
- H2: Docker Hub rate limiting (429 Too Many Requests) produces a distinct error in `ContainerAppSystemLogs` compared to an authentication failure (401). The rate limit error appears as a pull failure with "toomanyrequests" in the message.
- H3: When pulling from a private registry over a Private Endpoint without proper DNS or network configuration, the pull fails with a network timeout, not an authentication error.
- H4: After an image pull failure, the previous revision continues serving traffic uninterrupted.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Reliability / Configuration

**Controlled:**

- Container App: `aca-diag-batch` with active revision `--0000001` serving traffic
- Image registry: Microsoft Container Registry (MCR) — public, no credentials required

**Observed:**

- CLI error message when deploying with a non-existent image tag
- App HTTP response during and after failed revision deployment
- Revision state (active/inactive) after failed pull

**Scenarios:**

- S1: Deploy with valid image tag → success (baseline)
- S2: Deploy with non-existent image tag → pull failure, observe error message and traffic behavior

## 7. Instrumentation

- `az containerapp update --image <bad-tag>` — triggers revision deployment and pull attempt
- `curl` HTTP check against app URL during failed deployment
- `az containerapp revision list` — revision state and traffic weight after failure

## 8. Procedure

1. Baseline: App running with `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`. Confirm HTTP 200.
2. Attempt `az containerapp update --image mcr.microsoft.com/azuredocs/containerapps-helloworld:nonexistent-tag-12345`.
3. Observe CLI error output.
4. Immediately curl the app URL — verify existing revision still serves traffic.
5. Check `az containerapp revision list` for active revision state and traffic weights.

## 9. Expected signal

- S2: CLI returns an error with "MANIFEST_UNKNOWN" or similar; the update command fails before committing; previous revision stays active and serving.

## 10. Results

### S1 — Baseline (valid image)

```
App URL: https://aca-diag-batch.agreeablehill-e6bfb5a7.koreacentral.azurecontainerapps.io/
HTTP: 200
Active revision: aca-diag-batch--0000001 (replicas: 1, traffic: 70)
```

### S2 — Non-existent image tag

```bash
$ az containerapp update -n aca-diag-batch -g rg-lab-aca-batch \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:nonexistent-tag-12345"
```

```
ERROR: Failed to provision revision for container app 'aca-diag-batch'.
Error details: The following field(s) are either invalid or missing.
Field 'template.containers.aca-diag-batch.image' is invalid with details:
'Invalid value: "mcr.microsoft.com/azuredocs/containerapps-helloworld:nonexistent-tag-12345":
GET https:: MANIFEST_UNKNOWN: manifest tagged by "nonexistent-tag-12345" is not found;
map[Tag:nonexistent-tag-12345]'
```

### App behavior during failed revision

```
HTTP after failed update: 200
# Previous revision continued serving traffic uninterrupted
```

### Revision state after failed update

```
Name                     Active    Traffic    Healthy
-----------------------  --------  ---------  ---------
aca-diag-batch--0000001  True      70         Healthy
aca-diag-batch--0000002  True       0         Healthy
aca-diag-batch--0000003  True       0         Healthy
```

No new revision was created. The bad image update was rejected at the provisioning layer before a new revision record was written.

## 11. Interpretation

- **Observed**: The CLI returns a synchronous error for a non-existent image tag — the error `MANIFEST_UNKNOWN` is surfaced immediately during the `az containerapp update` call. The platform validates the image tag before committing the revision.
- **Observed**: The existing active revision (`--0000001`) continued serving HTTP 200 throughout the failed update. H4 is confirmed — traffic is uninterrupted when a new revision fails to deploy.
- **Inferred**: The `MANIFEST_UNKNOWN` error is specific to "tag not found on the registry." This is distinct from authentication failures (which would return "unauthorized" or "authentication required") and rate limit errors ("toomanyrequests").
- **Inferred**: The platform performs a registry manifest check during `az containerapp update` and rejects the request before creating a new revision record. No new revision appears in `az containerapp revision list`.
- **Not Proven**: Authentication failure (wrong ACR password) error message format was not tested in this experiment. H1 error text requires a separate test with invalid credentials.

## 12. What this proves

- A non-existent image tag is caught synchronously at the CLI level — no new revision is created. **Observed**.
- The error message `MANIFEST_UNKNOWN: manifest tagged by "..." is not found` is the specific format for a tag-not-found failure on MCR. **Observed**.
- Existing active revisions continue serving traffic uninterrupted when a new revision fails to deploy. **Observed** (H4 confirmed).
- The previous revision's traffic weight and health state are unchanged after a failed new-revision deployment. **Observed**.

## 13. What this does NOT prove

- Authentication failure error message format (ACR wrong password → "unauthorized") was not captured. A separate test with invalid credentials is needed.
- Docker Hub rate limit error format ("toomanyrequests") was not reproduced. That requires a Docker Hub image under a free account with high pull volume.
- Private registry network failure error format was not tested.
- Behavior when pulling an image that exists at the registry but the Container App's managed identity lacks the `AcrPull` role was not tested.

## 14. Support takeaway

When a customer reports "I updated the image but the new revision never appeared":

1. Check the CLI/portal error message during the update — if `MANIFEST_UNKNOWN`, the image tag does not exist at the registry. Verify the tag with `az acr repository show-tags` or `docker manifest inspect`.
2. If the update appears to succeed but no new revision is active, check `az containerapp revision list` and look for a revision in `Provisioning` or `Failed` state.
3. Key error string patterns to identify pull failure type:
   - `MANIFEST_UNKNOWN` → tag not found; check tag name spelling and registry source
   - `unauthorized` / `authentication required` → credential issue; rotate and redeploy
   - `toomanyrequests` → Docker Hub rate limit; switch to ACR mirror or use authenticated pull
   - `dial tcp: lookup ... no such host` → DNS resolution failure; check Private DNS Zone link
4. After any pull failure, the previous revision's traffic weight and health are preserved — the app stays up. A new revision must be explicitly deployed with a correct image to change the active revision.

## 15. Reproduction notes

```bash
RG="rg-lab-aca-batch"
APP="aca-diag-batch"

# S2: Deploy with non-existent tag (will fail)
az containerapp update -n $APP -g $RG \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:nonexistent-tag-99999"
# Expected: ERROR with MANIFEST_UNKNOWN

# Verify app still up
curl -s -o /dev/null -w "%{http_code}" \
  "https://aca-diag-batch.agreeablehill-e6bfb5a7.koreacentral.azurecontainerapps.io/"
# Expected: 200

# Check revisions unchanged
az containerapp revision list -n $APP -g $RG \
  --query "[].{name:name,active:properties.active,traffic:properties.trafficWeight}" -o table
```

- Docker Hub rate limits apply per egress IP. The Container Apps environment's shared egress IP may be rate-limited across all apps if they all pull from Docker Hub.
- ACR managed identity pull requires the `AcrPull` role on the registry assigned to the Container App's identity, not the environment.
- A failed new-revision pull does not deactivate the previous active revision; traffic continues on the old revision.

## 16. Related guide / official docs

- [Azure Container Registry authentication with managed identity](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication-managed-identity)
- [Use a private container registry in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers#use-an-image-from-a-private-registry)
- [Docker Hub rate limiting](https://docs.docker.com/docker-hub/download-rate-limit/)
- [Troubleshoot image pull failures in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-container-image-pull-failures)
