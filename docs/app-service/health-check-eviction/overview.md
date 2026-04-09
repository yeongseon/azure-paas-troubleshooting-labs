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

# Health Check Eviction on Partial Dependency Failure

!!! info "Status: Planned"

## 1. Question

When an App Service health check endpoint returns unhealthy because a single downstream dependency (e.g., database) is unreachable, does the platform evict the instance even though the application itself is running and could serve requests that don't require that dependency?

## 2. Why this matters

Customers implement health check endpoints that validate all dependencies. When one dependency fails, the health check returns unhealthy, and the platform removes the instance from the load balancer rotation. This can cascade — if the unhealthy dependency affects all instances equally, every instance gets evicted, causing a full outage for a partial dependency failure.

## 3. Customer symptom

- "Our app went completely down, but only the database was unreachable for 2 minutes."
- "Health check keeps failing and instances keep getting removed and re-added."
- "We see instance cycling in the health check blade even though the app is fine."

## 4. Hypothesis

When a health check endpoint depends on an external service and that service becomes unreachable, App Service will evict the instance after the configured failure threshold, even if the instance is otherwise healthy. If all instances share the same dependency, this creates a cascading eviction that amplifies a partial outage into a full outage.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | P1v3 (2 instances) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Health check path and response logic
- Dependency failure simulation (block outbound to database endpoint)
- Instance count (2)
- Health check failure threshold (default: 10 consecutive failures)

**Observed:**

- Instance eviction events (Activity Log)
- Health check status timeline
- Request routing behavior during eviction
- User-facing error rate

## 7. Instrumentation

- Azure Portal: Health Check blade, Activity Log
- Application Insights: request traces, availability
- Application logging: health check execution details
- Azure Monitor: `HealthCheckStatus`, `Http5xx`

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Health check returns unhealthy after dependency block
- Instance removed from rotation after ~10 consecutive failures (~10 minutes with 1-minute interval)
- If both instances fail simultaneously, brief period of zero healthy instances
- Requests return 503 during eviction window

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

- Health check interval is 1 minute by default; eviction happens after configurable consecutive failures
- The `/healthz` path must return 200 to be considered healthy
- Test with 2+ instances to observe differential eviction behavior

## 16. Related guide / official docs

- [Health check - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
