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

# Managed Identity Federated Credential vs. Service Principal

!!! warning "Status: Draft - Awaiting Execution"
    Cross-cutting experiment (App Service + Container Apps + Functions). Awaiting execution.

## 1. Question

In scenarios requiring cross-tenant or external IdP authentication (GitHub Actions, Kubernetes workload identity), when should federated credentials on a User-Assigned Managed Identity be used vs. a traditional Service Principal? How do the token acquisition flows differ, and what failure modes are specific to each approach?

## 2. Why this matters

Workload identity federation is increasingly the recommended approach for CI/CD pipelines and cross-tenant scenarios. However, the failure modes of federated credentials are less well-documented than traditional service principal + secret. Support cases arise when:
- The federated credential subject (issuer/subject claim) doesn't match exactly, causing token exchange to fail
- GitHub Actions workflows fail because the repo name or branch is case-sensitive in the subject claim
- The managed identity's federated credential is created but the Azure resource (App Service) can't use it for cross-tenant access
- Rotation patterns for federated credentials vs. client secrets are misunderstood

## 3. Customer symptom

- "Our GitHub Actions workflow can't authenticate to Azure even though federated credentials are set up."
- "The federation fails with 'Issuer/subject combination not found'."
- "We switched from service principal to managed identity federated credentials and everything broke."
- "How do we rotate federated credentials? There's no secret to rotate."

## 4. Hypothesis

**H1 — Subject claim is case-sensitive**: The `subject` field in the federated credential configuration is case-sensitive and must exactly match the claim sent by the external IdP. A mismatch on GitHub repo name capitalization causes token exchange to fail.

**H2 — Federated credentials don't expire**: Unlike service principal client secrets (which have an expiry), federated credentials don't expire. However, they can fail if the external IdP's issuer URL changes or if the target Azure resource's managed identity is deleted and recreated.

**H3 — App Service can't use federated credentials for outbound calls**: Federated credentials on a User-Assigned Managed Identity are used to establish trust for EXTERNAL systems authenticating AS the managed identity. App Service itself (for outbound calls to Azure services) still uses the IMDS token endpoint, not the federated credential flow.

**H4 — Federated credential token exchange is auditable**: The token exchange (external token → Azure token) appears in Microsoft Entra ID sign-in logs with a distinct `userPrincipalName` showing the workload identity. This is the diagnostic signal for federated credential failures.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Services | App Service, Functions, Container Apps (as deployment targets) |
| IdP | GitHub Actions (OIDC) |
| Region | Korea Central |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Identity + Auth

**Controlled:**

- Subject claim: correct, wrong case, missing wildcard
- Token validity: valid GitHub OIDC token vs. expired token
- Managed identity: correct target vs. wrong object ID

**Observed:**

- Token exchange success/failure and error message
- Microsoft Entra ID sign-in log entries
- GitHub Actions workflow failure messages
- Azure CLI / SDK error codes

## 7. Instrumentation

- GitHub Actions workflow with OIDC integration
- `az login --federated-token` step
- Microsoft Entra ID sign-in logs filtered by `Service Principal Name`

**Sign-in log query:**

```kusto
AADSignInLogs
| where AppDisplayName == "<app-name>"
| where AuthenticationProtocol == "oAuth2"
| project TimeGenerated, UserPrincipalName, ResultType, ResultDescription
| order by TimeGenerated desc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
# Create User-Assigned Managed Identity
az identity create --name mi-federated-test --resource-group rg-federated --location koreacentral

# Create federated credential for GitHub Actions
az identity federated-credential create \
  --identity-name mi-federated-test \
  --resource-group rg-federated \
  --name github-actions-prod \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:yeongseon/azure-paas-troubleshooting-labs:ref:refs/heads/main" \
  --audiences "api://AzureADTokenExchange"
```

### 8.2 Scenarios

**S1 — Correct federated credential**: GitHub Actions workflow with correct repo and branch. Verify token exchange succeeds.

**S2 — Wrong case in subject**: Change repo name to lowercase in the subject claim while the actual repo uses mixed case. Verify token exchange fails with specific error.

**S3 — Wrong branch**: Configure credential for `main` branch, run from `feature` branch. Verify rejection.

**S4 — Expired OIDC token**: Simulate stale token (not possible in real GitHub Actions, but can test with a manually crafted expired JWT). Verify rejection.

**S5 — Compare with service principal**: Same deployment task using service principal + secret. Compare failure modes, observability, and rotation requirements.

## 9. Expected signal

- **S1**: Token exchange succeeds. Azure resources accessible. Sign-in logs show workload identity entry.
- **S2**: Token exchange fails with `AADSTS70021: No matching federated identity record found for presented assertion`. Message includes issuer/subject mismatch details.
- **S3**: Same error as S2 — subject claim doesn't match.
- **S4**: Token exchange rejected with token expiry error.
- **S5**: SP + secret: no OIDC, simple client credentials flow. Rotation required every 1–2 years. Federated: no secret, no rotation, but more complex setup.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- GitHub Actions OIDC requires the repository to have Actions enabled and the workflow to request the `id-token` permission.
- The experiment requires a GitHub repository linked to the test Azure subscription.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Subject claim is case-sensitive | **Strongly Suggested** (consistent with JWT claim matching) |
| Federated credentials don't expire | **Strongly Suggested** (no expiry UI in portal) |
| Token exchange visible in Entra sign-in logs | **Inferred** |

## 14. Related experiments

- [Managed Identity Scope Mismatch (App Service)](../../app-service/managed-identity-scope-mismatch/overview.md) — identity RBAC scope errors
- [MI RBAC Propagation](../mi-rbac-propagation/overview.md) — role assignment delay

## 15. References

- [Workload identity federation for managed identities](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)
- [Configure GitHub Actions OIDC with Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure)
- [AADSTS error codes](https://learn.microsoft.com/en-us/entra/identity-platform/reference-error-codes)

## 16. Support takeaway

For federated credential failures:

1. `AADSTS70021` ("No matching federated identity record found") is the definitive error for subject/issuer mismatch. Check: (a) the `subject` in the federated credential exactly matches the GitHub workflow's `subject` claim, (b) the `issuer` URL matches exactly (GitHub OIDC uses `https://token.actions.githubusercontent.com`).
2. Subject claim format for GitHub Actions: `repo:<org>/<repo>:ref:refs/heads/<branch>` (or `:environment:<env>` for environment-specific). Case matters.
3. Federated credentials have no secret to rotate — but they can fail if the managed identity is deleted and recreated (new object ID, must update downstream RBAC).
4. The sign-in logs in Microsoft Entra ID show each token exchange attempt — use this to diagnose mismatches rather than relying solely on GitHub Actions error messages.
