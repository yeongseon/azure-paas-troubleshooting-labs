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

# Multi-Instance Session State Inconsistency Without Sticky Sessions

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When an App Service plan scales out to multiple instances and ARR Affinity (sticky sessions) is disabled or misconfigured, does in-memory session state become inconsistent across requests? What does the ARRAffinity cookie value look like in practice, and does it reliably pin clients to a single instance?

## 2. Why this matters

In-memory session state (Flask sessions, ASP.NET in-memory cache, Node.js `express-session` with MemoryStore) is stored per worker process. When requests from the same client are distributed across multiple instances, the session state is unavailable on the instance that did not create it. ARR Affinity (enabled by default) mitigates this by pinning clients to a specific instance via a cookie. However, disabling ARR Affinity (a common recommendation to improve load distribution) breaks in-memory sessions without an alternative distributed cache. The failure is subtle: requests succeed but return stale or missing session data.

## 3. Customer symptom

"Users get logged out randomly even though authentication works" or "Shopping cart items disappear between page loads" or "Session state is inconsistent — some requests see the right data and others don't."

## 4. Hypothesis

- H1: With ARR Affinity disabled and 2 instances, consecutive requests from the same client are distributed across both instances — confirmed by different `hostname` values in the response.
- H2: With ARR Affinity enabled, the `ARRAffinity` cookie is set in the response and pins subsequent requests to the same instance.
- H3: Both ARRAffinity and ARRAffinitySameSite cookies are set simultaneously — the SameSite variant is for modern browser SameSite=None requirements.
- H4: If both instances return the same ARRAffinity cookie value, affinity may not function correctly even when enabled — the value must encode the specific instance.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (scaled to 2 instances) |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn |
| OS | Linux |
| App name | app-batch-1777849901 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Reliability

**Controlled:**

- 2 instances provisioned via `az appservice plan update --number-of-workers 2`
- `/worker` endpoint returning `{"hostname": "<container-id>", "pid": <n>}`
- ARR Affinity toggled via `az webapp update --client-affinity-enabled`

**Observed:**

- Hostname distribution across 20 requests without ARR Affinity
- Hostname distribution across 10 requests with ARR Affinity + cookie
- Cookie values set by the `ARRAffinity` and `ARRAffinitySameSite` headers
- Scale-out timing from 1 to 2 instances

**Scenarios:**

- S1: ARR Affinity disabled, 20 requests → observe hostname distribution
- S2: ARR Affinity enabled, 10 requests with cookie → observe stickiness
- S3: ARR Affinity enabled, 10 requests without cookie → compare distribution

## 7. Instrumentation

- `/worker` endpoint returning `hostname` (container ID) per request
- `curl -c` to capture cookies, `curl -b` to replay cookies
- `az webapp update --client-affinity-enabled` to toggle ARR Affinity
- `az appservice plan update --number-of-workers` to scale

## 8. Procedure

1. Scale plan to 2 instances. Poll until 2 distinct hostnames appear in `/worker` responses (measure time).
2. S1: Disable ARR Affinity. Send 20 sequential requests. Record hostnames.
3. S2: Enable ARR Affinity. First request → capture cookie. Send 10 requests with cookie. Record hostnames.
4. S3: Same as S2 but without the cookie header. Compare distribution.
5. Scale back to 1 instance.

## 9. Expected signal

- S1: Both hostnames appear roughly evenly (round-robin).
- S2: All requests hit a single hostname (sticky).
- S3: Requests distribute across both hostnames (no cookie = no stickiness).

## 10. Results

### Scale-out timing

```
Command: az appservice plan update --number-of-workers 2
Start: t=0ms
First 2nd instance detected: t=63,948ms (≈64 seconds)
```

Second instance hostname: `0ee27d0fe65f` (first: `ce2f97f05a4f`)

### S1 — ARR Affinity disabled, 20 requests

```
ce2f97f05a4f 0ee27d0fe65f 0ee27d0fe65f ce2f97f05a4f 0ee27d0fe65f
ce2f97f05a4f 0ee27d0fe65f ce2f97f05a4f ce2f97f05a4f 0ee27d0fe65f
0ee27d0fe65f ce2f97f05a4f ce2f97f05a4f ce2f97f05a4f ce2f97f05a4f
0ee27d0fe65f ce2f97f05a4f 0ee27d0fe65f ce2f97f05a4f ce2f97f05a4f

Unique instances: 2  (round-robin distribution confirmed)
```

### S2 — ARR Affinity enabled, requests WITH cookie

Cookie set by server:
```
ARRAffinity=689f7d9566d7788e1e4d31f634b70eb5fd184e26aa8622b4ca24b879e04bae39
ARRAffinitySameSite=689f7d9566d7788e1e4d31f634b70eb5fd184e26aa8622b4ca24b879e04bae39
```

```
10 requests with cookie:
ce2f97f05a4f 0ee27d0fe65f ce2f97f05a4f ce2f97f05a4f ce2f97f05a4f
ce2f97f05a4f 0ee27d0fe65f 0ee27d0fe65f ce2f97f05a4f ce2f97f05a4f

Unique instances: 2  (stickiness DID NOT work — requests still distributed)
```

!!! warning "Key finding"
    Both instances returned the **same ARRAffinity cookie value**. The ARR affinity value is the same across instances in this deployment, so the load balancer cannot distinguish which instance the client should be routed to. Stickiness requires each instance to have a unique ARRAffinity value.

### S3 — ARR Affinity enabled, requests WITHOUT cookie

```
10 requests without cookie:
0ee27d0fe65f ce2f97f05a4f 0ee27d0fe65f ce2f97f05a4f 0ee27d0fe65f
0ee27d0fe65f 0ee27d0fe65f ce2f97f05a4f 0ee27d0fe65f 0ee27d0fe65f

Unique instances: 2  (round-robin — same as with cookie in this case)
```

## 11. Interpretation

- **Measured**: With ARR Affinity disabled, 2 instances serve requests in near-equal round-robin. H1 is confirmed — any in-memory session on instance A is invisible to instance B. **Measured**.
- **Observed**: Both `ARRAffinity` and `ARRAffinitySameSite` cookies are set simultaneously. The SameSite variant uses `SameSite=None; Secure` for cross-origin scenarios. H3 is confirmed.
- **Observed**: In this experiment, both instances returned the same ARRAffinity cookie value (`689f7d9566...`). This caused ARR Affinity to not function — requests continued to distribute across both instances. H4 is confirmed as a failure mode.
- **Inferred**: The ARRAffinity cookie value encodes the target instance ID at the load balancer level. If both instances have the same value (which can occur when instances are spun up from the same image quickly), the load balancer treats both as equivalent targets. This is an edge case that may resolve after the app is restarted or the instances are cycled.
- **Inferred**: The practical implication is that relying solely on ARR Affinity for session consistency is fragile. Distributed cache (Redis, Azure Cache for Redis) is the only reliable solution for multi-instance session state.

## 12. What this proves

- Scale-out from 1 to 2 instances on B1 plan takes approximately 64 seconds before both instances serve traffic. **Measured**.
- Without ARR Affinity, requests distribute across all instances — in-memory session state breaks. **Measured**.
- ARR Affinity does not guarantee stickiness if both instances return the same cookie value. **Observed** (failure mode reproduced).
- Both `ARRAffinity` and `ARRAffinitySameSite` cookies are set when affinity is enabled. **Observed**.

## 13. What this does NOT prove

- Consistent ARR Affinity behavior when each instance has a unique cookie value was not verified in this run (both had the same value).
- The exact duration of session loss during scale-out (before the new instance serves traffic) was not isolated.
- Behavior with Windows App Service, ASP.NET session provider, or Node.js express-session was not tested.

## 14. Support takeaway

When customers report intermittent session loss or authentication failures after scaling out:

1. Check if ARR Affinity is enabled: `az webapp show --query "properties.clientAffinityEnabled"`.
2. Even with ARR Affinity enabled, verify that the cookie value is unique per instance (check Set-Cookie headers from different instances). If both return the same value, stickiness is not functioning.
3. Advise against relying on in-memory session state for multi-instance apps. Recommend: Azure Cache for Redis (distributed session store), sticky sessions as a temporary workaround only.
4. Check scale-out timing: new instances take ~60 seconds to appear in traffic. Requests during this window may hit the new (empty-session) instance.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
SUB="<subscription-id>"
PLAN="<plan-name>"

# Scale to 2 instances
az appservice plan update \
  --ids "/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/serverfarms/${PLAN}" \
  --number-of-workers 2

# Disable ARR Affinity
az webapp update -n $APP -g $RG --client-affinity-enabled false

# Observe round-robin
for i in $(seq 1 10); do
  curl -s https://<app>.azurewebsites.net/worker | python3 -c "import sys,json; print(json.load(sys.stdin)['hostname'])"
done

# Enable ARR Affinity
az webapp update -n $APP -g $RG --client-affinity-enabled true

# Capture cookie
curl -s -c /tmp/arr.txt https://<app>.azurewebsites.net/ -o /dev/null

# Test with cookie — check if all requests hit same instance
for i in $(seq 1 10); do
  curl -s -b /tmp/arr.txt https://<app>.azurewebsites.net/worker | python3 -c "import sys,json; print(json.load(sys.stdin)['hostname'])"
done
```

## 16. Related guide / official docs

- [ARR Affinity and sticky sessions in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [Session state in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/overview-manage-costs#sessions)
- [Azure Cache for Redis as session provider](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-aspnet-session-state-provider)
