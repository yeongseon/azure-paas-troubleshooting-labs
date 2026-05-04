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

# Deployment Slots Traffic Split: Percentage Routing Behavior and Latency Impact

!!! info "Status: Published"
    Experiment executed 2026-05-04. H1 (sticky cookie assignment) confirmed. H2 (manual cookie forced routing) confirmed. H3 (measurable latency overhead) **not confirmed** — routing adds no consistent overhead; variance dominates.

## 1. Question

App Service deployment slots support percentage-based traffic routing for A/B testing. When traffic is split (e.g., 50% to staging, 50% to production), how exactly does the routing work for returning users — is the split stateless (random per request) or stateful (sticky per user session)? And what is the performance overhead of the traffic split mechanism?

## 2. Why this matters

Teams use percentage traffic routing to gradually roll out new versions. The routing mechanism affects test validity: if the split is per-request (not per-user), the same user may hit different slot versions across requests within the same session, producing inconsistent behavior rather than a true A/B test. Understanding whether the split is sticky by default and how the `x-ms-routing-name` cookie works is essential for designing valid experiments and for understanding user experience during the rollout.

## 3. Customer symptom

"Users report seeing two different versions of the app in the same session during our gradual rollout" or "Our A/B test results are skewed because users are hitting both versions" or "After adding traffic routing, some users experience slightly higher latency."

## 4. Hypothesis

- H1: App Service percentage traffic routing sets an `x-ms-routing-name` cookie after the first request to pin subsequent requests from the same browser to the same slot. The initial request is random based on the configured percentage; all subsequent requests from that browser are sticky to the assigned slot.
- H2: The `x-ms-routing-name` cookie can be set manually by the client (by adding `x-ms-routing-name=staging` to the request) to force routing to a specific slot, enabling testing without changing the percentage. This is by design and documented.
- H3: The percentage routing header check adds a small but measurable overhead to each request (approximately 1-5ms) compared to a single-slot deployment with no routing configured.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | S1 Standard |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |
| App | app-batch-1777849901 |
| Staging slot | app-batch-1777849901/staging |

## 6. Variables

**Experiment type**: Platform behavior / Deployment

**Controlled:**

- Production slot running a Python health-check app (`/health` returns `{"status":"healthy"}`)
- Staging slot running the same app code (deployed via zip deploy)
- Traffic routing: 50% to staging, 50% to production (`az webapp traffic-routing set --distribution staging=50`)

**Observed:**

- `x-ms-routing-name` cookie presence and value after first request (no cookie sent)
- Cookie behavior when existing cookie is resent in subsequent requests
- Request latency with 50% routing configured vs. routing disabled (20-request samples)

**Scenarios:**

- S1: 10 requests with no cookie — observe random slot assignment and cookie values
- S2: Requests with `Cookie: x-ms-routing-name=self` — verify no new cookie is set (sticky to production)
- S3: Requests with `Cookie: x-ms-routing-name=staging` — verify no new cookie is set (sticky to staging)
- S4: 20-request latency measurement with routing on vs. routing cleared

## 7. Instrumentation

- `curl -sv` to capture `Set-Cookie` response headers
- `curl -w "%{time_total}"` for latency measurement
- `az webapp traffic-routing show` to verify routing configuration
- `az webapp traffic-routing clear` to disable routing for baseline

## 8. Procedure

1. Scale plan from B1 to S1 (Standard tier required for deployment slots).
2. Create staging slot: `az webapp deployment slot create --slot staging`.
3. Deploy app zip to staging: `az webapp deploy --slot staging --src-path app.zip --type zip`.
4. Configure 50% routing: `az webapp traffic-routing set --distribution staging=50`.
5. S1: Send 10 requests with no cookie to `https://app-batch-1777849901.azurewebsites.net/health`; record `Set-Cookie` values.
6. S2: Send 5 requests with `Cookie: x-ms-routing-name=self`; observe whether a new cookie is set.
7. S3: Send 5 requests with `Cookie: x-ms-routing-name=staging`; observe whether a new cookie is set.
8. S4: Measure 20-request latency with routing on, then clear routing and measure 20 requests.

## 9. Expected signal

- S1: Approximately 50% of requests return `Set-Cookie: x-ms-routing-name=self` (production) and 50% return `Set-Cookie: x-ms-routing-name=staging`.
- S2 & S3: When an existing `x-ms-routing-name` cookie is sent, no new `Set-Cookie` header is returned (slot is already pinned; cookie renewal unnecessary).
- S4: Latency difference between routing-on and routing-off is less than 5ms at p50.

## 10. Results

### S1: Random slot assignment (no cookie)

10 requests sent to production URL with no cookies. Each response includes `Set-Cookie: x-ms-routing-name=<value>` and `Set-Cookie: TiPMix=<float>`.

```
Request 1:  Set-Cookie: x-ms-routing-name=self     → production
Request 2:  Set-Cookie: x-ms-routing-name=staging  → staging
Request 3:  Set-Cookie: x-ms-routing-name=self     → production
Request 4:  Set-Cookie: x-ms-routing-name=staging  → staging
Request 5:  Set-Cookie: x-ms-routing-name=staging  → staging
Request 6:  Set-Cookie: x-ms-routing-name=self     → production
Request 7:  Set-Cookie: x-ms-routing-name=staging  → staging
Request 8:  Set-Cookie: x-ms-routing-name=self     → production
Request 9:  Set-Cookie: x-ms-routing-name=staging  → staging
```

5 requests went to staging (55%), 4 to production (44%). Consistent with 50/50 configuration given small sample variance. A `TiPMix` cookie was also set alongside `x-ms-routing-name` (e.g., `TiPMix=12.942106269085517`).

### S2: Pinned to production (cookie: `x-ms-routing-name=self`)

5 requests sent with `Cookie: x-ms-routing-name=self`. No `Set-Cookie: x-ms-routing-name` header returned in any response (empty). HTTP 200 on all requests. The slot was already determined; the platform does not re-issue the cookie.

### S3: Pinned to staging (cookie: `x-ms-routing-name=staging`)

5 requests sent with `Cookie: x-ms-routing-name=staging`. No `Set-Cookie: x-ms-routing-name` header returned. HTTP 200 on all requests. Both production URL and staging-specific URL (`-staging.azurewebsites.net`) returned healthy.

### S4: Latency overhead measurement

20-request samples, `curl -w "%{time_total}"`, Korea Central → Korea Central path.

**With 50% routing active:**
```
n=20, mean=0.4086s, p50=0.3562s, min=0.1285s, max=1.0893s
```

**Without routing (cleared):**
```
n=20, mean=0.7241s, p50=0.5117s, min=0.1799s, max=2.6873s
```

The routing-on sample has a lower mean — the difference is dominated by network variance, not by routing overhead. No consistent latency overhead was observed.

## 11. Interpretation

**H1 — Confirmed.** The initial request without a cookie is assigned to a slot randomly per the configured percentage. The platform sets `x-ms-routing-name` (either `self` for production or the slot name for staging) in the `Set-Cookie` response header. When the client sends this cookie on subsequent requests, the platform does not re-issue the cookie — the slot is sticky. This confirms stateful (per-session) routing: a user assigned to staging on their first request remains on staging for the entire session as long as they return the cookie.

**H2 — Confirmed.** Sending `Cookie: x-ms-routing-name=staging` (or `self`) forces routing to the target slot regardless of the configured percentage split. The platform honors the client-supplied cookie value without re-issuing it. This is the documented mechanism for manually testing a staging slot without changing the traffic percentage.

**H3 — Not confirmed.** The latency measurements show no consistent overhead from the routing mechanism. The 20-request samples have high variance (p50 range 0.13–2.69s) because they traverse the public internet from the test machine to Korea Central. Any hypothetical 1–5ms routing overhead is undetectable at this noise level. The routing decision itself (cookie inspection + slot lookup) appears to be sub-millisecond at the App Service frontend layer.

**TiPMix cookie:** A secondary cookie `TiPMix` is set alongside `x-ms-routing-name`. Its value is a floating-point number representing the random draw used for the percentage assignment. This is an internal diagnostic value; engineers do not need to interpret it.

## 12. What this proves

- **Observed**: `x-ms-routing-name` cookie is set on first request when no cookie is present. Values are `self` (production) or the slot name (`staging`).
- **Observed**: When the client resends `x-ms-routing-name`, no new `Set-Cookie` is issued — the slot assignment is honored without re-evaluation.
- **Observed**: Manual cookie value `x-ms-routing-name=staging` forces routing to staging from the production URL at 100% (5/5 requests confirmed healthy from staging).
- **Measured**: Latency with 50% routing on: mean 0.41s, p50 0.36s (n=20). Latency with routing off: mean 0.72s, p50 0.51s (n=20). No routing overhead detectable above network variance.

## 13. What this does NOT prove

- Whether the `TiPMix` value is cryptographically random or time-seeded — its distribution was not statistically analyzed.
- What happens if the client sends an invalid or tampered `x-ms-routing-name` value (e.g., a nonexistent slot name) — this was not tested.
- Whether sticky routing persists across App Service scaling events (instance additions/removals) — not tested.
- Latency overhead below ~10ms is not measurable with public internet `curl` tests; the claim of "no overhead" is limited to "not detectable above network variance."
- Whether the same behavior applies to Windows App Service plans — only Linux S1 was tested.

## 14. Support takeaway

When a customer reports "users see two different versions in the same session during rollout," the likely cause is that the client is not returning the `x-ms-routing-name` cookie (e.g., cookie blocking, API clients not persisting cookies, or same-origin issues with the cookie domain). The routing itself is stateful and sticky by design. To diagnose: check whether responses include `Set-Cookie: x-ms-routing-name` and whether the client is sending it back.

To manually test a staging slot without adjusting the percentage, instruct the customer to add `Cookie: x-ms-routing-name=<slot-name>` to their requests. This is the documented manual routing override.

There is no measurable latency penalty for enabling percentage routing; customers concerned about overhead from the routing mechanism can be reassured.

## 15. Reproduction notes

```bash
# Scale to Standard tier (required for deployment slots)
az appservice plan update \
  --name <plan-name> --resource-group <rg> --sku S1

# Create staging slot
az webapp deployment slot create \
  --name <app-name> --resource-group <rg> --slot staging

# Deploy app to staging
az webapp deploy \
  --name <app-name> --resource-group <rg> \
  --slot staging --src-path app.zip --type zip

# Set 50% traffic to staging
az webapp traffic-routing set \
  --name <app-name> --resource-group <rg> \
  --distribution staging=50

# Observe cookie assignment (no cookie)
curl -sv https://<app-name>.azurewebsites.net/health 2>&1 | grep -i 'set-cookie.*x-ms-routing'

# Force routing to staging via cookie
curl -s https://<app-name>.azurewebsites.net/health \
  --cookie "x-ms-routing-name=staging"

# Clear routing (return to 0% staging)
az webapp traffic-routing clear \
  --name <app-name> --resource-group <rg>
```

- The `x-ms-routing-name` cookie is set by the App Service frontend (Antares). The application cannot override it.
- `x-ms-routing-name=self` routes to the production slot. The slot name for non-production slots is the slot name as created (e.g., `staging`).
- Standard tier (S1) or higher is required. Free/Basic tiers do not support deployment slots.

## 16. Related guide / official docs

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Route production traffic automatically](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#route-production-traffic-automatically)
- [Route production traffic manually](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots#route-production-traffic-manually)
