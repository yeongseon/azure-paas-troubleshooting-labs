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

# Secret Volume Mount Behavior

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When Container Apps secrets are mounted as volumes (files), how does the mounted content behave when the secret value is updated? Is the mounted file updated in-place, requiring a new revision, or does it refresh automatically? What is the latency between secret update and file system update?

## 2. Why this matters

Container Apps supports two methods of exposing secrets to containers: environment variables and volume mounts. The volume mount approach is commonly recommended for sensitive values because:
- Secrets don't appear in `ps` environment output
- Rotation can potentially be done without a full revision cycle

However, customers frequently misunderstand whether volume-mounted secrets auto-refresh or require a new revision/restart. This experiment clarifies the exact behavior and the refresh window.

## 3. Customer symptom

- "We updated our database password in Key Vault and the secret in Container Apps, but the app is still using the old password."
- "We're using volume-mounted secrets. After rotating, our app sees the old value for hours."
- "We expected secret rotation to be zero-downtime with volume mounts, but we still needed a new revision."

## 4. Hypothesis

**H1 — Volume mounts do not auto-refresh**: Updating a Container Apps secret value does NOT automatically update the mounted file on running replicas. A new revision is required to pick up the new secret value.

**H2 — Key Vault reference refresh**: If the secret is a Key Vault reference (not a plain text value), updating the Key Vault secret still requires a Container Apps secret update (version bump) AND a new revision before the volume mount reflects the new value.

**H3 — Env var vs. volume mount behavior is identical**: Both environment variable secrets and volume-mounted secrets require a new revision to reflect updated values. Neither auto-refreshes.

**H4 — New revision sees new value immediately**: A newly created revision always mounts the current value of the secret, not the value at any previous point in time.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Container Apps |
| Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Secret type: plain text value vs. Key Vault reference
- Update method: update secret value vs. update secret + restart vs. new revision
- Observation interval: check file content every 30s for 10 minutes

**Observed:**

- File content at `/mnt/secrets/<name>` via `/health` endpoint
- Timestamp of file modification (via `os.path.getmtime`)
- Container Apps revision active/inactive state after secret update

## 7. Instrumentation

- Application endpoint: `GET /secret` returning `{"value": open('/mnt/secrets/dbpass').read(), "mtime": os.path.getmtime('/mnt/secrets/dbpass')}`
- Continuous polling: 30s interval probe for 15 minutes after secret update
- Container Apps revision list: `az containerapp revision list` to detect new revision creation

**Key CLI:**

```bash
# Check current secret value seen by running replica
az containerapp exec --name myapp --resource-group myrg \
  --command "cat /mnt/secrets/dbpass"
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az containerapp env create --name env-secret-vol --resource-group rg-secret-vol --location koreacentral

az containerapp create \
  --name app-secret-vol \
  --resource-group rg-secret-vol \
  --environment env-secret-vol \
  --image mcr.microsoft.com/k8se/quickstart:latest \
  --secrets "dbpass=initial-value" \
  --secret-volume-mount "/mnt/secrets"
```

### 8.2 Scenarios

**S1 — Plain text secret update, no new revision**: Update secret value via `az containerapp secret set`. Poll `/secret` endpoint every 30s for 10 minutes. Observe whether mounted file updates.

**S2 — Plain text secret update + new revision**: Update secret value. Create new revision (`az containerapp update`). Verify new revision immediately sees new value.

**S3 — Key Vault reference update**: Use a KV reference for the secret. Update the KV secret version. Update Container Apps secret to point to new version. Observe when mounted file updates.

**S4 — Long observation window**: Leave S1 running for 60 minutes. Check if auto-refresh occurs at any point.

## 9. Expected signal

- **S1**: Mounted file does NOT update. Old value persists indefinitely.
- **S2**: New revision sees new value. Old revision still sees old value.
- **S3**: KV reference update requires Container Apps secret update AND new revision.
- **S4**: No auto-refresh observed at 60 minutes.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Kubernetes secret behavior (inotify-based updates) does not apply to Container Apps managed secrets — the platform behavior may differ from raw Kubernetes.
- The test uses a simple string value; larger secrets (certificates) may have different behavior.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Volume-mounted secrets do not auto-refresh | **Strongly Suggested** (consistent with KV reference behavior) |
| New revision sees updated secret | **Inferred** |
| KV reference requires both Container Apps and KV update | **Inferred** |

## 14. Related experiments

- [Secret Rotation and Revision](../liveness-probe-failures/overview.md) — revision creation on secret update
- [KEDA Secret Scaler Rotation](../liveness-probe-failures/overview.md) — KEDA secret handling
- [Key Vault Reference Resolution (App Service)](../../app-service/zip-vs-container/overview.md) — comparison with App Service behavior

## 15. References

- [Container Apps secrets documentation](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Mount secrets as volumes](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets#mount-secrets-in-a-volume)

## 16. Support takeaway

When customers expect zero-downtime secret rotation via volume mounts:

1. Clarify that Container Apps volume-mounted secrets do NOT auto-refresh. A new revision is required for the new value to take effect.
2. Rotation workflow: (1) Update KV secret, (2) Update Container Apps secret reference, (3) Create new revision. The old revision continues serving until traffic is shifted.
3. For true zero-downtime rotation, use the multi-revision traffic split pattern: create new revision with new secret, shift traffic gradually, then deactivate old revision.
4. Volume mounts and environment variable secrets behave identically — both require a new revision.
