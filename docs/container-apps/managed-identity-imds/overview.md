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

# Managed Identity Token Acquisition in Container Apps: IMDS, Federated Identity, and Network Restrictions

!!! info "Status: Planned"

## 1. Question

When a Container App uses managed identity to acquire tokens via the IMDS-compatible endpoint, what failure modes arise from network restrictions blocking the endpoint, from federated identity misconfiguration, or from token cache behavior across replica restarts — and how do these failures surface in application logs versus platform logs?

## 2. Why this matters

Container Apps support both system-assigned and user-assigned managed identities. Token acquisition uses a local endpoint (`http://169.254.169.254` or the `IDENTITY_ENDPOINT` environment variable) that is injected by the platform. Unlike App Service, Container Apps environments can have custom network configurations that inadvertently block the identity endpoint. Federated workload identity (used for Kubernetes-style scenarios) adds an additional layer with audience and subject claim requirements. Failures in any of these layers appear as generic 401/403 errors from downstream services, not as identity endpoint errors.

## 3. Customer symptom

"My container gets 401 from Key Vault even though I assigned the managed identity" or "The identity works in one revision but fails after redeployment" or "I'm using workload identity federation but the token keeps getting rejected."

## 4. Hypothesis

- H1: The managed identity token endpoint in Container Apps is exposed via the `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` environment variables, not via the standard IMDS IP `169.254.169.254`. SDKs that hardcode the IMDS IP (rather than reading `IDENTITY_ENDPOINT`) will fail to acquire tokens in Container Apps, even with a correctly configured identity.
- H2: If the Container Apps environment has custom DNS or network policies that inadvertently block the `IDENTITY_ENDPOINT` host, token acquisition fails with a connection timeout. The error is indistinguishable at the application layer from a misconfigured identity; the `IDENTITY_ENDPOINT` URL must be tested separately.
- H3: Tokens acquired by a replica are cached in the Azure SDK's credential chain. When a replica restarts, the in-memory token cache is cleared. The first request after restart triggers a fresh token acquisition. If the identity endpoint is slow or temporarily unavailable at restart time, the first request fails with a credential error.
- H4: For user-assigned managed identity, the application must explicitly specify the `client_id` of the identity when using `ManagedIdentityCredential`. If multiple user-assigned identities are attached to the Container App and the `client_id` is omitted, the SDK may pick an unexpected identity or fail with an ambiguity error.

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

**Experiment type**: Security / Identity

**Controlled:**

- Container App with system-assigned managed identity
- Container App with two user-assigned managed identities
- Target resource: Azure Key Vault (secret read)
- Azure SDK: `azure-identity` (`ManagedIdentityCredential`, `DefaultAzureCredential`)

**Observed:**

- `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` values in the container environment
- Token acquisition success/failure per SDK call
- Error type: connection timeout vs. HTTP 4xx vs. credential ambiguity
- Time from replica restart to first successful token acquisition

**Scenarios:**

- S1: System-assigned identity with `DefaultAzureCredential` — baseline token acquisition
- S2: Hardcoded IMDS IP (`169.254.169.254`) instead of `IDENTITY_ENDPOINT` — observe failure
- S3: Two user-assigned identities, `client_id` omitted — observe SDK behavior
- S4: Two user-assigned identities, correct `client_id` specified — confirm correct identity used
- S5: Replica restart — measure time to first successful token acquisition

**Independent run definition**: One token acquisition attempt per scenario; S5 uses 10 restarts.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Container env dump: `env | grep IDENTITY` — confirm `IDENTITY_ENDPOINT` and `IDENTITY_HEADER` are present
- `curl "$IDENTITY_ENDPOINT?resource=https://vault.azure.net&api-version=2019-08-01" -H "X-IDENTITY-HEADER: $IDENTITY_HEADER"` — direct token endpoint test
- Application log: token acquisition timestamp, credential type, client_id used, success/failure
- Azure AD sign-in log: `AADManagedIdentitySignInLogs | where AppId == "<client_id>"` — token issuance events
- Key Vault diagnostic log: `AzureDiagnostics | where OperationName == "SecretGet"` — caller identity

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container App with system-assigned identity; confirm `IDENTITY_ENDPOINT` is set; acquire Key Vault token via SDK (S1).
2. S2: Modify app to use hardcoded `169.254.169.254` IMDS URL; observe failure; confirm `IDENTITY_ENDPOINT` is the correct address in Container Apps.
3. S3: Attach two user-assigned identities; deploy app with `ManagedIdentityCredential()` (no `client_id`); observe SDK behavior (error or arbitrary identity selection).
4. S4: Specify correct `client_id`; confirm correct identity is used via Azure AD sign-in log.
5. S5: Trigger 10 replica restarts (`az containerapp revision restart`); log time from restart to first successful Key Vault call.

## 9. Expected signal

- S1: Token acquired successfully via `IDENTITY_ENDPOINT`; Key Vault call succeeds.
- S2: `169.254.169.254` connection times out; SDK raises `CredentialUnavailableException`; error message does not reference `IDENTITY_ENDPOINT`.
- S3: SDK raises an error about multiple user-assigned identities requiring explicit `client_id`, or silently picks one — behavior depends on SDK version.
- S4: Correct user-assigned identity used; Key Vault audit log shows expected `client_id`.
- S5: First token acquisition after restart adds measurable latency (~500ms–2s); no persistent failures across restarts.

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

- In Container Apps, the managed identity endpoint is exposed via `IDENTITY_ENDPOINT` (not the standard IMDS IP). Azure SDKs using `ManagedIdentityCredential` read this variable automatically; code that hardcodes `169.254.169.254` will fail.
- `IDENTITY_HEADER` must be passed as the `X-IDENTITY-HEADER` HTTP header in direct calls to `IDENTITY_ENDPOINT`; omitting this header returns a 403.
- When multiple user-assigned identities are attached, always specify the `client_id` explicitly in the credential constructor to avoid ambiguity.
- Azure AD sign-in logs for managed identities in Container Apps may show the system-assigned identity's `objectId` rather than a named identity; correlate using the `AppId` (client ID) field.

## 16. Related guide / official docs

- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Azure SDK managed identity credential — Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity?tabs=portal%2Cpython#connect-to-azure-services-in-app-code)
- [Troubleshoot managed identity token acquisition](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/known-issues)
