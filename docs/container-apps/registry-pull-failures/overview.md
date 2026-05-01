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

# Container Registry Pull Failures: Authentication, Rate Limiting, and Private Registry Access

!!! info "Status: Planned"

## 1. Question

When a Container App fails to pull its container image — due to an incorrect registry credential, an expired managed identity token for a private ACR, or a Docker Hub rate limit — how does the failure manifest in system logs and replica provisioning events, and how does the error message differ across failure types?

## 2. Why this matters

Container image pull failures are a top cause of Container App deployment failures, but the error messages are inconsistent. An authentication failure against ACR, a rate limit from Docker Hub, and a network-level failure reaching a private registry all produce provisioning failures that look similar in the Azure portal ("Container failed to start"). The `ContainerAppSystemLogs` entries for each failure type differ in the `Message` field, but support engineers must know which patterns to look for to distinguish them. Image pull failures are also silent when the previous revision is still running — the new revision silently stays unprovisioned.

## 3. Customer symptom

"I deployed a new revision but it never became active" or "My Container App used to pull from Docker Hub but now it fails intermittently" or "I updated my ACR credential but the app still can't pull the image."

## 4. Hypothesis

- H1: When ACR authentication fails (wrong password, expired service principal, revoked managed identity role), the replica provisioning fails with a message in `ContainerAppSystemLogs` that includes "unauthorized" or "authentication required". The previous revision continues serving traffic if traffic splitting is configured; if there is no previous active revision, the app returns 503.
- H2: Docker Hub rate limiting (429 Too Many Requests) produces a distinct error in `ContainerAppSystemLogs` compared to an authentication failure (401). The rate limit error appears as a pull failure with "toomanyrequests" in the message. The rate limit applies per source IP — the Container Apps environment's egress IP — and may affect all apps in the environment simultaneously.
- H3: When pulling from a private registry over a Private Endpoint without proper DNS or network configuration, the pull fails with a network timeout, not an authentication error. The system log message contains "connection refused" or "dial tcp: lookup" rather than "unauthorized".
- H4: After updating an ACR admin password or managed identity role assignment, the Container App does not automatically re-pull. A new revision deployment is required to trigger a fresh pull with the new credentials.

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

**Experiment type**: Reliability / Configuration

**Controlled:**

- Container App configured to pull from: (a) Azure Container Registry with admin credentials, (b) Azure Container Registry with managed identity, (c) Docker Hub public image
- Registry authentication methods: admin password, expired password, managed identity with/without role

**Observed:**

- `ContainerAppSystemLogs` Reason and Message fields per failure type
- Replica provisioning state (Waiting, Failed, Running)
- Time from revision deployment to failure event in system log
- Traffic behavior: does the previous revision continue serving during a failed new-revision pull?

**Scenarios:**

- S1: ACR with correct admin password — baseline pull success
- S2: ACR with incorrect admin password — authentication failure
- S3: ACR with managed identity — correct role assigned — success
- S4: ACR with managed identity — role removed — failure after cached token expires
- S5: Docker Hub public image — rate limit triggered by pulling repeatedly
- S6: Private ACR behind Private Endpoint — DNS misconfigured (no zone link) — network failure

**Independent run definition**: One revision deployment per scenario; observe system logs for 10 minutes.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `ContainerAppSystemLogs` KQL: `| where Reason contains "Pull" or Reason contains "Image" or Message contains "unauthorized" or Message contains "toomanyrequests"` — pull failure events
- `az containerapp revision show --query "properties.replicas[].runningState"` — replica state
- `az containerapp revision list --query "[].{name:name, active:properties.active, replicas:properties.replicas}"` — active revision state
- Docker Hub rate limit header: inspect pull response headers for `X-RateLimit-Remaining`
- ACR login test: `az acr login --name <acr>` from a local machine to confirm credential validity before deploying

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container App pulling from ACR with correct admin credentials (S1); confirm replica running.
2. S2: Update registry credential with wrong password; deploy new revision; monitor `ContainerAppSystemLogs` for pull failure message; note exact Reason and Message.
3. S3/S4: Switch to managed identity pull; confirm success; remove ACR pull role; deploy new revision; observe failure after token expiry.
4. S5: Use Docker Hub public image; trigger repeated pulls by deploying many revisions in rapid succession; observe rate limit message in system log.
5. S6: Configure private ACR with Private Endpoint but omit DNS zone link; deploy revision; observe network error message vs. S2 authentication error message.
6. For each failure: note exact `ContainerAppSystemLogs` `Reason` and `Message` fields; compare across scenarios.

## 9. Expected signal

- S2: System log shows `Reason: Failed`, `Message: "unauthorized: authentication required"` or similar; previous revision continues serving if active.
- S4: Pull failure appears after managed identity token used for pull expires (~60–90 min after role removal); system log message differs from S2 (may include "denied" rather than "unauthorized").
- S5: System log shows `Message: "toomanyrequests: Too Many Requests."` with Docker Hub rate limit indication; multiple apps in the environment may fail simultaneously.
- S6: System log shows a network-level error (`dial tcp: lookup <acr>.azurecr.io: no such host` or connection refused); distinguishable from authentication failure by the absence of "unauthorized".

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

- Docker Hub rate limits apply per source IP; the Container Apps environment's egress IP (shared across all apps in the environment) is the rate-limited entity. Pull rate limits are 100 pulls/6 hours for unauthenticated requests and 200/6 hours for authenticated free accounts.
- ACR managed identity pull requires the `AcrPull` role on the registry. The role must be assigned to the Container App's managed identity (system-assigned or user-assigned), not to the Container Apps environment.
- Private ACR with Private Endpoint requires a Private DNS Zone (`privatelink.azurecr.io`) linked to the Container Apps environment's VNet for DNS resolution to succeed.
- A failed new-revision pull does not deactivate the previous active revision; traffic continues on the old revision until the new revision is explicitly activated.

## 16. Related guide / official docs

- [Azure Container Registry authentication with managed identity](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication-managed-identity)
- [Use a private container registry in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers#use-an-image-from-a-private-registry)
- [Docker Hub rate limiting](https://docs.docker.com/docker-hub/download-rate-limit/)
- [Troubleshoot image pull failures in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-container-image-pull-failures)
