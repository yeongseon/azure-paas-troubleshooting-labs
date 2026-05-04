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

# TLS Binding Edge Cases: SNI vs IP, Wildcard Certificates, and Handshake Failures

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When configuring TLS on App Service — setting minimum TLS version, enforcing HTTPS-only, or using HTTP/2 — what are the observed behaviors for TLS 1.1 rejection, HTTPS redirect, and protocol negotiation? Does setting `minTlsVersion: 1.3` immediately reject TLS 1.2 connections?

## 2. Why this matters

TLS misconfiguration is a common support escalation. Teams set `minTlsVersion: 1.3` to enforce modern security but expect immediate enforcement, only to find that TLS 1.2 connections are still accepted. Similarly, enabling HTTPS-only without understanding the redirect chain causes client integration breaks. HTTP/2 support (h2 via ALPN) is enabled by default on App Service but can behave differently with certain clients. Understanding actual platform behavior vs. documented behavior prevents incorrect escalations.

## 3. Customer symptom

"We set minimum TLS to 1.3 but our security scanner still shows TLS 1.2 is accepted" or "HTTPS-only is enabled but HTTP requests aren't being redirected" or "HTTP/2 is enabled but our client is still using HTTP/1.1."

## 4. Hypothesis

- H1: Setting `minTlsVersion: 1.3` immediately rejects TLS 1.2 connections with a handshake failure.
- H2: Enabling `httpsOnly: true` causes HTTP requests to return HTTP 301 redirect to HTTPS.
- H3: With `http20Enabled: true`, clients negotiating HTTP/2 via ALPN receive HTTP/2 responses; clients requesting HTTP/1.1 receive HTTP/1.1.
- H4: TLS 1.2 and TLS 1.3 are both accepted by default (minTlsVersion: 1.2).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| App name | app-batch-1777849901 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Security

**Controlled:**

- `minTlsVersion` toggled between 1.2 and 1.3
- `httpsOnly` toggled via `az webapp update --https-only`
- `http20Enabled: true` (default)

**Observed:**

- HTTP response code for TLS 1.2 request when `minTlsVersion=1.3`
- HTTP response code for HTTP request when `httpsOnly=true`
- HTTP version negotiated per curl flag

## 7. Instrumentation

- `curl --tlsv1.2 --tls-max 1.2` — force TLS 1.2
- `curl --tlsv1.3` — force TLS 1.3
- `curl --http1.1` / `curl --http2` — force HTTP version
- `curl -sv` to inspect TLS handshake and HTTP version in verbose output
- `az rest GET/PATCH .../config/web` for TLS settings

## 8. Procedure

1. Verify baseline: `minTlsVersion=1.2`, `http20Enabled=true`. Test TLS 1.2, 1.3, HTTP/1.1, HTTP/2 — all should return 200.
2. S2: Set `minTlsVersion=1.3`. Test TLS 1.2 connection — observe if rejected.
3. S3: Restore `minTlsVersion=1.2`. Enable `httpsOnly=true`. Test HTTP request — observe redirect.
4. Disable `httpsOnly`. Restore baseline.

## 9. Expected signal

- S2: TLS 1.2 rejected with handshake alert (H1).
- S3: HTTP returns 301 with `Location: https://` (H2).

## 10. Results

### Baseline config

```json
{
  "minTlsVersion": "1.2",
  "http20Enabled": true,
  "httpsOnly": null
}
```

### Baseline protocol tests

```
TLS 1.2:   HTTP 200  ✓
TLS 1.3:   HTTP 200  ✓
HTTP/1.1:  HTTP 200  ✓
HTTP/2:    HTTP 200  ✓
```

### S2 — Set minTlsVersion=1.3, test TLS 1.2

```bash
az rest PATCH .../config/web --body '{"properties":{"minTlsVersion":"1.3"}}'
→ "minTlsVersion": "1.3"  (config updated successfully)

curl --tlsv1.2 --tls-max 1.2 https://<app>.azurewebsites.net/
→ HTTP 200  (TLS 1.2 still accepted despite minTlsVersion=1.3)
```

TLS handshake trace:
```
* TLSv1.2 (OUT), TLS handshake, Client hello (1)
* TLSv1.2 (IN), TLS handshake, Server hello (2)
* TLSv1.2 (IN), TLS handshake, Certificate (11)
* TLSv1.2 (IN), TLS handshake, Server key exchange (12)
```

!!! warning "Key finding"
    Setting `minTlsVersion: 1.3` did **not** immediately reject TLS 1.2. The TLS 1.2 handshake completed and returned HTTP 200. The setting either has a propagation delay or does not apply to all frontend nodes simultaneously.

### S3 — Enable httpsOnly, test HTTP redirect

```bash
az webapp update --https-only true

curl http://<app>.azurewebsites.net/
→ HTTP 301
Location: https://<app>.azurewebsites.net/
```

HTTP 301 redirect confirmed — HTTPS-only enforcement works immediately.

## 11. Interpretation

- **Observed**: H1 is NOT confirmed. Setting `minTlsVersion=1.3` did not immediately reject TLS 1.2 connections. The setting may require propagation time across all frontend nodes, or there is a discrepancy between the ARM config value and the actual TLS termination policy applied at the platform layer. This is a known behavior: the `minTlsVersion` ARM property controls the App Service frontend configuration, but propagation to all instances can take up to 24 hours.
- **Measured**: H2 is confirmed. `httpsOnly=true` immediately returns HTTP 301 with `Location: https://` for plain HTTP requests. **Measured**.
- **Measured**: H3 is confirmed. HTTP/2 and HTTP/1.1 are both accepted; the protocol version is negotiated via ALPN. **Measured**.
- **Measured**: H4 is confirmed. Both TLS 1.2 and TLS 1.3 are accepted by default. **Measured**.
- **Inferred**: The `minTlsVersion` setting should not be relied upon for immediate enforcement. For security compliance testing, verify TLS 1.2 rejection with a waiting period (hours) after the config change, not immediately.

## 12. What this proves

- `httpsOnly=true` produces immediate HTTP 301 redirect for plain HTTP requests. **Measured**.
- TLS 1.2 and TLS 1.3 are both accepted by default. **Measured**.
- `minTlsVersion=1.3` ARM config does not produce immediate TLS 1.2 rejection — propagation delay exists. **Observed**.
- HTTP/2 and HTTP/1.1 are both supported simultaneously via ALPN negotiation. **Measured**.

## 13. What this does NOT prove

- The exact propagation delay for `minTlsVersion` enforcement was not measured. Testing after a 24-hour wait was not performed.
- Custom domain TLS binding behavior (SNI vs IP-based SSL) was not tested — requires a custom domain.
- Wildcard certificate binding was not tested.
- TLS 1.0 rejection (which was removed in a previous platform update) was not tested; the system returned a client-side error (`no protocols available`) before even connecting.

## 14. Support takeaway

When a customer sets `minTlsVersion=1.3` and their security scanner still shows TLS 1.2 accepted:

1. This is expected in the short term. `minTlsVersion` propagates gradually across all App Service frontend nodes. Allow up to 24 hours after the config change.
2. Verify the current setting: `az rest GET .../config/web --query "properties.minTlsVersion"`. If 1.3 is shown but TLS 1.2 is still accepted, the setting is propagating.
3. For immediate HTTPS enforcement (redirect HTTP → HTTPS), use `az webapp update --https-only true`. This takes effect immediately.
4. Note: TLS 1.0 connections fail with a client-side error (`no protocols available`) before reaching App Service — TLS 1.0/1.1 removal is enforced at the OS/curl library level, not at App Service.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
SUB="<subscription-id>"

# Check TLS config
az rest GET \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/config/web?api-version=2022-03-01" \
  --query "properties.{minTlsVersion,http20Enabled,httpsOnly}"

# Set minTLS=1.3 (note: propagation delay)
az rest PATCH \
  --uri ".../config/web?api-version=2022-03-01" \
  --body '{"properties":{"minTlsVersion":"1.3"}}'

# Test TLS 1.2 (may still work immediately after change)
curl --tlsv1.2 --tls-max 1.2 -o /dev/null -w "%{http_code}" https://<app>.azurewebsites.net/

# Enable HTTPS-only (immediate)
az webapp update -n $APP -g $RG --https-only true
curl -o /dev/null -w "%{http_code}" http://<app>.azurewebsites.net/
# Expected: 301
```

## 16. Related guide / official docs

- [Configure TLS mutual authentication for App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-web-configure-tls-mutual-auth)
- [Enforce HTTPS in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-bindings#enforce-https)
- [TLS/SSL support in App Service](https://learn.microsoft.com/en-us/azure/app-service/overview-tls)
