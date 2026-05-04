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

# Application Gateway URL Rewrite Breaking App-Internal Redirects

!!! warning "Status: Draft - Blocked"
    Execution blocked: Application Gateway WAF_v2 SKU required. Cost constraint prevents provisioning in this subscription.

## 1. Question

When Application Gateway rewrites the URL or strips path prefixes before forwarding to App Service, app-internal redirects (HTTP 301/302) that the application generates using the original request URL will reference the wrong base URL. Under what conditions does this create a redirect loop or a broken redirect, and how can the application be made aware of the rewritten URL?

## 2. Why this matters

Application Gateway is commonly used to host multiple App Service apps under a single public endpoint using path-based routing (`/api/` → App Service A, `/web/` → App Service B). When the gateway strips the path prefix before forwarding (e.g., `/api/users` becomes `/users` at App Service), the application may issue redirects to `/` (root) that become `/api/` at the gateway — but the application generates the redirect as `https://app.azurewebsites.net/` (internal URL), causing the browser to leave the gateway URL and go directly to the App Service URL. This breaks the routing architecture and may expose the internal App Service URL to clients.

## 3. Customer symptom

"After adding Application Gateway, some pages redirect to the wrong URL" or "Login redirects go to the azurewebsites.net domain instead of our custom domain" or "The app works fine directly but breaks when accessed through Application Gateway."

## 4. Hypothesis

- H1: When Application Gateway rewrites the `Host` header to the App Service hostname (`.azurewebsites.net`) and the app generates an absolute redirect using `request.host`, the redirect uses the App Service hostname instead of the gateway hostname.
- H2: Configuring Application Gateway to preserve the `Host` header (forward the original client hostname) causes App Service to see the gateway hostname and generate correct absolute redirects.
- H3: Configuring the app to use relative redirects (instead of absolute) avoids the hostname issue entirely, regardless of Application Gateway host header configuration.
- H4: The `X-Forwarded-Host` header is forwarded by Application Gateway and can be used by the app to construct the correct redirect URL when the gateway hostname differs from the backend hostname.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Routing

**Controlled:**

- Application Gateway v2 with path-based routing: `/app/*` → App Service
- App Service with Flask app that has a login redirect (absolute URL redirect)
- Application Gateway host header override setting (enabled/disabled)

**Observed:**

- `Location` header value in 302 redirect responses
- Final URL after redirect chain
- Presence of `X-Forwarded-Host` header in the request reaching App Service

**Scenarios:**

- S1: App Gateway with host override (backend hostname) → redirect points to azurewebsites.net
- S2: App Gateway preserving original host header → redirect points to gateway hostname
- S3: App uses `X-Forwarded-Host` to construct redirect → correct URL regardless of host header setting
- S4: App uses relative redirects → no hostname issue

## 7. Instrumentation

- `curl -v https://<agw-hostname>/app/login` to capture `Location` header
- App `/headers` endpoint to inspect what hostname the app sees (`Host`, `X-Forwarded-Host`)
- Application Gateway access logs for rewrite rule application

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Flask app with `/login` endpoint that redirects to `https://{request.host}/dashboard` (absolute redirect using `request.host`).
2. Configure Application Gateway with override host header = App Service hostname.
3. S1: Access `/app/login` via Application Gateway; capture `Location` header; confirm it points to App Service hostname.
4. S2: Change Application Gateway to preserve original host header; retry; confirm `Location` points to gateway hostname.
5. S3: Update app to use `request.headers.get('X-Forwarded-Host', request.host)` for redirect construction; retry with override; confirm correct URL.
6. S4: Change redirect to relative (`/dashboard`); retry all gateway configurations; confirm `Location` is always relative.

## 9. Expected signal

- S1: `Location: https://<app>.azurewebsites.net/dashboard` (exposes internal URL).
- S2: `Location: https://<agw-hostname>/app/dashboard` or `https://<agw-hostname>/dashboard` depending on path handling.
- S3: App constructs correct URL from `X-Forwarded-Host`; `Location` points to gateway hostname.
- S4: `Location: /dashboard` (relative; browser resolves against current base URL, which is the gateway).

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

- Application Gateway host header override is configured per backend setting: `Pick host name from backend target` vs. custom host name vs. preserve client host name.
- App Service requires the `Host` header to match its hostname or configured custom domain to route correctly; using a wrong host may cause 400 errors.
- Easy Auth redirect URIs must also account for the gateway hostname when Easy Auth is used behind Application Gateway.

## 16. Related guide / official docs

- [Application Gateway URL rewrite](https://learn.microsoft.com/en-us/azure/application-gateway/rewrite-http-headers-url)
- [Application Gateway with App Service backend](https://learn.microsoft.com/en-us/azure/application-gateway/configure-web-app)
- [Override HTTP host headers with Application Gateway](https://learn.microsoft.com/en-us/azure/application-gateway/how-application-gateway-works#modifications-to-the-request)
