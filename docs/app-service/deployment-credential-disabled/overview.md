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

# Deployment Credential Disabled: SCM and FTP Access Blocked

!!! info "Status: Planned"

## 1. Question

When App Service basic authentication (deployment credentials) is disabled at the subscription or resource level via Azure Policy or manual configuration, which deployment methods break, which still work, and how does the error message differ between methods?

## 2. Why this matters

Microsoft recommends disabling basic authentication (SCM and FTP basic auth) in favor of Entra ID-based deployment. However, many CI/CD pipelines and tools (FTP clients, WebDeploy, some GitHub Actions configurations) rely on the publish profile username/password. When basic auth is disabled — either intentionally via policy or accidentally via a security hardening runbook — these deployments fail with errors that do not clearly explain that basic authentication is disabled. Engineers waste time debugging pipeline configurations before identifying the root cause.

## 3. Customer symptom

"Our CI/CD pipeline suddenly can't deploy — it was working yesterday" or "FTP upload fails with 401 and I haven't changed any credentials" or "GitHub Actions deployment fails with an authentication error on zip deploy."

## 4. Hypothesis

- H1: When `basicPublishingCredentialsPolicies` is set to `Disabled` for the SCM site, Kudu-based deployments (zip deploy via `/api/zipdeploy`, WebDeploy, Git push) that use basic auth credentials fail with HTTP 401.
- H2: Deployment methods that use Entra ID authentication (service principal, managed identity via `az webapp deployment`) continue to work when basic auth is disabled — they do not depend on the publish profile credentials.
- H3: FTP and FTPS access is controlled by a separate `basicPublishingCredentialsPolicies` setting for the FTP endpoint. Disabling SCM basic auth does not affect FTP and vice versa.
- H4: The 401 error from a disabled SCM basic auth does not include a descriptive message explaining that basic auth is disabled. The portal shows the correct status under **Deployment Center > Settings > Authentication**.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Security

**Controlled:**

- App Service with basic auth enabled (baseline) and disabled (test)
- Deployment methods: zip deploy with publish profile, zip deploy with SPN, FTP, Kudu REST API

**Observed:**

- HTTP status code and error message for each deployment method under both configurations
- Which methods succeed when basic auth is disabled

**Scenarios:**

- S1: Basic auth enabled → all methods work (baseline)
- S2: Disable SCM basic auth → zip deploy with publish profile fails; SPN-based deploy still works
- S3: Disable FTP basic auth → FTP fails; SCM methods unaffected
- S4: Re-enable basic auth → all methods recover

## 7. Instrumentation

- HTTP response code from deployment API endpoint
- App Service **Deployment Center** portal UI status
- Azure Policy compliance report (if policy is managing the setting)
- Activity Log for `Microsoft.Web/sites/basicPublishingCredentialsPolicies/write` events

## 8. Procedure

_To be defined during execution._

### Sketch

1. S1: Confirm basic auth enabled; zip deploy using publish profile credentials → 200 OK.
2. S2: `az webapp update --set properties.publicNetworkAccess=Disabled` — no, use `az resource update` to set `basicPublishingCredentialsPolicies/scm` to `Disabled`; retry zip deploy with publish profile → 401; retry with SPN → success.
3. S3: Disable FTP basic auth; attempt FTPS upload with FTP credentials → 401; zip deploy via Kudu → still works.
4. S4: Re-enable both; verify all methods work again.

## 9. Expected signal

- S1: All deployment methods succeed.
- S2: Publish-profile zip deploy returns 401 with no descriptive message; SPN-based zip deploy returns 200.
- S3: FTPS returns 421/530 (FTP auth failure); Kudu zip deploy unaffected.
- S4: All methods succeed after re-enablement.

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

- Disable SCM basic auth: `az resource update --resource-type Microsoft.Web/sites/basicPublishingCredentialsPolicies --name scm --set properties.allow=false`
- Disable FTP basic auth: same command with `--name ftp`.
- Azure Policy built-in: "App Service apps should have basic authentication disabled for SCM site" (policy ID: `2c034a29-2a5f-4857-b120-f800fe5549ae`).
- SPN-based deployment: `az webapp deployment source config-zip --src app.zip` (uses Azure CLI credentials, not publish profile).

## 16. Related guide / official docs

- [Disable basic authentication in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-basic-auth-disable)
- [Deploy to App Service using GitHub Actions](https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions)
