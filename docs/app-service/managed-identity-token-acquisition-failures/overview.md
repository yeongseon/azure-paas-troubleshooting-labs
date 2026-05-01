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

# Managed Identity Token Acquisition Failures: IMDS, Caching, and RBAC Propagation Delay

!!! info "Status: Planned"

## 1. Question

When an App Service application acquires an access token via the Instance Metadata Service (IMDS) endpoint, what failure modes arise from transient IMDS unavailability, token cache TTL expiry during RBAC role removal, or RBAC role assignment propagation delay — and how do these failure modes appear in application logs versus Azure AD sign-in logs?

## 2. Why this matters

App Service managed identity token acquisition appears simple: call the IMDS endpoint, receive a token, use it. In practice, three distinct failure classes exist that surface as intermittent 401/403 errors indistinguishable at the application layer: (1) transient IMDS endpoint unavailability during platform operations, (2) stale cached tokens used after RBAC role removal, and (3) newly assigned roles not yet propagated when the application first acquires a token. Support engineers routinely misattribute these failures to application code or Key Vault/storage configuration rather than to the identity layer.

## 3. Customer symptom

"My app intermittently gets 401 errors calling Key Vault even though the managed identity has the right permissions" or "I just assigned the role and the app still fails — but only for the first few minutes" or "After a slot swap, the app suddenly can't authenticate to Storage."

## 4. Hypothesis

- H1: A newly assigned RBAC role for a managed identity does not take effect immediately. There is a propagation delay (typically 1–5 minutes) during which the identity's token is valid but the role assignment is not yet visible to the target resource. Applications that acquire a token immediately after role assignment and cache it may succeed or fail depending on when the token is first used relative to propagation completion.
- H2: When IMDS is transiently unavailable (e.g., during a platform update or instance migration), the IMDS endpoint (`http://169.254.169.254/metadata/instance`) returns a connection timeout rather than an HTTP error code. Application SDKs that do not retry on IMDS timeouts will surface this as an `CredentialUnavailableException` or equivalent, which looks identical to a misconfigured identity.
- H3: After an RBAC role is removed from a managed identity, the identity's previously acquired token remains valid until it expires (typically 60–90 minutes). Applications using cached tokens continue to succeed against the target resource for the remainder of the token's lifetime, then begin to fail. This delayed failure window causes confusion about the timing of the permission change.
- H4: After a deployment slot swap, the system-assigned managed identity of the swapped app does not change — but if the application cached the IMDS endpoint URL or a token bound to the pre-swap hostname, token acquisition may fail until the cache is invalidated.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Security / Identity

**Controlled:**

- App Service with system-assigned managed identity
- Target resource: Azure Key Vault (secret read) and Azure Storage (blob read)
- Application: Python FastAPI with Azure SDK (`azure-identity`, `azure-keyvault-secrets`)
- Token acquisition: `DefaultAzureCredential` with IMDS path

**Observed:**

- Token acquisition success/failure per request (application log)
- Azure AD sign-in log: managed identity credential event, success/failure, token issued time
- Time from RBAC role assignment to first successful token use
- Time from RBAC role removal to first failure (token expiry window)
- IMDS response during simulated unavailability (connection timeout vs HTTP error)

**Scenarios:**

- S1: Role assigned → immediate token acquisition → measure propagation delay to first success
- S2: Role removed → monitor time until cached token expires and requests begin failing
- S3: Simulate IMDS unavailability by blocking `169.254.169.254` via `iptables` → observe error type and SDK behavior
- S4: Slot swap with cached token → verify token reuse across swap

**Independent run definition**: One role assignment/removal event per scenario; observe for 10 minutes.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Application log: token acquisition timestamp, success/failure, exception type
- Azure AD sign-in log (Log Analytics): `AADManagedIdentitySignInLogs | where ResourceId contains "<app-name>"`
- Key Vault diagnostic log: `AzureDiagnostics | where OperationName == "SecretGet"` — caller identity and result
- IMDS response time: `curl -w "%{time_total}" http://169.254.169.254/metadata/identity/oauth2/token?...`
- `iptables -A OUTPUT -d 169.254.169.254 -j DROP` — IMDS block for S3
- Time measurement: `az role assignment create` timestamp → first successful Key Vault call

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy App Service with managed identity; verify Key Vault access works at baseline.
2. S1: Remove the Key Vault role; re-assign it; immediately start polling the Key Vault endpoint every 5 seconds; record the first success timestamp relative to role assignment time.
3. S2: Remove the Key Vault role; continue polling; record how long the cached token sustains successful calls before failure begins.
4. S3: Block IMDS via `iptables`; trigger token acquisition; record exception type and stack trace; unblock and measure recovery time.
5. S4: Swap staging slot (with warm app, cached token) to production; immediately poll Key Vault; check for transient failures.

## 9. Expected signal

- S1: First successful Key Vault call arrives 1–5 minutes after role assignment; requests during propagation window return 403.
- S2: Key Vault calls succeed for up to 60–90 minutes after role removal (token lifetime); failure onset correlates with token expiry, not with role removal timestamp.
- S3: IMDS block produces a connection timeout, not an HTTP error; SDK surfaces `CredentialUnavailableException`; recovery is automatic after unblocking without app restart.
- S4: Slot swap does not invalidate the managed identity; token reuse across swap succeeds without re-acquisition.

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

- RBAC propagation delay is a platform behavior, not a bug; the documented SLA for role assignment propagation is up to 5 minutes globally, but can be shorter within a single region.
- Token cache TTL for `DefaultAzureCredential` defaults to 5 minutes before refresh; the underlying access token from Azure AD has a 60–90 minute lifetime. These are two distinct caches.
- `iptables` modifications on App Service Linux containers may not persist across restarts; validate the block is active before starting the IMDS scenario.
- Azure AD sign-in logs for managed identities are available in the `AADManagedIdentitySignInLogs` table in Log Analytics; they require the workspace to be linked to the Microsoft Entra tenant.

## 16. Related guide / official docs

- [How to use managed identities for App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity)
- [Azure Instance Metadata Service — identity endpoint](https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service)
- [Troubleshoot managed identity token acquisition](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/known-issues)
- [Azure RBAC — role assignment propagation](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting)
