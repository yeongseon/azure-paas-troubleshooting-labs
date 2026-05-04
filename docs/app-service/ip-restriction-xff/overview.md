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

# IP Restriction X-Forwarded-For Header Bypass Risk

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

App Service IP restrictions filter inbound traffic based on the source IP. When a request includes a spoofed `X-Forwarded-For` header claiming to be from an allowed IP, does App Service evaluate the restriction against the spoofed header or the actual TCP-layer source IP?

## 2. Why this matters

IP restrictions are commonly used to limit App Service access to corporate IP ranges or specific upstream services. If the restriction is enforced against the final hop (proxy IP) rather than the original client IP, and the proxy IP range is allowed, then any client that can reach the proxy can bypass the IP restriction simply by using the proxy. Conversely, if App Service evaluates `X-Forwarded-For`, an attacker can spoof that header to make their traffic appear to come from an allowed IP. Understanding the actual enforcement point is critical for secure network design.

## 3. Customer symptom

"IP restrictions are enabled but some unauthorized IPs are getting through" or "After adding Application Gateway, our IP restrictions stopped working" or "We restricted to our office IP but remote workers are still able to access the app via VPN."

## 4. Hypothesis

- H1: App Service IP restrictions evaluate the TCP-layer source IP, not the `X-Forwarded-For` header. Spoofing `X-Forwarded-For` does not bypass IP restrictions. ✅ **Confirmed**
- H2: Spoofing `X-Client-Ip` also has no effect on restriction evaluation. ✅ **Confirmed**
- H3: A restriction allowing only `10.0.0.1/32` blocks requests from the actual client IP `121.190.225.37` regardless of header manipulation. ✅ **Confirmed**

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

**Experiment type**: Security / Networking

**Controlled:**

- App Service with IP restriction: allow only `10.0.0.1/32` (deny all others implicitly)
- Client IP: `121.190.225.37` (not in allowed range)
- Spoofed header values: `X-Forwarded-For: 10.0.0.1`, `X-Client-Ip: 10.0.0.1`

**Observed:**

- HTTP response code (200 vs. 403) for direct access and spoofed header requests
- Whether header manipulation changes the restriction outcome

**Scenarios:**

- S1: Direct request without any spoofed headers (client IP `121.190.225.37`, not allowed)
- S2: Request with `X-Forwarded-For: 10.0.0.1` (spoofing allowed IP in XFF header)
- S3: Request with `X-Client-Ip: 10.0.0.1` (spoofing allowed IP in client-ip header)

## 7. Instrumentation

- `curl -s -o /dev/null -w "%{http_code}"` for each scenario
- `curl -H "X-Forwarded-For: <IP>"` to inject spoofed header
- `az webapp config access-restriction add/remove` to manage test restrictions

## 8. Procedure

1. Confirmed real client IP: `121.190.225.37` (via `https://api.ipify.org`).
2. Added IP restriction: `az webapp config access-restriction add --action Allow --ip-address "10.0.0.1/32" --priority 100 --rule-name allow-fake-only`.
3. Waited 8 seconds for restriction to propagate.
4. S1: `curl` without headers → recorded HTTP status.
5. S2: `curl -H "X-Forwarded-For: 10.0.0.1"` → recorded HTTP status.
6. S3: `curl -H "X-Client-Ip: 10.0.0.1"` → recorded HTTP status.
7. Removed restriction: `az webapp config access-restriction remove --rule-name allow-fake-only`.

## 9. Expected signal

- S1: 403 (client IP not in allowed range)
- S2: 403 (XFF spoofing does not bypass TCP-layer restriction)
- S3: 403 (X-Client-Ip spoofing does not bypass TCP-layer restriction)

## 10. Results

```
Client IP:                          121.190.225.37
Restriction:                        Allow 10.0.0.1/32 only

S1: Direct request (no XFF header): HTTP 403
S2: X-Forwarded-For: 10.0.0.1:     HTTP 403
S3: X-Client-Ip: 10.0.0.1:         HTTP 403
```

**Restriction removal confirmed:** After `az webapp config access-restriction remove`, app returned HTTP 200.

**Platform-injected headers (observed earlier, before restriction):**

```
X-Forwarded-For: 121.190.225.37:51152
X-Client-Ip:     121.190.225.37
X-Arr-Log-Id:    b3fc85f1-840a-4348-8b03-c90aa426141d
```

## 11. Interpretation

- **Observed**: App Service IP restrictions evaluate the TCP-layer source IP of the inbound connection. Client-supplied `X-Forwarded-For` and `X-Client-Ip` headers are ignored for restriction enforcement purposes.
- **Observed**: Spoofing `X-Forwarded-For: 10.0.0.1` (an "allowed" IP) from a non-allowed client IP produces HTTP 403 — the restriction is not bypassed.
- **Observed**: Spoofing `X-Client-Ip: 10.0.0.1` also produces HTTP 403 — this header has no effect on restriction evaluation.
- **Observed**: The platform itself injects `X-Forwarded-For` and `X-Client-Ip` into the application request (visible in the `/headers` endpoint) — these reflect the actual client IP, not any spoofed client-supplied value. The platform overrides or appends to these headers.
- **Inferred**: When App Service is behind Application Gateway or Front Door, all TCP connections arrive from the proxy's IP, not the original client. If the proxy IP is in the allowed range, all clients routed through the proxy bypass the App Service restriction. The restriction must be applied at the proxy layer for client-IP-based enforcement.

## 12. What this proves

- App Service IP restrictions operate at the TCP layer and cannot be bypassed by spoofing `X-Forwarded-For` or `X-Client-Ip` on a direct connection.
- Restrictions propagate within ~8 seconds of the CLI command.
- The deny-all implicit default applies: adding an "Allow" rule without an explicit "Allow all" rule blocks all other IPs.

## 13. What this does NOT prove

- The proxy-bypass scenario (S3 from the original plan: Application Gateway routing) was **Not Tested** — no Application Gateway was provisioned. The behavior is **Inferred** from TCP-layer enforcement: the proxy's IP would be what App Service evaluates, not the original client IP passed in XFF.
- Service tag restrictions (`AzureFrontDoor.Backend`) were **Not Tested**.
- IPv6 restriction behavior was **Not Tested**.

## 14. Support takeaway

- "IP restrictions are enabled but unauthorized IPs get through" — check if there is a proxy (Application Gateway, Front Door, CDN, VPN) in front of App Service. The restriction evaluates the connection source IP, not `X-Forwarded-For`. If the proxy IP is allowed, all clients through the proxy bypass the restriction.
- "Can someone bypass our IP restrictions with a spoofed header?" — No, if they are connecting directly to App Service. The TCP source IP cannot be spoofed over a real TCP connection.
- To restrict by client IP when behind a proxy: apply WAF rules at Application Gateway or Front Door rules at the CDN layer; do not rely on App Service IP restrictions for client-IP enforcement in proxy deployments.
- To block direct App Service access when using Front Door: add `AzureFrontDoor.Backend` service tag as the only allowed range in App Service restrictions.

## 15. Reproduction notes

```bash
# Add IP restriction (allow only specific IP, deny all others)
az webapp config access-restriction add \
  -n <app> -g <rg> \
  --rule-name "allow-specific" \
  --action Allow \
  --ip-address "10.0.0.1/32" \
  --priority 100

# Test with spoofed XFF header
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Forwarded-For: 10.0.0.1" \
  https://<app>.azurewebsites.net/
# Returns 403 - spoofing has no effect

# Remove restriction
az webapp config access-restriction remove \
  -n <app> -g <rg> --rule-name "allow-specific"
```

## 16. Related guide / official docs

- [App Service access restrictions](https://learn.microsoft.com/en-us/azure/app-service/app-service-ip-restrictions)
- [Secure traffic to App Service with Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/origin-security)
- [Application Gateway integration with App Service](https://learn.microsoft.com/en-us/azure/application-gateway/configure-web-app)
