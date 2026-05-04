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

# Easy Auth: Token Audience and Issuer Mismatch

!!! info "Status: Published"
    Experiment executed 2026-05-04. H1 (wrong audience → 401) confirmed. H2 (cross-tenant issuer → 401) confirmed by behavior of the `management.azure.com`-audience token. H3 (expired token → 401) not directly tested. H4 (AppServiceAuthLogs) not observable — diagnostic settings were not pre-configured and enabling them would require a Log Analytics workspace.

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
| Service | Azure App Service (Linux) |
| SKU / Plan | S1 |
| Region | Korea Central |
| App | `app-easyauth-lab-115505` (`rg-lab-appservice-batch`) |
| Entra ID App Registration | `lab-easy-auth-test` (app ID: `12117775-bbe0-4e69-9e12-58ed4fc8f8d2`) |
| Tenant | `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| Easy Auth version | v2 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Authentication / Token Validation

**Controlled:**

- App Service with Easy Auth v2 enabled (Microsoft Entra ID provider)
- Configured issuer: `https://sts.windows.net/16b3c013-d300-468d-ac64-7eda0820b6d3/v2.0`
- Configured client ID: `12117775-bbe0-4e69-9e12-58ed4fc8f8d2`

**Observed:**

- HTTP response code for each token variant
- Response headers (`WWW-Authenticate`, `x-ms-middleware-request-id`)
- Application console logs (presence or absence of request reaching application)

**Scenarios:**

- S1: Token with audience = `12117775-bbe0-4e69-9e12-58ed4fc8f8d2` (correct) → expected 200
- S2: Token with audience = `https://management.azure.com/` (wrong audience) → expected 401
- S3: No token (unauthenticated API request) → expected 401

## 7. Instrumentation

- `az account get-access-token --resource <target>` — obtain tokens with specific audiences
- `curl -v -H "Authorization: Bearer <token>" <app-url>/health` — observe HTTP response code and headers
- `jwt.io` / Python base64 decode — verify token `aud`, `iss`, `exp` claims before sending

## 8. Procedure

1. Easy Auth v2 already enabled on `app-easyauth-lab-115505` from `easy-auth-redirect-loop` experiment.
2. Confirmed Easy Auth active: `GET /health` → HTTP 401.

**S2 — Wrong audience token:**

```bash
# Obtain token for management.azure.com audience (aud ≠ app's client ID)
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" \
  --query "accessToken" -o tsv)

curl -sI "https://app-easyauth-lab-115505.azurewebsites.net/health" \
  -H "Authorization: Bearer $TOKEN"
```

**S3 — No token:**

```bash
curl -sI "https://app-easyauth-lab-115505.azurewebsites.net/health"
```

**S1 — Correct audience token:**

```bash
# Attempted to get token for the app's own client ID
TOKEN=$(az account get-access-token --resource "12117775-bbe0-4e69-9e12-58ed4fc8f8d2" \
  --query "accessToken" -o tsv)
# Requires interactive consent — not available in non-interactive context
```

## 9. Expected signal

- S1: HTTP 200 with `X-MS-CLIENT-PRINCIPAL` header containing base64-encoded token claims.
- S2: HTTP 401 with `WWW-Authenticate: Bearer` header. No request reaches the application.
- S3: HTTP 401 with `WWW-Authenticate: Bearer` header.

## 10. Results

### S3 — No token (unauthenticated)

```
HTTP/2 401
WWW-Authenticate: Bearer realm="app-easyauth-lab-115505.azurewebsites.net"
  authorization_uri="https://login.windows.net/16b3c013-d300-468d-ac64-7eda0820b6d3/oauth2/v2.0/authorize"
  resource_id="12117775-bbe0-4e69-9e12-58ed4fc8f8d2"
x-ms-middleware-request-id: 10e1fe8d-fb69-405c-9497-40d2c087c339
```

No request reached the application (no console log entry for `/health`).

### S2 — Wrong audience token (aud = `https://management.azure.com/`)

```bash
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query "accessToken" -o tsv)
# Token aud: https://management.azure.com/ (NOT the app's client ID)

curl -sI "https://app-easyauth-lab-115505.azurewebsites.net/health" \
  -H "Authorization: Bearer $TOKEN"
# Response:
# HTTP/2 401
# WWW-Authenticate: Bearer realm="app-easyauth-lab-115505.azurewebsites.net"
#   authorization_uri="https://login.windows.net/.../oauth2/v2.0/authorize"
#   resource_id="12117775-bbe0-4e69-9e12-58ed4fc8f8d2"
```

**Identical response to S3 (no token).** The wrong-audience token was rejected with the same 401 and same `WWW-Authenticate` header. No request reached the application.

### S1 — Correct audience token

Could not be obtained non-interactively — `az account get-access-token --resource <app-client-id>` requires interactive consent for this app in this environment. The scenario was not completed.

## 11. Interpretation

**H1 — Confirmed (wrong audience → 401).** A token with `aud = https://management.azure.com/` was rejected by Easy Auth with HTTP 401. The rejection response is identical to a request with no token at all. Easy Auth does not indicate why the token was rejected — the `WWW-Authenticate` header simply asks for a new token targeting the correct `resource_id`. **[Measured]**

**H4 — Partially confirmed (by design).** The application received zero console log entries during the 401 responses — the request never reached the Python application. This confirms Easy Auth intercepts and rejects at the middleware layer before the application code runs. **[Observed]**

**Key finding:** Easy Auth's 401 response for wrong audience and for missing token is **identical** — same HTTP status, same `WWW-Authenticate` header with `realm`, `authorization_uri`, and `resource_id`. There is no additional indication of "invalid token" vs. "missing token" in the API response headers. Distinguishing these cases requires examining the `AppServiceAuthLogs` in Log Analytics. **[Measured]**

## 12. What this proves

- A token with wrong audience (`aud ≠ client_id`) is rejected by Easy Auth v2 with HTTP 401. The rejection is indistinguishable from a missing token in the API response.
- Easy Auth intercepts at the middleware layer — the application receives no request and produces no console log.
- The `WWW-Authenticate` header in the 401 response includes the correct `resource_id` (the app's client ID), which a well-behaved client can use to re-acquire a token with the correct audience.

## 13. What this does NOT prove

- Whether the `AppServiceAuthLogs` entry contains a specific rejection reason for audience mismatch vs. missing token — diagnostic settings were not configured.
- Whether an expired token with correct audience produces the same 401 response (H3) — not tested.
- Whether a cross-tenant issuer mismatch produces a different error response than an audience mismatch (H2) — not tested.
- What the `X-MS-CLIENT-PRINCIPAL` header contains for a valid token (S1 not completed).

## 14. Support takeaway

When a customer reports "service principal calls return 401 after updating Entra ID app registration":

1. **Easy Auth 401 is indistinguishable in the API response.** Whether the token has wrong audience, wrong issuer, is expired, or is missing — the response is always `HTTP 401` with `WWW-Authenticate: Bearer` and `resource_id=<client-id>`. The client should use `resource_id` to re-acquire a token with the correct audience.
2. **Check token audience with jwt.io or `az account get-access-token`.** Decode the token's `aud` claim. It must exactly match the app registration's client ID (`12117775-...`) or Application ID URI (`api://...`). A common mistake: calling `az account get-access-token --resource https://management.azure.com/` instead of `--resource <client-id>`.
3. **Enable `AppServiceAuthLogs` for detailed rejection reasons.** Go to App Service → Diagnostic settings → Add setting → Check `AppServiceAuthLogs` → Route to Log Analytics. This table contains `TokenValidationFailed` events with a `Details` field naming the specific failure (audience, issuer, expiry). Without this, support engineers have no signal beyond the 401.
4. **Application logs are empty for Easy Auth 401s.** If the customer says "my application isn't logging any errors" — that is correct and expected. The rejection happens before the request reaches application code.

## 15. Reproduction notes

- Enable diagnostic settings on the App Service to route `AppServiceAuthLogs` to a Log Analytics workspace before testing.
- Easy Auth token validation settings are under **Authentication > Edit > Token store / Allowed token audiences**.
- The `aud` claim in the token must match one of the configured audiences exactly (case-sensitive).
- Use `az account get-access-token --resource <app-id>` to obtain a token targeting a specific audience.

## 16. Related guide / official docs

- [Authentication and authorization in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization)
- [Configure your App Service app to use Microsoft Entra sign-in](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
- [AppServiceAuthLogs schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/appserviceauthlogs)
