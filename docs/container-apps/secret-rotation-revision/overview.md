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

# Secret Rotation and Revision Restart Behavior

!!! info "Status: Planned"

## 1. Question

When a secret referenced by a Container App is updated — either as an ACA-managed secret value, a Key Vault reference with a versioned URI, or a Key Vault reference with a versionless URI — does the running application pick up the new value automatically, and does the update trigger a revision restart?

## 2. Why this matters

Secret rotation is a routine security operation, but the propagation behavior in Container Apps differs significantly depending on how the secret is configured. ACA-managed secrets require an explicit restart. Key Vault references with versionless URIs may auto-refresh without a restart. Mixing these patterns in the same environment without understanding the propagation rules leads to incidents where a rotated credential continues to cause authentication failures because the running app has not picked up the new value — or conversely, an unexpected restart disrupts a production workload.

## 3. Customer symptom

"I rotated my database password but the app is still failing authentication" or "I updated the secret in Azure Container Apps but the running app is still using the old value" or "My app restarted unexpectedly after I updated a Key Vault secret."

## 4. Hypothesis

- H1: For ACA-managed secrets (plain value stored in Container Apps), updating the secret value does **not** propagate to running replicas automatically. The new value is only reflected after an explicit revision restart (`az containerapp revision restart`) or a new revision deployment.
- H2: For Key Vault references using a **versioned URI** (e.g., `https://<vault>.vault.azure.net/secrets/<name>/<version>`), updating Key Vault does not change the ACA secret reference. A new ACA secret version must be registered explicitly, and a revision restart is required to propagate it.
- H3: For Key Vault references using a **versionless URI** (e.g., `https://<vault>.vault.azure.net/secrets/<name>`), the platform polls Key Vault periodically and may auto-refresh the secret value. If the secret is referenced as an environment variable, the running revision may be restarted automatically when the new version is detected.
- H4: An application that reads secrets directly from Key Vault via the SDK at runtime (not via Container Apps secret injection) picks up the new Key Vault version on the next SDK call — only if the application does not cache the secret value. No Container Apps operation is required.

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

**Experiment type**: Configuration / Security

**Controlled:**

- Container App with three secret injection methods tested separately:
  1. ACA-managed secret as environment variable
  2. Key Vault reference with versioned URI as environment variable
  3. Key Vault reference with versionless URI as environment variable
- Separate test for runtime SDK access (no ACA injection)
- A debug endpoint (`GET /secret-value`) that returns the current value of the injected environment variable

**Observed:**

- Secret value returned by the debug endpoint before and after rotation
- Time between secret update and new value pickup (polling interval)
- Revision restart events triggered by secret propagation
- `ContainerAppSystemLogs` — restart and revision change events

**Scenarios:**

- S1: ACA-managed secret updated — no restart — observe pickup
- S2: ACA-managed secret updated — explicit `az containerapp revision restart` — observe timing
- S3: Key Vault versioned URI — new version created; ACA secret ref updated — observe pickup
- S4: Key Vault versionless URI — new version created in Key Vault — observe auto-refresh and any restart
- S5: Runtime SDK read — new version created in Key Vault — observe transparent pickup (no caching)

**Independent run definition**: One secret update event per scenario; observe for 30 minutes.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Debug endpoint (`GET /secret-value`) polling every 60 seconds — detects new value pickup
- `az containerapp revision list --name <app> --resource-group <rg>` — revision creation events
- `ContainerAppSystemLogs` KQL: `| where Reason contains "restart" or Reason contains "revision"` — restart events
- Key Vault audit logs (`AuditEvent`): `getSecret` operations — caller identity and version retrieved
- Time measurement: secret update timestamp → debug endpoint returns new value

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container App with ACA-managed secret as env var; record current value via debug endpoint.
2. S1: Update secret value via `az containerapp secret set`; poll debug endpoint every 60 seconds for 30 minutes; record if/when new value appears.
3. S2: Trigger `az containerapp revision restart`; poll until new value appears; record time and restart event.
4. S3: Deploy with versioned Key Vault URI; rotate Key Vault version; update ACA secret ref to new version; restart; verify propagation.
5. S4: Deploy with versionless Key Vault URI; rotate Key Vault version; observe debug endpoint and system logs for auto-refresh or restart.
6. S5: Deploy app that reads secret via Key Vault SDK at request time (no ACA injection); rotate Key Vault version; call debug endpoint immediately; verify transparent pickup.

## 9. Expected signal

- S1: Debug endpoint returns old value for the full observation window; no automatic pickup; no restart event.
- S2: New value appears within replica restart window (~60 seconds); one restart event in system log.
- S3: Value does not update until ACA secret ref is explicitly updated and restart triggered; Key Vault audit shows old version being read until restart.
- S4: Platform may auto-refresh the versionless URI and restart the revision within a platform-defined window; Key Vault audit log shows new version being retrieved.
- S5: Debug endpoint returns new Key Vault version on next call; no Container Apps restart required.

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

- ACA-managed secret updates do not create a new revision; they update the secret value in place. A revision restart cycles replicas without creating a new revision.
- Versionless Key Vault URI auto-refresh behavior may vary by platform version; document the Container Apps environment version during the test.
- For S5 (SDK access), ensure the application does not cache the secret (e.g., reads from Key Vault on every request); caching would make the result indistinguishable from S1.
- Key Vault audit logs capture the secret version retrieved on each `getSecret` call; use this to confirm which version the platform or app is reading at any given time.

## 16. Related guide / official docs

- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Use Key Vault references in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets#reference-secret-from-key-vault)
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
