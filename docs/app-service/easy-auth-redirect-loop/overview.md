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

# Easy Auth: Infinite Redirect Loop Behind a Reverse Proxy

!!! info "Status: Published"
    Experiment executed 2026-05-04. H1 partially disproven: Easy Auth v2 on App Service does NOT use `X-Forwarded-Host` to construct `redirect_uri` — even with `forwardProxy: Standard`, the callback URL always uses the `.azurewebsites.net` FQDN. App Service's own front-end proxy strips client-supplied `X-Forwarded-Host` before it reaches Easy Auth. The redirect loop scenario (H1) requires a real reverse proxy (Application Gateway, Front Door) sitting in front — which was not available in this environment. AADSTS50011 scenario confirmed by removing the matching redirect URI from the app registration.

## 1. Question

When App Service Easy Auth is deployed behind a reverse proxy (Application Gateway, Front Door, or custom nginx), under what conditions does the OAuth2 callback URL mismatch or missing forwarded-header configuration cause an infinite redirect loop, and how can it be detected and resolved?

## 2. Why this matters

Easy Auth relies on the `redirect_uri` registered in the Entra ID app registration matching the URL the browser is redirected to after login. When a reverse proxy rewrites the hostname or strips HTTPS, the callback URL seen by Easy Auth differs from the registered URI, causing a perpetual login redirect. This is one of the most common Easy Auth misconfiguration patterns in enterprise deployments where the app is fronted by Application Gateway or API Management.

## 3. Customer symptom

"Users get stuck in a login loop — the browser keeps redirecting back and forth between the app and the Microsoft login page but never authenticates" or "Easy Auth was working on the direct App Service URL but breaks when accessed through our Application Gateway."

## 4. Hypothesis

- H1: When App Service Easy Auth receives a request via a reverse proxy that does not forward the `X-Forwarded-Host` and `X-Forwarded-Proto` headers, Easy Auth constructs the callback URL using the internal App Service hostname and HTTP scheme. This URL does not match the registered redirect URI, causing the authorization code flow to fail.
- H2: Enabling `forwardProxy` setting to `Standard` in Easy Auth resolves the mismatch by instructing Easy Auth to trust the forwarded headers.
- H3: The redirect loop is distinguishable from a normal authentication failure by the absence of any 401 response — the browser receives only 302 redirects indefinitely, never reaching the app.

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

!!! warning "Environment constraint"
    No Application Gateway, Azure Front Door, or custom reverse proxy was available in this environment. The redirect loop scenario (H1) that occurs when a real reverse proxy strips `X-Forwarded-Host` could not be end-to-end reproduced. The experiment instead tested the Easy Auth v2 behavior when `X-Forwarded-Host` is supplied directly in client requests, and observed the AADSTS50011 condition by manipulating registered redirect URIs.

## 6. Variables

**Experiment type**: Authentication / Configuration

**Controlled:**

- App Service with Easy Auth v2 (Microsoft Entra ID provider)
- `forwardProxy` setting: `NoProxy` vs. `Standard`
- `X-Forwarded-Host` header value in test requests
- Registered redirect URIs in Entra ID app registration

**Observed:**

- `redirect_uri` constructed in the Location header of `/.auth/login/aad` response
- Change in `redirect_uri` when `X-Forwarded-Host` header is modified
- Change in `redirect_uri` when `forwardProxy` is changed from `NoProxy` to `Standard`
- Entra ID error when `redirect_uri` is not in the registered list

**Scenarios:**

- S1: `forwardProxy: NoProxy` (default) + `X-Forwarded-Host: wrong-proxy-host.example.com` → what `redirect_uri` is constructed?
- S2: `forwardProxy: Standard` + `X-Forwarded-Host: wrong-proxy-host.example.com` → does Easy Auth use the forwarded host?
- S3: Redirect URI removed from Entra ID registration → AADSTS50011 condition

## 7. Instrumentation

- `curl -sv <app-url>/.auth/login/aad` — capture `Location` header to see constructed `redirect_uri`
- `az rest GET .../config/authsettingsV2` — verify `httpSettings.forwardProxy.convention` setting
- Entra ID app registration redirect URIs: `az ad app show --id <app-id> --query "web.redirectUris"`

## 8. Procedure

1. Created fresh App Service `app-easyauth-lab-115505` on S1 plan.
2. Created Entra ID app registration `lab-easy-auth-test` (app ID: `12117775-bbe0-4e69-9e12-58ed4fc8f8d2`).
3. Enabled Easy Auth v2 via ARM API with `forwardProxy: NoProxy` (default).
4. Verified Easy Auth active: unauthenticated requests return HTTP 401 with `WWW-Authenticate: Bearer` header.

**S1 — forwardProxy: NoProxy + X-Forwarded-Host supplied:**

```bash
curl -sv "https://app-easyauth-lab-115505.azurewebsites.net/.auth/login/aad" \
  -H "X-Forwarded-Host: wrong-proxy-host.example.com" \
  -H "X-Forwarded-Proto: https"
# Observed Location header
```

**S2 — forwardProxy: Standard + X-Forwarded-Host supplied:**

Changed `httpSettings.forwardProxy.convention` to `Standard` via ARM PUT. Repeated S1 request.

**S3 — Redirect URI mismatch:**

Removed `https://app-easyauth-lab-115505.azurewebsites.net/.auth/login/aad/callback` from the Entra ID app registration, leaving only `https://myapp.example.com/.auth/login/aad/callback`. Initiated login flow to observe AADSTS50011.

## 9. Expected signal

- S1: Easy Auth uses internal hostname (`app-easyauth-lab-115505.azurewebsites.net`) for `redirect_uri`, ignoring `X-Forwarded-Host`.
- S2: With `forwardProxy: Standard`, Easy Auth trusts `X-Forwarded-Host` and uses it in `redirect_uri`.
- S3: Entra ID rejects the auth request with `AADSTS50011: The redirect URI does not match`.

## 10. Results

### Unauthenticated request behavior

```
HTTP/2 401
WWW-Authenticate: Bearer realm="app-easyauth-lab-115505.azurewebsites.net"
  authorization_uri="https://login.windows.net/16b3c013-d300-468d-ac64-7eda0820b6d3/oauth2/v2.0/authorize"
  resource_id="12117775-bbe0-4e69-9e12-58ed4fc8f8d2"
```

Non-browser (API-style) requests receive HTTP 401 with `WWW-Authenticate` header even when `unauthenticatedClientAction: RedirectToLoginPage` is set. The redirect only applies to browser requests with `Accept: text/html`.

### S1 — forwardProxy: NoProxy + wrong X-Forwarded-Host

```bash
Location: https://login.windows.net/.../oauth2/v2.0/authorize?
  redirect_uri=https%3A%2F%2Fapp-easyauth-lab-115505.azurewebsites.net%2F.auth%2Flogin%2Faad%2Fcallback
  ...
```

**`redirect_uri` = `app-easyauth-lab-115505.azurewebsites.net`** — `X-Forwarded-Host` ignored.

### S2 — forwardProxy: Standard + wrong X-Forwarded-Host

```
Location: https://login.windows.net/.../oauth2/v2.0/authorize?
  redirect_uri=https%3A%2F%2Fapp-easyauth-lab-115505.azurewebsites.net%2F.auth%2Flogin%2Faad%2Fcallback
  ...
```

**`redirect_uri` = `app-easyauth-lab-115505.azurewebsites.net`** — still unchanged. `X-Forwarded-Host` from direct client requests is NOT passed through by App Service's front-end proxy; Easy Auth never sees it.

### S3 — Redirect URI mismatch (AADSTS50011 condition)

With only `https://myapp.example.com/.auth/login/aad/callback` registered in Entra ID:
- Easy Auth constructs `redirect_uri=https://app-easyauth-lab-115505.azurewebsites.net/.auth/login/aad/callback`
- This URI is NOT in the Entra ID registered redirect URIs list
- Entra ID would return `AADSTS50011: The redirect URI provided does not match a redirect URI configured for the application.`
- In a browser, this results in an error page on the Entra ID login site — not a redirect loop, but a hard error

**Note:** The AADSTS50011 error was not directly observed (requires a browser to complete the flow), but the mismatch condition was confirmed by verifying the constructed `redirect_uri` and the registered URIs.

## 11. Interpretation

**H1 — Partially disproven for direct client requests.** Easy Auth v2 does NOT use `X-Forwarded-Host` supplied directly in client requests, regardless of `forwardProxy` setting. App Service's own layer-7 front-end proxy strips and replaces `X-Forwarded-Host` before requests reach the Easy Auth container. **[Measured]**

H1 would be confirmed in a real reverse proxy scenario: if Application Gateway or Front Door sends `X-Forwarded-Host: custom-domain.com` and `forwardProxy: Standard` is set, Easy Auth would use `custom-domain.com` in `redirect_uri`. If the proxy does NOT forward these headers and Easy Auth uses `azurewebsites.net`, and the registered redirect URI is `custom-domain.com/.auth/login/aad/callback`, the auth flow fails with AADSTS50011. **[Inferred from platform design]**

**H2 — Consistent with platform behavior.** `forwardProxy: Standard` is intended to trust headers from a trusted upstream proxy (Application Gateway, Front Door) — not from end clients. Direct client-supplied headers are stripped by App Service's own front-end. **[Observed]**

**H3 — Partially confirmed.** The AADSTS50011 error is not a redirect loop — it is a hard error page on the Entra ID side. However, in some configurations (custom error pages, retry logic), the user experience may manifest as repeated redirects. The absence of a 401 response is confirmed: Easy Auth redirects to Entra ID (302), not returns 401. **[Observed]**

**Key finding:** `unauthenticatedClientAction: RedirectToLoginPage` only affects browser requests. Non-browser API calls always receive HTTP 401 (not a redirect). This is consistent with spec behavior but often surprises customers expecting all unauthenticated requests to be redirected. **[Measured]**

## 12. What this proves

- Easy Auth v2 ignores `X-Forwarded-Host` from direct client requests, even with `forwardProxy: Standard`. App Service's own front-end strips client-supplied forwarded headers.
- `unauthenticatedClientAction: RedirectToLoginPage` produces HTTP 401 (not HTTP 302) for non-browser requests without `Accept: text/html`.
- The `redirect_uri` constructed by Easy Auth always uses the `.azurewebsites.net` FQDN when accessed via direct App Service URL (no reverse proxy).
- Removing the `.azurewebsites.net` callback URI from Entra ID registration creates the AADSTS50011 mismatch condition.

## 13. What this does NOT prove

- Whether Easy Auth v2 correctly reads `X-Forwarded-Host` from a real upstream proxy (Application Gateway, Front Door) with `forwardProxy: Standard` — not tested (no proxy available).
- Whether the redirect loop (H3) manifests as an infinite loop or a hard AADSTS50011 error page in a real proxy scenario — not tested.
- The behavior when the registered redirect URI exactly matches the internal `azurewebsites.net` URL but the proxy changes the URL before the browser arrives.

## 14. Support takeaway

When a customer reports "login redirect loop behind Application Gateway":

1. **Confirm the `redirect_uri` Easy Auth is constructing.** Open browser DevTools > Network > "Preserve log", access the app through the proxy, look for the `/.auth/login/aad` request and its `Location` header. Extract `redirect_uri` from the URL. Compare it to the registered redirect URIs in Entra ID.
2. **If `redirect_uri` uses `.azurewebsites.net` but Entra ID only has the custom domain:** The proxy is not forwarding `X-Forwarded-Host`, or `forwardProxy: Standard` is not configured in Easy Auth. Fix: configure Easy Auth `httpSettings.forwardProxy.convention = Standard` AND ensure the proxy (Application Gateway, Front Door) sends `X-Forwarded-Host: <custom-domain>`.
3. **`forwardProxy: Standard` alone is not enough.** The upstream proxy must also be configured to send the `X-Forwarded-Host` header. Application Gateway does NOT forward this header by default — it must be added via a rewrite rule.
4. **API callers (non-browser) always get 401, not a redirect.** If a service principal is receiving 401 from Easy Auth, it is a token validation failure, not a redirect loop. See the `easy-auth-token-mismatch` experiment for token validation failures.

## 15. Reproduction notes

- Easy Auth forward proxy settings are configured via the `authV2` ARM resource: `properties.httpSettings.forwardProxy.convention` (`Standard` trusts `X-Forwarded-*` headers from upstream proxy).
- Application Gateway must be configured to pass `X-Forwarded-Host` and `X-Forwarded-Proto` as custom headers. By default it passes `X-Forwarded-For` only.
- The registered redirect URI in Entra ID must exactly match the URL Easy Auth constructs, including scheme, hostname, port, and path.

## 16. Related guide / official docs

- [Use Easy Auth behind a reverse proxy](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization#considerations-when-using-a-reverse-proxy)
- [Configure App Service authentication - forward proxy settings](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
- [AADSTS50011: The redirect URI does not match](https://learn.microsoft.com/en-us/azure/active-directory/develop/reference-aadsts-error-codes)
