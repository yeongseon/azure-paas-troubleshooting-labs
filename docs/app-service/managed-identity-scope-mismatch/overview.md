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

# Managed Identity Scope Mismatch

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When an App Service managed identity is assigned to a resource with an overly broad or mismatched scope (wrong resource, wrong subscription, wrong tenant), how does the failure manifest? Does the token acquisition fail at the identity level, or does it succeed with a token that fails at the resource authorization level?

## 2. Why this matters

Managed identity is the recommended authentication pattern for App Service to Azure services. However, scope misconfiguration is one of the most common errors support engineers encounter:
- Role assigned to the wrong resource (different storage account, different Key Vault)
- Role assigned at resource group level when service-level assignment was intended
- Using a user-assigned identity when the code reads the system-assigned identity token
- Multi-tenant scenarios where the identity exists in a different tenant from the resource

The failure messages for these cases are often confusing because the error occurs at different layers (IMDS token acquisition vs. service authorization).

## 3. Customer symptom

- "We assigned the Contributor role but managed identity still doesn't work."
- "The managed identity can access the storage account but not the Key Vault."
- "We're getting 403 when accessing Storage but the role assignment is there."
- "The token is acquired successfully but Key Vault returns Forbidden."

## 4. Hypothesis

**H1 — Token acquisition always succeeds (when identity exists)**: IMDS token acquisition for a managed identity succeeds regardless of whether the identity has been granted any RBAC roles. The token contains claims for the identity, not claims for specific resource access.

**H2 — Authorization fails at the resource**: Scope mismatch (wrong resource, wrong role) is not visible until the token is used against the target resource. The resource returns 403 Forbidden with a message that may or may not indicate the specific misconfiguration.

**H3 — Wrong identity selected with multiple identities**: When both system-assigned and user-assigned identities are attached, token requests without specifying `client_id` return the system-assigned identity token. If the RBAC role is on the user-assigned identity, the request will fail at authorization.

**H4 — Cross-tenant identity fails at IMDS**: A user-assigned managed identity from a different tenant cannot be attached to an App Service. The IMDS endpoint will not return a token for cross-tenant identities.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Linux |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Identity + Authorization

**Controlled:**

- Identity type: system-assigned, user-assigned, both
- Role assignment: correct resource, wrong resource, no role
- Target service: Azure Storage, Key Vault
- `client_id` parameter in token request: specified vs. omitted

**Observed:**

- IMDS token acquisition success/failure
- HTTP status code from target resource
- Error message text from target resource (for diagnosability assessment)
- Token claims (decoded JWT) for each scenario

## 7. Instrumentation

- Python endpoint: `GET /identity-test?resource=<storage|keyvault>&client_id=<optional>`
- Uses `azure-identity` DefaultAzureCredential with explicit `managed_identity_client_id`
- Decodes and returns token claims (audience, oid, appid) for diagnostics
- Captures both the identity acquisition step and the resource access step separately

**Token claim inspection:**

```python
import base64, json

def decode_token(token):
    payload = token.split('.')[1]
    padded = payload + '=' * (4 - len(payload) % 4)
    return json.loads(base64.b64decode(padded))
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
# Create test resources
az keyvault create --name kv-mi-scope-test --resource-group rg-mi-scope --location koreacentral
az storage account create --name samiscopetest --resource-group rg-mi-scope --location koreacentral

# Assign system-assigned identity
az webapp identity assign --name app-mi-scope --resource-group rg-mi-scope

# Intentionally assign role to wrong resource (storage, not keyvault)
PRINCIPAL_ID=$(az webapp identity show --name app-mi-scope --resource-group rg-mi-scope --query principalId -o tsv)
az role assignment create --assignee $PRINCIPAL_ID \
  --role "Storage Blob Data Reader" \
  --scope $(az storage account show --name samiscopetest --query id -o tsv)
# Note: NOT assigning Key Vault role
```

### 8.2 Scenarios

**S1 — No role, token still acquired**: App has no RBAC roles. Acquire token. Verify token contains identity claims. Attempt Key Vault access. Document 403 error message.

**S2 — Wrong resource role**: Storage role assigned, Key Vault access attempted. Verify token acquired. Verify 403 on Key Vault. Compare error message specificity.

**S3 — Two identities, no client_id**: Attach both system-assigned and user-assigned identities. Grant Key Vault role to user-assigned only. Attempt access without `client_id`. Document failure mode.

**S4 — Two identities, correct client_id**: Same setup, but specify `client_id` matching user-assigned identity. Verify success.

**S5 — Token decode**: For each scenario, decode the JWT and document which claims differ (audience, oid, appid).

## 9. Expected signal

- **S1**: Token acquired (IMDS returns 200). Key Vault returns 403 with `Caller is not authorized to perform action on resource`.
- **S2**: Same — token acquired, Key Vault 403.
- **S3**: Token acquired for system-assigned identity. Key Vault 403 because system-assigned has no role.
- **S4**: Token acquired for user-assigned identity (`client_id` specified). Key Vault 200 OK.
- **S5**: Token `oid` differs between system and user-assigned. `aud` (audience) matches the target service in all cases.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- RBAC role assignment propagation takes up to 5 minutes — test must wait for propagation before measuring.
- Key Vault access also depends on Key Vault access policies vs. RBAC model (Azure RBAC for Key Vault must be enabled).

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| IMDS token acquisition succeeds regardless of RBAC | **Strongly Suggested** |
| Resource returns 403 (not 401) on scope mismatch | **Inferred** |
| Multiple identity ambiguity causes wrong token | **Strongly Suggested** |

## 14. Related experiments

- [Managed Identity Token Acquisition Failures](../zip-vs-container/overview.md) — IMDS failure modes
- [Key Vault Certificate Binding](../zip-vs-container/overview.md) — Key Vault specific access patterns
- [Key Vault Reference Resolution](../zip-vs-container/overview.md) — App setting KV references

## 15. References

- [Managed identity for App Service](https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity)
- [Azure RBAC for Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide)

## 16. Support takeaway

For managed identity authorization failures:

1. Separate the diagnosis into two steps: (a) can the identity acquire a token? (b) does the resource accept the token? Token acquisition failure and resource authorization failure have different root causes.
2. Use `GET /metadata/identity/oauth2/token?resource=https://vault.azure.net&api-version=2018-02-01` from Kudu to verify token acquisition independently.
3. With multiple identities (system + user-assigned), always specify `client_id` in SDK calls. DefaultAzureCredential without `managed_identity_client_id` uses the system-assigned identity.
4. The most diagnostic piece of information is the `oid` claim in the JWT and the `principalId` in the RBAC role assignment — verify they match.
5. RBAC propagation takes 1–5 minutes after `az role assignment create`. Rule out timing before deeper investigation.
