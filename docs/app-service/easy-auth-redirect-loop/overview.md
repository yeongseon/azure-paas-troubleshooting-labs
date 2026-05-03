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

# Easy Auth: Infinite Redirect Loop Behind a Reverse Proxy

!!! info "Status: Planned"

## 1. Question

When App Service Easy Auth is deployed behind a reverse proxy (Application Gateway, Front Door, or custom nginx), under what conditions does the OAuth2 callback URL mismatch or missing forwarded-header configuration cause an infinite redirect loop, and how can it be detected and resolved?

## 2. Why this matters

Easy Auth relies on the `redirect_uri` registered in the Entra ID app registration matching the URL the browser is redirected to after login. When a reverse proxy rewrites the hostname or strips HTTPS, the callback URL seen by Easy Auth differs from the registered URI, causing a perpetual login redirect. This is one of the most common Easy Auth misconfiguration patterns in enterprise deployments where the app is fronted by Application Gateway or API Management.

## 3. Customer symptom

"Users get stuck in a login loop — the browser keeps redirecting back and forth between the app and the Microsoft login page but never authenticates" or "Easy Auth was working on the direct App Service URL but breaks when accessed through our Application Gateway."

## 4. Hypothesis

- H1: When App Service Easy Auth receives a request via a reverse proxy that does not forward the `X-Forwarded-Host` and `X-Forwarded-Proto` headers, Easy Auth constructs the callback URL using the internal App Service hostname and HTTP scheme. This URL does not match the registered redirect URI, causing the authorization code flow to fail.
- H2: Enabling `WEBSITE_AUTH_ALLOWED_REDIRECT_URLS` or configuring `forwardProxy` settings to `Standard` or `Custom` in Easy Auth resolves the mismatch by instructing Easy Auth to trust the forwarded headers.
- H3: The redirect loop is distinguishable from a normal authentication failure by the absence of any 401 response — the browser receives only 302 redirects indefinitely, never reaching the app.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Node.js 20 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Authentication

**Controlled:**

- App Service with Easy Auth (Microsoft provider) enabled
- Application Gateway in front of the App Service with a custom domain
- Entra ID app registration with redirect URI set to the Application Gateway hostname

**Observed:**

- Browser redirect chain (captured via browser DevTools Network tab or `curl -L -v`)
- Easy Auth callback URL constructed (visible in the `Location` response header)
- Resolution after enabling `X-Forwarded-Host` pass-through on Application Gateway

**Scenarios:**

- S1: Access via Application Gateway without forwarded headers → loop
- S2: Access via Application Gateway with `X-Forwarded-Host` and `X-Forwarded-Proto` headers forwarded → successful auth
- S3: Direct access to App Service URL (bypassing Application Gateway) → successful auth (confirms Easy Auth config is correct for direct access)

## 7. Instrumentation

- Browser DevTools Network tab with "Preserve log" enabled to capture full redirect chain
- `curl -L --max-redirs 10 -v <url>` to observe redirect chain from CLI
- `AppServiceAuthLogs` in Log Analytics for server-side events
- Application Gateway access logs for header pass-through verification

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy App Service with Easy Auth enabled; register redirect URI as `https://<appgw-hostname>/.auth/login/aad/callback`.
2. Configure Application Gateway to route to App Service backend without forwarding `X-Forwarded-Host`.
3. S1: Access the Application Gateway URL; capture redirect chain; confirm loop (same `Location` header repeating).
4. S2: Add HTTP header rewrite rule on Application Gateway to forward `X-Forwarded-Host: <appgw-hostname>` and `X-Forwarded-Proto: https`. Retry; confirm successful authentication.
5. S3: Access App Service URL directly; confirm auth works (baseline).
6. Query `AppServiceAuthLogs` for `AuthorizationFailed` events with callback URL mismatch details.

## 9. Expected signal

- S1: Browser redirects to `/.auth/login/aad` → Microsoft login → callback to internal App Service URL → mismatch → loop. `AppServiceAuthLogs` shows redirect URI mismatch error.
- S2: Browser completes login flow and lands on the application. `X-MS-CLIENT-PRINCIPAL` header present on requests.
- S3: Auth completes successfully, confirming the issue is proxy-header related.

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

- Easy Auth forward proxy settings are configured via the `authV2` ARM resource: `properties.login.preserveUrlFragmentsForLogins` and `properties.httpSettings.forwardProxy.convention` (`Standard` trusts `X-Forwarded-*` headers).
- Application Gateway must be configured to pass `X-Forwarded-Host` and `X-Forwarded-Proto` as custom headers. By default it passes `X-Forwarded-For` only.
- The registered redirect URI in Entra ID must exactly match the URL Easy Auth constructs, including scheme, hostname, port, and path.

## 16. Related guide / official docs

- [Use Easy Auth behind a reverse proxy](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization#considerations-when-using-a-reverse-proxy)
- [Configure App Service authentication - forward proxy settings](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
