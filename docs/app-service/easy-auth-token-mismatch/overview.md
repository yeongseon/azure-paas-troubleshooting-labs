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

# Easy Auth: Token Audience and Issuer Mismatch

!!! info "Status: Planned"

## 1. Question

When App Service Easy Auth (Built-in Authentication) is enabled, under what exact conditions does an incoming JWT token get rejected with 401, and how does audience or issuer mismatch differ from an expired token or a missing scope?

## 2. Why this matters

Easy Auth is a zero-code authentication layer that sits in front of the application. When it rejects a token, the application receives no request at all — there are no application-level logs and no stack traces. Engineers must diagnose the rejection entirely from the Easy Auth logs and token claims, which is non-obvious. Audience mismatch is the most common cause of silent 401s after an app registration change or when calling across tenants.

## 3. Customer symptom

"All API calls started returning 401 after we updated our Azure AD app registration" or "Authentication works for users but fails for our service principal" or "Easy Auth is rejecting tokens from our other app even though we added the permission."

## 4. Hypothesis

- H1: A token issued for audience `api://app-a` is rejected with 401 when Easy Auth is configured to validate audience `api://app-b`. The rejection occurs at the Easy Auth middleware layer; the app receives no request.
- H2: A token issued by a different AAD tenant issuer is rejected with 401 even if the audience matches, unless the app is configured for multi-tenant or the specific issuer is explicitly allowed.
- H3: An expired token (exp claim in the past) is rejected with 401 regardless of audience/issuer correctness.
- H4: Easy Auth rejection events are visible in App Service logs under `AppServiceAuthLogs` table in Log Analytics, not in `AppServiceConsoleLogs`.

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

**Experiment type**: Authentication / Configuration

**Controlled:**

- App Service with Easy Auth enabled (Microsoft identity platform provider)
- Entra ID app registration with a defined application ID URI (`api://correct-app`)
- Test tokens minted with various audience, issuer, and expiry values using `az account get-access-token` or a test JWT minting tool

**Observed:**

- HTTP response code for each token variant
- Log entry in `AppServiceAuthLogs`
- Presence or absence of `X-MS-CLIENT-PRINCIPAL` header on forwarded requests

**Scenarios:**

- S1: Token with correct audience and issuer, valid expiry → 200
- S2: Token with wrong audience (`api://wrong-app`) → 401
- S3: Token with correct audience but different tenant issuer → 401
- S4: Token with correct audience and issuer, expired → 401
- S5: Token with correct audience and issuer, missing required scope → behavior under Easy Auth scope validation

## 7. Instrumentation

- `AppServiceAuthLogs` in Log Analytics (requires diagnostic settings enabled)
- `curl -v` with `Authorization: Bearer <token>` to capture response headers
- `jwt.io` to decode and verify token claims before sending
- Activity Log for configuration changes

## 8. Procedure

_To be defined during execution._

### Sketch

1. Enable Easy Auth on App Service with Microsoft provider; configure the correct audience.
2. S1: Obtain a valid token for the correct app registration; send request; verify 200 and `X-MS-CLIENT-PRINCIPAL` header.
3. S2: Create a second app registration; obtain a token for that registration; send to the same endpoint; verify 401.
4. S3: If a second tenant is available, obtain a cross-tenant token; send; verify 401.
5. S4: Use a pre-expired token (manually crafted or wait for natural expiry); send; verify 401.
6. For each scenario, query `AppServiceAuthLogs` to capture the rejection reason field.

## 9. Expected signal

- S1: 200 with `X-MS-CLIENT-PRINCIPAL` header set and base64-decoded claims visible.
- S2–S4: 401 with no forwarded request to the app. `AppServiceAuthLogs` contains `AuthorizationFailed` or `TokenValidationFailed` with a reason string.
- S5: Behavior depends on whether Easy Auth scope validation is enabled; if not, the request may pass through with the token claims available to the app.

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

- Enable diagnostic settings on the App Service to route `AppServiceAuthLogs` to a Log Analytics workspace before testing.
- Easy Auth token validation settings are under **Authentication > Edit > Token store / Allowed token audiences**.
- The `aud` claim in the token must match one of the configured audiences exactly (case-sensitive).
- Use `az account get-access-token --resource <app-id-uri>` to obtain a token targeting a specific audience.

## 16. Related guide / official docs

- [Authentication and authorization in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization)
- [Configure your App Service app to use Microsoft Entra sign-in](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
- [AppServiceAuthLogs schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/appserviceauthlogs)
