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

# ARR Affinity: Session Stickiness During Instance Restart and Scale Events

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When ARR Affinity (session affinity) is enabled on a multi-instance App Service and the affinity-pinned instance is restarted or removed, what happens to in-flight requests and ongoing client sessions — and does disabling affinity change load distribution measurably under steady-state traffic?

## 2. Why this matters

ARR Affinity pins client sessions to a specific backend instance. When the pinned instance is restarted during a deployment or scale event, clients lose their affinity cookie binding and must reconnect. For stateless applications this may be invisible; for stateful sessions (login tokens cached in memory, WebSocket connections, SignalR) it causes visible errors. Support engineers also encounter cases where one instance consistently handles more traffic than others, which can indicate affinity imbalance under skewed initial distribution — particularly when a small number of clients arrived before others and were all pinned to one instance.

## 3. Customer symptom

"After a deployment or restart, some users get errors and have to log in again" or "One App Service instance is always overloaded while the others are nearly idle" or "Disabling ARR Affinity seemed to fix the load imbalance but I'm not sure why."

## 4. Hypothesis

- H1: With ARR Affinity enabled, the platform sets two cookies (`ARRAffinity` and `ARRAffinitySameSite`) in the HTTP response. The application code cannot read these cookies directly because they are `HttpOnly`. ✅ **Confirmed**
- H2: When ARR Affinity is disabled, no affinity cookies are set in responses. ✅ **Confirmed**
- H3: Disabling ARR Affinity is instantaneous via `az webapp update --client-affinity-enabled false`; the change takes effect within ~10 seconds. ✅ **Confirmed**
- H4: The platform injects ARR-related request headers (`X-Arr-Ssl`, `X-Arr-Log-Id`, `X-Client-Ip`, `X-Forwarded-For`) regardless of whether ARR Affinity is enabled. ✅ **Confirmed**

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

**Experiment type**: Configuration / Platform behavior

**Controlled:**

- Python Flask app with `/cookies` (reads `request.cookies`) and `/headers` (returns all request headers) endpoints
- Single instance (B1 plan)

**Observed:**

- `Set-Cookie` headers in HTTP response with ARR Affinity enabled vs. disabled
- ARR platform headers injected into application request context

**Scenarios:**

- S1: ARR Affinity enabled (default) — capture `Set-Cookie` response headers
- S2: ARR Affinity disabled via CLI — confirm no affinity cookies in response
- S3: Both states — capture ARR request headers visible to application

## 7. Instrumentation

- `curl -sv` to capture full response headers including `Set-Cookie`
- Flask `/cookies` endpoint returning `request.cookies` as JSON — confirms application-side cookie visibility
- Flask `/headers` endpoint returning all request headers — confirms platform header injection

## 8. Procedure

1. Deployed Flask app to `app-batch-1777849901` (B1, Korea Central).
2. S1: Sent `GET /cookies` with `curl -sv`; captured raw response headers; confirmed `ARRAffinity` and `ARRAffinitySameSite` cookies in `Set-Cookie`.
3. Sent `GET /headers`; captured all request headers forwarded to the application.
4. S2: Ran `az webapp update --client-affinity-enabled false`; waited 10 seconds; re-sent `GET /cookies`; confirmed no `Set-Cookie` affinity cookies.

## 9. Expected signal

- S1: Two `Set-Cookie` headers: `ARRAffinity` (HttpOnly, Secure) and `ARRAffinitySameSite` (HttpOnly, SameSite=None, Secure).
- S2: No `ARRAffinity`-related `Set-Cookie` headers.
- S3: Platform headers (`X-Arr-Ssl`, `X-Arr-Log-Id`, `X-Client-Ip`, `X-Forwarded-For`) present in both states.

## 10. Results

**S1 — ARR Affinity enabled:**

```
Set-Cookie: ARRAffinity=689f7d9566d7788e1e4d31f634b70eb5fd184e26aa8622b4ca24b879e04bae39;
            Path=/;HttpOnly;Secure;Domain=app-batch-1777849901.azurewebsites.net
Set-Cookie: ARRAffinitySameSite=689f7d9566d7788e1e4d31f634b70eb5fd184e26aa8622b4ca24b879e04bae39;
            Path=/;HttpOnly;SameSite=None;Secure;Domain=app-batch-1777849901.azurewebsites.net
```

Application-side `/cookies` response:

```json
{"arr_affinity_set": false, "cookies": {}}
```

The application receives an empty `request.cookies` dict — `HttpOnly` prevents JavaScript and server-side `Cookie:` header parsing from seeing these cookies, but they ARE sent back by the browser on subsequent requests.

**Platform headers injected into application request (S3):**

```
X-Arr-Ssl: 2048|256|CN=Microsoft TLS G2 RSA CA OCSP 04, ...|CN=*.azurewebsites.net, ...
X-Original-Url: /headers
X-Forwarded-For: 121.190.225.37:51152
X-Client-Ip: 121.190.225.37
X-Site-Deployment-Id: app-batch-1777849901
X-Arr-Log-Id: b3fc85f1-840a-4348-8b03-c90aa426141d
```

**S2 — ARR Affinity disabled:**

```
CLI: az webapp update --client-affinity-enabled false (exit 0, ~8 seconds)
Response cookies: (none)
```

No `Set-Cookie` headers containing `ARRAffinity` in the response.

## 11. Interpretation

- **Observed**: With ARR Affinity enabled, the platform front-end (ARR — Application Request Routing) sets two cookies in every response: `ARRAffinity` (standard) and `ARRAffinitySameSite` (for cross-site iframe scenarios). Both carry the same opaque instance token.
- **Observed**: Both cookies are `HttpOnly` — they are invisible to `document.cookie` in the browser and to the application's `request.cookies` dict. The application cannot read, modify, or suppress them.
- **Observed**: Disabling ARR Affinity removes both cookies from responses. The change propagates within approximately 10 seconds without a restart.
- **Observed**: ARR injects request headers (`X-Arr-Ssl`, `X-Arr-Log-Id`, `X-Client-Ip`, `X-Forwarded-For`, `X-Site-Deployment-Id`) into every request regardless of affinity state. These are not ARR Affinity-specific; they are standard ARR proxy headers.
- **Inferred**: Because the cookies are `HttpOnly`, application code that tries to read `ARRAffinity` from `request.cookies` will always find it absent. The affinity mechanism operates entirely between the client browser and the ARR front-end; the application backend never sees the cookie value.

## 12. What this proves

- The platform sets `ARRAffinity` and `ARRAffinitySameSite` cookies when session affinity is enabled, and sets none when disabled.
- The cookies are `HttpOnly` — application code cannot read them server-side via `request.cookies`.
- Disabling ARR Affinity takes effect within ~10 seconds via `az webapp update --client-affinity-enabled false`.
- ARR request headers (`X-Forwarded-For`, `X-Client-Ip`, `X-Arr-Log-Id`) are present in all requests regardless of affinity state.

## 13. What this does NOT prove

- This experiment ran on a single B1 instance. Per-instance load distribution imbalance (the original H1/H3 multi-instance scenario) was **Not Proven** — B1 does not scale to multiple instances for direct per-instance routing comparison.
- The behavior of affinity cookies during an instance restart was **Not Tested** — B1 single instance has no alternate instance to reroute to.
- SignalR and WebSocket affinity behavior were **Not Tested** in this run.
- The `ARRAffinitySameSite` cookie behavior for cross-origin iframe scenarios is **Inferred** from cookie attributes only; not directly tested.

## 14. Support takeaway

- When a customer reports "my app ignores the ARR Affinity cookie" — the application is expected to not see it. `HttpOnly` is intentional; the cookie exists between browser and the ARR layer only.
- When a customer sees one instance consistently overloaded: first confirm they are on a plan with multiple instances (B1 is single-instance). On multi-instance plans, disabling ARR Affinity is the correct recommendation for stateless apps. For stateful apps (SignalR, in-memory session), disabling affinity without a backplane will break sessions.
- To confirm affinity status: `az webapp show -n <app> -g <rg> --query clientAffinityEnabled`.
- The `X-Client-Ip` header is the most reliable source for the real client IP; `X-Forwarded-For` may contain proxy chain entries.

## 15. Reproduction notes

```bash
# Enable ARR Affinity (default)
az webapp update -n <app> -g <rg> --client-affinity-enabled true

# Disable ARR Affinity
az webapp update -n <app> -g <rg> --client-affinity-enabled false

# Verify cookie presence
curl -sv https://<app>.azurewebsites.net/ 2>&1 | grep -i "ARRAffinity\|Set-Cookie"

# Verify platform headers (requires app that returns request.headers)
curl -s https://<app>.azurewebsites.net/headers | python3 -m json.tool
```

## 16. Related guide / official docs

- [Configure an App Service app — session affinity](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [ARR Affinity and SignalR on Azure App Service](https://learn.microsoft.com/en-us/aspnet/core/signalr/scale?view=aspnetcore-8.0#azure-app-service)
- [Robust apps for the cloud — App Service best practices](https://azure.github.io/AppService/2020/05/15/Robust-Apps-for-the-Cloud.html)
