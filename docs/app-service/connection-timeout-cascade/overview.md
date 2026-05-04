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

# Connection Timeout Cascade

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

When an outbound dependency (database, API) becomes unavailable, how do connection timeouts propagate through the request stack in App Service? Does thread exhaustion or connection pool saturation occur before the outbound timeout fires, and how quickly does the cascading failure affect inbound request availability?

## 2. Why this matters

Cascading failures triggered by a single slow or unavailable dependency are one of the most common patterns in App Service support escalations. Customers expect that a database going offline for 30 seconds will cause brief errors, then recovery. In practice, the thread pool or connection pool exhaustion caused by pending requests waiting on the timeout can extend the outage significantly beyond the dependency recovery time.

The diagnostic challenge is that all standard metrics (CPU, memory) appear normal while threads are exhausted — the app is not doing work, it is waiting. This experiment characterizes the cascade timing.

## 3. Customer symptom

- "Our database went offline for 30 seconds but the app was broken for 5 minutes."
- "After our database came back, the app didn't recover for a long time."
- "We see timeouts even though the database is responding."
- "CPU is at 5% but users are getting 503 errors."

## 4. Hypothesis

**H1 — Thread saturation precedes timeout**: Python (threaded) Flask app with 10 worker threads will reach thread saturation within `thread_count × connection_timeout` seconds of the dependency becoming unavailable. After thread saturation, inbound requests receive 503 errors even though the dependency has recovered.

**H2 — Connection pool hold**: If a connection pool (e.g., SQLAlchemy pool size 5) is used, the pool holds connections in pending state during the timeout window. New requests queue waiting for a pool slot rather than failing immediately.

**H3 — Recovery lag**: After the dependency becomes available again, recovery requires: timeout to fire, thread to release, connection pool to reset. This recovery lag can be 2–3× the configured timeout.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Linux |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Failure Injection + Latency

**Controlled:**

- Number of worker threads (Gunicorn workers × threads)
- Database connection timeout (5s, 15s, 30s)
- Connection pool size (1, 5, 10)
- Dependency outage duration (10s, 30s, 60s)
- Inbound request rate (10 req/s, 50 req/s)

**Observed:**

- Inbound request success rate during and after outage
- Response latency p50/p95/p99
- Thread pool utilization (via `/proc` or psutil)
- Time from dependency recovery to full inbound request recovery

## 7. Instrumentation

- App Insights: request success/failure rate, dependency call failure
- Custom `/metrics` endpoint: active thread count, connection pool state
- Gunicorn stats endpoint (if enabled)
- External load generator: `hey` or `ab` sending requests throughout the experiment

**Key KQL query:**

```kusto
requests
| where timestamp > ago(1h)
| summarize 
    success_rate = 100.0 * countif(success == true) / count(),
    p95_ms = percentile(duration, 95)
  by bin(timestamp, 10s)
| order by timestamp asc
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az group create --name rg-timeout-cascade --location koreacentral
az appservice plan create --name plan-timeout --resource-group rg-timeout-cascade --sku B1 --is-linux
az webapp create --name app-timeout-cascade --resource-group rg-timeout-cascade --plan plan-timeout --runtime "PYTHON:3.11"
```

### 8.2 Application Design

Flask app with:
- Configurable connection timeout via env var `CONN_TIMEOUT_S`
- Simulated dependency: `time.sleep(timeout)` to simulate a slow/hung dependency
- Toggle via app setting: `DEPENDENCY_BLOCKED=true/false`
- `/metrics` endpoint: active thread count, pending requests

### 8.3 Scenarios

**S1 — Baseline**: Healthy dependency, 10 req/s for 60s. Establish baseline latency and thread counts.

**S2 — Short outage (30s), fast timeout (5s)**: Block dependency for 30s, timeout=5s. Measure cascade depth and recovery time.

**S3 — Short outage (30s), slow timeout (30s)**: Block dependency for 30s, timeout=30s. At 30s outage × N threads, measure when thread saturation occurs.

**S4 — Recovery lag measurement**: After dependency recovers, measure seconds until success_rate returns to >95%.

## 9. Expected signal

- **S2**: Thread saturation at ~2 seconds (10 threads × 5s timeout / 10 req/s). Recovery within 10s of dependency recovery.
- **S3**: Thread saturation within 1 second (10 req/s × 1 thread/req, 30s timeout → queue builds fast). Extended outage.
- **S4**: Recovery lag = time for pending requests to timeout + connection pool reset time.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Python with GIL has different thread saturation characteristics than Java or .NET apps.
- The experiment uses simulated latency, not real network packet drops; TCP keepalive and socket timeout behavior may differ.
- B1 has 1 core, limiting parallel thread execution to platform scheduling.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Thread saturation causes 503s before timeout fires | **Inferred** |
| Recovery takes longer than the outage duration | **Inferred** |
| Connection pool size affects cascade depth | **Unknown** |

## 14. Related experiments

- [SNAT Exhaustion](../snat-exhaustion/overview.md) — outbound connection exhaustion
- [Thread Pool Exhaustion](https://github.com/yeongseon/azure-paas-troubleshooting-labs) — thread pool limits
- [Slow Requests](../slow-requests/overview.md) — dependency latency vs. worker-side delay

## 15. References

- [Azure App Service connection limits](https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans)
- [Cascading failures pattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)

## 16. Support takeaway

When investigating cascading outages caused by dependency failures:

1. Check the configured connection timeout on all outbound calls — a 30s timeout with 10 workers means full saturation in ~10 seconds of dependency unavailability.
2. Look for the characteristic pattern: CPU near 0% with high 5xx error rate. This is the signature of thread/connection exhaustion while waiting for timeouts.
3. After dependency recovery, monitor for the "recovery lag" — requests may fail for 1–2× the timeout duration while pending threads drain.
4. Recommend circuit breakers (Polly for .NET, tenacity for Python) to fail fast and preserve thread capacity during dependency outages.
