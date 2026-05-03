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

# Thread Pool Exhaustion Under Synchronous I/O

!!! info "Status: Planned"

## 1. Question

When an App Service application uses a synchronous I/O pattern on a framework with a bounded thread pool (e.g., ASP.NET Core ThreadPool, Python WSGI with gunicorn workers), and inbound requests block on slow external dependencies, at what point does thread pool exhaustion occur and how does it manifest differently from CPU exhaustion or memory pressure?

## 2. Why this matters

Thread pool exhaustion is a common and subtle failure mode in server-side applications. When all threads are blocked waiting for I/O (slow database, external API, or network timeout), new inbound requests queue up and eventually time out. The failure looks like a slow or unresponsive application, but CPU and memory metrics remain low — there is no CPU spike and no OOM event. This leads to incorrect diagnoses and ineffective remediations (scaling up when the actual fix is async I/O or connection pool tuning).

## 3. Customer symptom

"The app becomes unresponsive under moderate load even though CPU and memory are fine" or "Requests queue up and time out but we have plenty of resources" or "Response times increase linearly with concurrency until everything stops."

## 4. Hypothesis

- H1: When a gunicorn WSGI app is configured with `workers=2` and each worker handles one request at a time, only 2 concurrent requests can be in flight. A third concurrent request must wait for an available worker. If requests take 5 seconds (due to a slow upstream call), throughput is limited to `workers / request_duration = 0.4 req/s` regardless of CPU capacity.
- H2: When worker count is increased to match expected concurrency, the issue resolves. Alternatively, using `gevent` or `asyncio` workers allows a single worker to handle many concurrent I/O-bound requests.
- H3: Thread pool exhaustion is visible as a `RequestQueueLength` spike in Azure Monitor (for Windows apps) or as request wait time in Application Insights (end-to-end transaction duration with long "waiting for dependency" spans).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P2v3 |
| Region | Korea Central |
| Runtime | Python 3.11 (gunicorn) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance / Runtime

**Controlled:**

- gunicorn with `workers=2` (sync worker class)
- External endpoint with configurable delay (simulating slow dependency)
- Load generator with configurable concurrency

**Observed:**

- Successful request rate at different concurrency levels
- Request queue depth
- CPU and memory during exhaustion

**Scenarios:**

- S1: 2 workers, 1 concurrent request, 5s dependency → baseline (no queue)
- S2: 2 workers, 10 concurrent requests, 5s dependency → queue exhaustion
- S3: 10 workers, 10 concurrent requests, 5s dependency → no queue
- S4: 2 workers with gevent, 10 concurrent requests, 5s dependency → async handles concurrency

## 7. Instrumentation

- Application Insights dependency tracking (request duration breakdown)
- `AppServiceHTTPLogs` — request wait time (`TimeTaken` vs. actual dependency duration)
- gunicorn access log for worker utilization
- `ps aux` via Kudu SSH during load to observe worker states (R vs. S)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy gunicorn app with a `/slow?delay=5` endpoint that calls an external URL with a 5-second delay.
2. S1: 2 workers, send 1 concurrent request; verify 5s response time, 0 queuing.
3. S2: 2 workers, send 10 concurrent requests via `ab -c 10`; observe response times (first 2 complete in 5s, remaining queue up in 5s increments → last request takes 25s).
4. S3: Restart with `--workers=10`; repeat S2; verify all 10 complete in ~5s.
5. S4: Restart with `--worker-class=gevent --workers=1`; repeat S2; verify concurrency handled within one worker.

## 9. Expected signal

- S1: All requests complete in ~5s; no queuing.
- S2: First 2 requests complete at t=5s; requests 3-4 complete at t=10s; requests 9-10 complete at t=25s. CPU remains <20%.
- S3: All 10 requests complete at approximately t=5s regardless of concurrency.
- S4: All 10 requests complete at approximately t=5s with 1 gevent worker.

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

- gunicorn sync workers are single-threaded. Each worker handles exactly one request at a time.
- For I/O-bound applications, use `--worker-class=gevent` or `--worker-class=gthread` with `--threads=N`.
- The number of gunicorn workers is set via `GUNICORN_CMD_ARGS` app setting or the startup command.

## 16. Related guide / official docs

- [gunicorn worker types](https://docs.gunicorn.org/en/stable/design.html#worker-types)
- [Configure Python app for App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)
- [Application Insights dependency tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-dependencies)
