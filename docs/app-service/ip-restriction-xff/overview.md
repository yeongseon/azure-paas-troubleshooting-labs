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

# IP Restriction X-Forwarded-For Header Bypass Risk

!!! info "Status: Planned"

## 1. Question

App Service IP restrictions filter inbound traffic based on the source IP. When App Service is behind a reverse proxy (Application Gateway, Front Door, or third-party CDN) that forwards the `X-Forwarded-For` header, does App Service evaluate the restriction against the original client IP (from `X-Forwarded-For`) or the proxy IP? And can an attacker bypass the restriction by spoofing the `X-Forwarded-For` header?

## 2. Why this matters

IP restrictions are commonly used to limit App Service access to corporate IP ranges or specific upstream services. If the restriction is enforced against the final hop (proxy IP) rather than the original client IP, and the proxy IP range is allowed, then any client that can reach the proxy can bypass the IP restriction simply by using the proxy. Conversely, if App Service evaluates `X-Forwarded-For`, an attacker can spoof that header to make their traffic appear to come from an allowed IP. Understanding the actual enforcement point is critical for secure network design.

## 3. Customer symptom

"IP restrictions are enabled but some unauthorized IPs are getting through" or "After adding Application Gateway, our IP restrictions stopped working" or "We restricted to our office IP but remote workers are still able to access the app via VPN."

## 4. Hypothesis

- H1: App Service IP restrictions evaluate the TCP-layer source IP of the connection, not the `X-Forwarded-For` header. When a proxy (Application Gateway) fronts the app, all connections come from the proxy IP. If the proxy IP is allowed in the restriction, all clients through the proxy are allowed regardless of their real IP.
- H2: Spoofing `X-Forwarded-For` has no effect on App Service IP restrictions because they operate at the TCP layer, not the HTTP header layer.
- H3: To enforce client IP-based restrictions when behind a proxy, the restriction should be applied at the proxy layer (Application Gateway WAF, Front Door, CDN rules) rather than at App Service, since App Service only sees the proxy's IP.
- H4: Service tags (e.g., `AzureFrontDoor.Backend`) can be used in App Service access restrictions to allow only traffic from Front Door's known IP ranges, preventing direct access to the App Service URL.

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

**Experiment type**: Security / Networking

**Controlled:**

- App Service with IP restriction allowing only `10.0.0.1/32`
- Application Gateway in front of App Service (AGIC or standard routing)
- Test client from a non-allowed IP with and without `X-Forwarded-For` header spoofing

**Observed:**

- HTTP response code from App Service (200 vs. 403)
- IP evaluated by App Service (verified via `/headers` endpoint showing request headers)
- Effect of `X-Forwarded-For` header manipulation

**Scenarios:**

- S1: Direct connection from allowed IP → 200
- S2: Direct connection from non-allowed IP → 403
- S3: Non-allowed IP via Application Gateway (proxy IP allowed) → expected: 200 (restriction bypassed because only proxy IP evaluated)
- S4: Non-allowed IP with spoofed `X-Forwarded-For: <allowed IP>` → restriction behavior (does spoofing help?)
- S5: Front Door service tag restriction → direct access blocked, Front Door access allowed

## 7. Instrumentation

- App `/headers` endpoint printing all request headers including `X-Forwarded-For`, `X-Client-IP`, `REMOTE_ADDR`
- HTTP response code (200 vs. 403) for each scenario
- App Service access logs for the source IP recorded on denied requests

## 8. Procedure

_To be defined during execution._

### Sketch

1. Set App Service IP restriction: allow `<test-client-IP>/32`, deny all others.
2. S1: Connect directly from test client → 200.
3. S2: Connect from a different IP (e.g., another VM) directly → 403.
4. S3: Route traffic from S2 VM through Application Gateway (whose IP is allowed) → observe if 200 or 403.
5. S4: From S2 VM, send request with `X-Forwarded-For: <allowed IP>` directly to App Service → observe response.
6. S5: Add `AzureFrontDoor.Backend` service tag to App Service restrictions; remove direct IP allow; route via Front Door → verify direct access blocked, Front Door access allowed.

## 9. Expected signal

- S1: 200 (allowed).
- S2: 403 (blocked by IP restriction).
- S3: 200 (Application Gateway's IP is what App Service evaluates; proxy bypasses IP restriction).
- S4: 403 (App Service ignores `X-Forwarded-For` for restriction evaluation — TCP source IP is non-allowed).
- S5: Direct access returns 403; Front Door access returns 200.

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

- App Service access restrictions are documented to evaluate the TCP source IP, not `X-Forwarded-For`. This is by design.
- When behind Front Door or Application Gateway, apply IP restrictions at the proxy layer, not App Service.
- The `X-Azure-ClientIP` header added by App Service shows the original client IP (from `X-Forwarded-For` if behind a proxy), but this is informational only — it is not used for access control.

## 16. Related guide / official docs

- [App Service access restrictions](https://learn.microsoft.com/en-us/azure/app-service/app-service-ip-restrictions)
- [Secure traffic to App Service with Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/origin-security)
- [Application Gateway integration with App Service](https://learn.microsoft.com/en-us/azure/application-gateway/configure-web-app)
