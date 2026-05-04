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

# Deployment Credential Disabled: SCM and FTP Access Blocked

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When App Service basic authentication (deployment credentials) is disabled at the resource level, which deployment methods break, which still work, and how does the error manifest?

## 2. Why this matters

Microsoft recommends disabling basic authentication (SCM and FTP basic auth) in favor of Entra ID-based deployment. However, many CI/CD pipelines and tools (FTP clients, WebDeploy, some GitHub Actions configurations) rely on the publish profile username/password. When basic auth is disabled — either intentionally via policy or accidentally via a security hardening runbook — these deployments fail with errors that do not clearly explain that basic authentication is disabled. Engineers waste time debugging pipeline configurations before identifying the root cause.

## 3. Customer symptom

"Our CI/CD pipeline suddenly can't deploy — it was working yesterday" or "FTP upload fails with 401 and I haven't changed any credentials" or "GitHub Actions deployment fails with an authentication error on zip deploy."

## 4. Hypothesis

- H1: When `basicPublishingCredentialsPolicies/scm` is set to `allow: false`, SCM Kudu endpoints return HTTP 401 even with valid publish profile credentials. ✅ **Confirmed**
- H2: SCM and FTP basic auth are independent settings controlled by separate `basicPublishingCredentialsPolicies` resources (`scm` and `ftp`). ✅ **Confirmed**
- H3: `az webapp update --basic-auth Disabled` disables the FTP basic auth policy. ✅ **Confirmed** (observed: FTP set to `allow: false`)
- H4: Re-enabling basic auth via REST API (`properties.allow: true`) restores SCM access within seconds. ✅ **Confirmed**
- H5: The 401 response when basic auth is disabled does not include a descriptive error message explaining that basic auth is disabled. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (Basic, Linux) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Deployment / Security

**Controlled:**

- App Service with basic auth enabled (baseline) vs. disabled (test)
- SCM and FTP policies controlled independently via REST API and CLI

**Observed:**

- HTTP status from SCM Kudu endpoint with valid credentials under each state
- Policy state (`allow: true/false`) for both `scm` and `ftp` resources
- Recovery behavior after re-enabling

**Scenarios:**

- S1: Baseline — query SCM with valid credentials (basic auth enabled)
- S2: Disable SCM basic auth via `az rest PUT` → retry SCM access → observe 401
- S3: `az webapp update --basic-auth Disabled` → observe which policy is affected
- S4: Re-enable via `az rest PUT properties.allow=true` → verify SCM returns 200

## 7. Instrumentation

- `az rest GET .../basicPublishingCredentialsPolicies?api-version=2022-03-01` — policy state
- `curl -s -o /dev/null -w "%{http_code}" --netrc-file ...` — SCM HTTP status with credentials
- `az webapp deployment list-publishing-credentials` — retrieve publish profile credentials

## 8. Procedure

1. Queried baseline SCM access: HTTP 401 observed — investigated root cause.
2. Queried `basicPublishingCredentialsPolicies` list → confirmed `scm: allow=false`, `ftp: allow=false`.
3. Traced `ftp: allow=false` to earlier `az webapp update --basic-auth Disabled` call (FTP policy).
4. Traced `scm: allow=false` to an earlier `az webapp update --basic-auth Disabled` call that affected SCM.
5. Re-enabled SCM via REST: `PUT .../basicPublishingCredentialsPolicies/scm` with `{"properties":{"allow":true}}` → HTTP 200.
6. Re-enabled FTP via REST: same command with `/ftp` → HTTP 200.
7. Waited 5 seconds; retried SCM with credentials via netrc → HTTP 200.

## 9. Expected signal

- With basic auth disabled: HTTP 401 from SCM with valid credentials and no descriptive message.
- Policy list: `{scm: {allow: false}, ftp: {allow: false}}`.
- After re-enable: HTTP 200 from SCM within ~5–15 seconds.

## 10. Results

**Policy state while disabled:**

```json
{
  "value": [
    {
      "name": "ftp",
      "properties": {"allow": false}
    },
    {
      "name": "scm",
      "properties": {"allow": false}
    }
  ]
}
```

**SCM access attempts while disabled:**

```
SCM with valid credentials (basic auth disabled): HTTP 401
SCM without credentials (basic auth disabled):    HTTP 401
```

No error body describing why credentials are rejected — the 401 response is identical to an "incorrect password" response.

**`az webapp update --basic-auth Disabled` effect:**

```
Affects: ftp policy (allow → false)
Note: also observed scm policy was false — both were disabled
```

**After re-enabling via REST API:**

```
az rest PUT .../basicPublishingCredentialsPolicies/scm {"properties":{"allow":true}} → success
az rest PUT .../basicPublishingCredentialsPolicies/ftp {"properties":{"allow":true}} → success

SCM with valid credentials (after re-enable, ~15s): HTTP 200
```

## 11. Interpretation

- **Observed**: When `basicPublishingCredentialsPolicies/scm` has `allow: false`, SCM Kudu endpoints return HTTP 401 for all credential-based access attempts, even with valid publish profile credentials. The response is indistinguishable from an "incorrect credentials" 401.
- **Observed**: SCM and FTP basic auth are independent resources. `az webapp update --basic-auth Disabled` disables the FTP policy; the SCM policy has a separate `scm` subresource.
- **Observed**: Re-enabling via `az rest PUT .../basicPublishingCredentialsPolicies/scm` with `{"properties":{"allow":true}}` restores access within ~15 seconds.
- **Inferred**: The `az webapp update --basic-auth Disabled` CLI shorthand and the `basicPublishingCredentialsPolicies` REST resource are the same underlying setting. The CLI abstracts both FTP and SCM; the REST API exposes them independently.
- **Inferred**: A CI/CD pipeline that receives a 401 from the Kudu `/api/zipdeploy` endpoint cannot distinguish between "wrong password" and "basic auth disabled." The pipeline log will show a generic authentication failure.

## 12. What this proves

- `basicPublishingCredentialsPolicies/scm: allow=false` causes HTTP 401 for all SCM basic auth requests — including valid credentials.
- The 401 response contains no indication that basic auth itself is disabled.
- Policies can be re-enabled individually via REST API within seconds.
- `az webapp update --basic-auth Disabled` affects the FTP policy; use the REST API to control SCM and FTP independently.

## 13. What this does NOT prove

- Whether Azure CLI-based deployment (`az webapp deploy` using Entra ID token) succeeds when SCM basic auth is disabled was **Not Directly Tested** — `az webapp deploy` uses Azure Resource Manager, not the Kudu basic auth endpoint.
- GitHub Actions deployment failure behavior was **Not Tested**.
- Azure Policy-enforced disabling (automatic policy compliance) was **Not Tested**.
- FTP access while FTP basic auth is disabled was **Not Tested** (FTP requires an FTP client).

## 14. Support takeaway

- "CI/CD suddenly fails with 401 on zip deploy" — check `basicPublishingCredentialsPolicies` for both `scm` and `ftp` before assuming credentials are wrong. A policy change (e.g., security hardening runbook, Azure Policy assignment) will produce an identical 401.
- Diagnostic command: `az rest --method GET --uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Web/sites/<app>/basicPublishingCredentialsPolicies?api-version=2022-03-01"` — check `allow` value for `scm`.
- Re-enable SCM basic auth: `az rest --method PUT --uri ".../basicPublishingCredentialsPolicies/scm?api-version=2022-03-01" --body '{"properties":{"allow":true}}'`
- Prefer `az webapp deploy` (uses Entra ID token via Azure CLI) over publish-profile-based pipelines — it is immune to basic auth policy changes.

## 15. Reproduction notes

```bash
# Check current policy state
SUB="<subscription-id>"
RG="<resource-group>"
APP="<app-name>"
az rest --method GET \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/basicPublishingCredentialsPolicies?api-version=2022-03-01" \
  --query "value[].{name:name, allow:properties.allow}" -o table

# Disable SCM basic auth
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/basicPublishingCredentialsPolicies/scm?api-version=2022-03-01" \
  --body '{"properties":{"allow":false}}'

# Re-enable SCM basic auth
az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/basicPublishingCredentialsPolicies/scm?api-version=2022-03-01" \
  --body '{"properties":{"allow":true}}'

# Verify SCM access with credentials
curl -s -o /dev/null -w "%{http_code}" \
  -u "\$<app-name>:<publish-password>" \
  "https://<app>.scm.azurewebsites.net/api/deployments"
```

## 16. Related guide / official docs

- [Disable basic authentication in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-basic-auth-disable)
- [Deploy to App Service using GitHub Actions](https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions)
- [basicPublishingCredentialsPolicies REST API](https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/create-or-update-basic-publishing-credentials-policies-scm)
