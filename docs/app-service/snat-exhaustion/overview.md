---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-10
    cli_version: "2.73.0"
    core_tools_version: null
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# SNAT Exhaustion Without High CPU

!!! info "Status: Published"
    Experiment completed with real data collected on 2026-04-10 from Azure App Service B1 (koreacentral).
    Fifteen test runs across 5 configurations (3 runs each, randomized order). Hypothesis confirmed — SNAT exhaustion causes connection failures with CPU/memory completely normal.

## 1. Question

Can SNAT port exhaustion cause connection failures and latency spikes on App Service even when CPU and memory metrics remain normal, and does connection pooling prevent the exhaustion?

## 2. Why this matters

Support engineers naturally check CPU and memory first when customers report intermittent connection failures. SNAT exhaustion is invisible in those metrics — it manifests only as `TimeoutError` or `SocketException` in application logs, with no corresponding resource pressure. Without understanding SNAT mechanics, engineers waste hours debugging application code that is actually working correctly.

### Background: How SNAT Works on App Service

Azure App Service uses **Source Network Address Translation (SNAT)** for outbound connections. Each instance receives a pool of **~128 preallocated SNAT ports** per destination IP:port tuple. When the application opens more concurrent outbound connections than available ports, new connections fail or queue until ports are released.

```text
┌──────────────────────────────────────────────────────────┐
│  App Service Instance (B1, single)                       │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  SNAT Port Pool: ~128 ports per destination IP:port │ │
│  │  ┌───┐┌───┐┌───┐┌───┐         ┌───┐                │ │
│  │  │ 1 ││ 2 ││ 3 ││ 4 │  ...    │128│                │ │
│  │  └─┬─┘└─┬─┘└─┬─┘└─┬─┘         └─┬─┘                │ │
│  └────┼────┼────┼────┼─────────────┼────────────────────┘ │
│       │    │    │    │             │                      │
│       ▼    ▼    ▼    ▼             ▼                      │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Azure Load Balancer (SNAT)                         │ │
│  │  Maps: instance_ip:ephemeral → public_ip:port       │ │
│  └─────────────────────┬───────────────────────────────┘ │
└────────────────────────┼─────────────────────────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │  Target Server  │
                │  (single IP)    │
                └─────────────────┘
```

**Without connection pooling**, each HTTP request creates a new TCP connection → consumes 1 SNAT port for the duration of the request + TIME_WAIT period (~4 minutes). With a 10-second target response time and 200 concurrent workers, all 200 workers need simultaneous SNAT ports.

**With connection pooling**, workers reuse existing TCP connections → a single persistent connection can serve many sequential requests, consuming only 1 SNAT port across hundreds of requests.

## 3. Customer symptom

- "My app randomly fails to connect to external APIs, but CPU is only at 20%."
- "We see intermittent `TimeoutError` or `ConnectionError` in our logs."
- "The problem comes and goes — sometimes 5% of requests fail, sometimes 50%."
- "Adding more instances didn't help" (each instance has its own SNAT pool — if each instance makes the same number of outbound connections, scaling out doesn't solve the per-instance exhaustion).

## 4. Hypothesis

**H1 — Threshold exists**: When an App Service instance opens more than ~128 concurrent outbound TCP connections to a single destination IP:port without connection pooling, connection failures begin.

**H2 — CPU/memory independent**: SNAT exhaustion occurs with CPU under 35% and memory unchanged, proving it is a network-layer constraint invisible to standard resource metrics.

**H3 — Pooling prevents exhaustion**: Connection pooling (reusing TCP connections) eliminates SNAT exhaustion even at 200 concurrent workers, because pooled connections share a small number of SNAT ports.

**H4 — High variance**: Failure rates are non-deterministic — SNAT port availability depends on TIME_WAIT recycling timing, producing high variance across identical test runs.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (1 instance, Linux) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Source App | `app-snat-source` (stdlib http.client + ThreadPoolExecutor) |
| Target App | `app-snat-target` (Flask + gunicorn gthread, 2 workers × 250 threads) |
| Deployment | ZIP Deploy with Oryx build |
| Date tested | 2026-04-10 |

**Architecture:**

| Component | Startup Command | Purpose |
|-----------|----------------|---------|
| Source | `gunicorn --bind=0.0.0.0 --timeout 600 --workers 1 app:app` | SNAT test client — launches N threads, each opening outbound connections |
| Target | `gunicorn --bind=0.0.0.0 --timeout 300 --workers 2 --worker-class gthread --threads 250 app:app` | Slow-response server — `/delay?seconds=10` holds connections open |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Concurrent outbound connections: 50, 128, 200, 300
- Connection pooling: disabled (Connection: close) vs enabled (Connection: keep-alive)
- Target response delay: 10 seconds (holds SNAT port for duration)
- Single destination IP (target app resolved to 1 IP address)
- Single source instance (B1, autoscale off)

**Observed:**

- Connection failure rate (per run)
- Response latency: p50, p95, p99
- CPU percentage (before and after each run)
- Memory percentage (before and after each run)
- TCP connection states via `/proc/net/tcp` (ESTABLISHED, TIME_WAIT, etc.)
- Error types and phases (connect vs request vs read)

**Independent run definition**: 4-minute cooldown between runs (SNAT port reclaim), randomized run order to avoid systematic bias

**Runs per configuration**: 3

**Warm-up exclusion rule**: First 10 seconds of each run excluded from measurement

**Primary metric**: Connection failure rate; meaningful effect threshold: 1 percentage point

**Comparison method**: Direct comparison across configurations (0% vs non-zero failure rate)

## 7. Instrumentation

- **Source application**: Custom Flask app using `http.client.HTTPSConnection` + `concurrent.futures.ThreadPoolExecutor` with `threading.Barrier` for synchronized start
- **Target application**: Flask app with `/delay?seconds=N` endpoint using `time.sleep()` (gthread worker handles concurrency)
- **Per-request telemetry**: worker ID, timestamp, latency (ms), success/failure, error type, error phase (connect/request/read), HTTP status code
- **System metrics**: CPU/memory from `/proc/stat` and `/proc/meminfo`, TCP states from `/proc/net/tcp` and `/proc/net/tcp6`
- **Connection isolation (no-pool mode)**: Each request creates a new `HTTPSConnection` with `Connection: close` header — guarantees 1 SNAT port per concurrent request
- **Connection reuse (pool mode)**: Each worker maintains a persistent `HTTPSConnection` with `Connection: keep-alive` — SNAT ports shared across sequential requests
- **Test runner**: Automated Python script with randomized run order, 4-minute cooldowns, and JSON output per run

## 8. Procedure

### Step 1: Deploy test infrastructure

```bash
az group create --name rg-snat-lab --location koreacentral

az appservice plan create --name plan-snat \
    --resource-group rg-snat-lab --sku B1 --is-linux \
    --number-of-workers 1

az webapp create --name app-snat-target \
    --resource-group rg-snat-lab \
    --plan plan-snat --runtime "PYTHON:3.11"

az webapp create --name app-snat-source \
    --resource-group rg-snat-lab \
    --plan plan-snat --runtime "PYTHON:3.11"

az webapp config set --name app-snat-target \
    --resource-group rg-snat-lab \
    --startup-file "gunicorn --bind=0.0.0.0 --timeout 300 --workers 2 --worker-class gthread --threads 250 app:app"

az webapp config set --name app-snat-source \
    --resource-group rg-snat-lab \
    --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 --workers 1 app:app"

az webapp config appsettings set --name app-snat-source \
    --resource-group rg-snat-lab \
    --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true

az webapp config appsettings set --name app-snat-target \
    --resource-group rg-snat-lab \
    --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true

az webapp deploy --name app-snat-target \
    --resource-group rg-snat-lab \
    --src-path snat-target.zip --type zip

az webapp deploy --name app-snat-source \
    --resource-group rg-snat-lab \
    --src-path snat-source.zip --type zip
```

### Step 2: Verify both apps are healthy

```bash
curl https://app-snat-source.azurewebsites.net/healthz
curl "https://app-snat-target.azurewebsites.net/delay?seconds=1"
```

### Step 3: Run automated test matrix

```bash
python3 snat-runner.py
```

The runner executes 15 runs (5 configs × 3 runs) in randomized order with 4-minute cooldowns between runs. Each run consists of 10 seconds warmup + 60 seconds measurement.

### Step 4: Clean up

```bash
az group delete --name rg-snat-lab --yes --no-wait
```

## 9. Expected signal

- Connection failure rate = 0% at 50 and 128 concurrent connections (within SNAT budget)
- Connection failure rate > 0% at 200 and 300 concurrent connections (exceeds SNAT budget)
- CPU stays under 35% across all configurations
- Memory stays under 85% across all configurations
- Connection pooling at 200 connections → 0% failures (same workers, shared ports)
- All failures are `TimeoutError` in the `request` phase (connection establishment)
- High variance in failure rates across runs at 200+ connections

## 10. Results

### 10.1 Summary Table

| Config | Connections | Pool | Run 1 | Run 2 | Run 3 | Median Failure Rate |
|--------|------------|------|-------|-------|-------|-------------------|
| 50conn_nopool | 50 | No | 0.000% | 0.000% | 0.000% | **0.000%** |
| 128conn_nopool | 128 | No | 0.000% | 0.000% | 0.000% | **0.000%** |
| 200conn_nopool | 200 | No | 22.222% | 7.543% | 6.923% | **7.543%** |
| 300conn_nopool | 300 | No | 49.312% | 11.325% | 19.142% | **19.142%** |
| 200conn_pool | 200 | Yes | 0.000% | 0.000% | 0.000% | **0.000%** |

### 10.2 Latency Distribution (p50, milliseconds)

| Config | Run 1 | Run 2 | Run 3 | Baseline |
|--------|-------|-------|-------|----------|
| 50conn_nopool | 10,102 | 10,076 | 10,195 | ~10,000 (= target delay) |
| 128conn_nopool | 10,149 | 10,061 | 10,075 | ~10,000 |
| 200conn_nopool | **29,540** | 10,355 | 10,564 | ~10,000 |
| 300conn_nopool | **24,689** | 10,185 | **12,854** | ~10,000 |
| 200conn_pool | 10,048 | 10,034 | 10,015 | ~10,000 |

!!! tip "How to read this"
    The baseline latency is ~10,000ms (matching the 10-second target delay). Any p50 significantly above 10,000ms indicates SNAT port queuing — connections are waiting for ports to become available before the TCP handshake can begin. The 29,540ms p50 in 200conn_nopool_run1 means half of all requests waited ~20 seconds for a SNAT port before the actual 10-second request.

### 10.3 CPU and Memory (Proving Resource Independence)

| Config | CPU Before | CPU After | Memory Before | Memory After |
|--------|-----------|-----------|---------------|--------------|
| 50conn_nopool | 29.7–32.2% | 29.6–32.1% | 76.8–79.2% | 78.0–79.2% |
| 128conn_nopool | 29.2–32.9% | 29.2–33.0% | 75.8–81.4% | 76.3–81.5% |
| 200conn_nopool | 29.4–30.3% | 29.5–30.2% | 76.2–78.3% | 78.1–80.1% |
| 300conn_nopool | 31.4–32.5% | 31.3–32.6% | 77.9–80.4% | 80.9–81.9% |
| 200conn_pool | 30.6–33.4% | 30.6–33.3% | 78.8–82.3% | 78.6–83.7% |

!!! tip "How to read this"
    CPU never exceeded 33.4% and memory never exceeded 83.7% across ALL configurations — including 300 concurrent connections with 49% failure rate. SNAT exhaustion is completely invisible in standard resource metrics. A support engineer checking only CPU/memory dashboards would see "everything is fine" while nearly half of outbound connections fail.

### 10.4 Error Classification

All 1,144 failures across all configurations shared the same characteristics:

| Property | Value |
|----------|-------|
| Error type | `TimeoutError` |
| Error phase | `request` (connection establishment) |
| Error count | 1,144 total across 6 affected runs |
| HTTP status | None (connection never completed) |

No `ConnectionRefusedError`, no `OSError`, no TLS errors. The uniform `TimeoutError` in the `request` phase confirms these are SNAT port exhaustion failures — the TCP SYN cannot be sent because no SNAT port is available.

### 10.5 Variance Analysis

The 200 and 300 connection configurations showed significant variance across runs:

| Config | Min Failure Rate | Max Failure Rate | Range |
|--------|-----------------|-----------------|-------|
| 200conn_nopool | 6.923% | 22.222% | 15.3 pp |
| 300conn_nopool | 11.325% | 49.312% | 38.0 pp |

!!! warning "High Run-to-Run Variance"
    The 300conn_nopool configuration produced failure rates ranging from 11% to 49% across three identical runs. This variance is inherent to SNAT exhaustion — port availability depends on TIME_WAIT recycling timing, load balancer state, and platform-level port allocation algorithms. **A single test run is insufficient to characterize SNAT behavior.** Multiple runs with proper cooldowns are required.

### 10.6 Connection Pooling: Direct Comparison at 200 Connections

| Metric | 200conn_nopool (median) | 200conn_pool (median) | Delta |
|--------|------------------------|----------------------|-------|
| Failure rate | 7.543% | 0.000% | **-7.5 pp** |
| p50 latency | 10,564ms | 10,034ms | -530ms |
| Total requests (60s) | 928 | 1,200 | +29% throughput |
| TCP TIME_WAIT post | 0–2 | 200 | — |

!!! tip "How to read this"
    Same number of concurrent workers (200), same target, same duration — but connection pooling eliminated all failures, reduced latency, and increased throughput by 29%. The 200 TIME_WAIT connections in pool mode reflect the worker count, not port exhaustion — these are connections being recycled by the pool.

## 11. Interpretation

**H1 — Threshold exists: CONFIRMED.** The boundary lies between 128 and 200 concurrent connections. At 128 connections without pooling, all three runs showed 0% failure rate with baseline latency. At 200 connections, all three runs showed failures (6.9–22.2%). This aligns with the documented ~128 SNAT port preallocated limit per destination IP:port.

**H2 — CPU/memory independent: CONFIRMED.** CPU ranged from 29.2% to 33.4% and memory from 75.8% to 83.7% across all configurations — including the 300-connection test with 49.3% failure rate. SNAT exhaustion produces zero signal in standard resource metrics.

**H3 — Pooling prevents exhaustion: CONFIRMED.** At 200 concurrent workers, connection pooling produced 0.000% failure rate across all 3 runs, while the identical worker count without pooling produced 6.9–22.2% failure rates. Connection pooling is a complete mitigation.

**H4 — High variance: CONFIRMED.** The 300-connection configuration showed failure rates ranging from 11.3% to 49.3% across three runs with identical parameters and 4-minute cooldowns. This variance is inherent to SNAT mechanics and makes single-run testing unreliable.

### Key Discovery: SNAT Exhaustion is a Soft Cliff, Not a Hard Wall

At 128 connections (the documented preallocated limit), we observed 0% failures — suggesting the platform can allocate additional ports beyond the preallocated pool when capacity exists. The exhaustion becomes probabilistic: at 200 connections, some runs show 7% failures while others show 22%, depending on port availability at the moment of the test.

### Key Discovery: Failure Phase Matters

All failures occurred in the `request` phase (TCP connection establishment), not the `read` phase. This means the application's HTTP handler never ran — the connection was rejected at the SNAT layer before any application-level communication occurred. This is why application-level retries won't help unless they include a backoff period long enough for ports to become available.

## 12. What this proves

!!! success "Evidence level: Statistical (3 independent runs per config, randomized order)"

1. **SNAT exhaustion causes connection failures between 128 and 200 concurrent outbound connections** per destination IP:port on App Service B1
2. **CPU and memory remain completely normal** during SNAT exhaustion (29–34% CPU, 76–84% memory with up to 49% failure rate)
3. **Connection pooling is a complete mitigation** — 200 concurrent workers with pooling: 0% failures; without pooling: 7.5% median failure rate
4. **Failure rates are highly variable** across identical runs (11–49% range at 300 connections), making single-run testing misleading
5. **All failures are TimeoutError in the request phase** — connection establishment fails, not request processing
6. **Pooling increases throughput by ~29%** (1,200 vs 928 requests in 60 seconds) because it avoids TCP handshake overhead

## 13. What this does NOT prove

- **Exact SNAT port limit**: The preallocated limit is documented as ~128, but the actual failure threshold depends on platform-level port allocation and recycling. We proved failures begin between 128 and 200, not that the exact boundary is 128.
- **Premium/Dedicated plan behavior**: B1 may have different SNAT allocation than P1v3, Premium, or Consumption plans. The documented limits vary by plan tier.
- **Multi-destination behavior**: We tested a single destination IP:port. SNAT ports are allocated per-destination, so an application connecting to 10 different APIs has 10× the budget.
- **VNet integration effect**: With VNet integration and NAT Gateway, SNAT behavior changes entirely. This experiment covers only the default (non-VNet) path.
- **Long-term accumulation**: Each test ran for 60 seconds. Production workloads that slowly accumulate connections over hours may exhibit different failure patterns.
- **Platform variation**: Azure's SNAT allocation may vary by region, time of day, or platform load. Our results are from Korea Central on a single day.

## 14. Support takeaway

!!! abstract "For support engineers"

    **When a customer reports "intermittent connection failures with normal CPU/memory":**

    1. **Check outbound connection count** — not CPU/memory. Use Azure Monitor `TcpConnectionsOutbound` metric or Application Insights dependency failure counts
    2. **Count concurrent connections per destination** — ask "How many simultaneous outbound connections does your app make to a single IP?" If >100, SNAT is likely
    3. **Check for connection pooling** — the #1 mitigation. An `HttpClient` per request (C#), `requests.get()` in a loop (Python), or `new URL().openStream()` (Java) all create individual connections

    **Key mitigations (in order of preference):**

    1. **Connection pooling**: Reuse HTTP connections via `HttpClientFactory` (.NET), `requests.Session` (Python), or connection pool libraries. This is a complete fix.
    2. **VNet integration + NAT Gateway**: Provides a dedicated outbound IP with 64,000 ports, eliminating SNAT entirely
    3. **Service Endpoints / Private Endpoints**: Route traffic within the Azure backbone, bypassing SNAT
    4. **Reduce connection hold time**: Shorter timeouts, smaller payloads, faster downstream services

    **Anti-pattern: creating a new connection per request**

    ```python
    # ❌ BAD: Each request consumes 1 SNAT port for ~4 minutes (TIME_WAIT)
    for item in items:
        response = requests.get(f"https://api.example.com/items/{item}")

    # ✅ GOOD: Session reuses TCP connections via keep-alive
    session = requests.Session()
    for item in items:
        response = session.get(f"https://api.example.com/items/{item}")
    ```

## 15. Reproduction notes

- SNAT port allocation varies by App Service plan tier — B1 was used here; Premium plans may have different limits
- The target server must support sufficient concurrency (we used gunicorn gthread with 500 total threads) to avoid confusing server-side capacity limits with SNAT exhaustion
- A 4-minute cooldown between runs is essential — SNAT ports in TIME_WAIT take ~4 minutes to reclaim
- Randomize run order to avoid systematic bias from TIME_WAIT port accumulation
- Using `stdlib http.client` instead of `aiohttp` eliminates external dependencies and ensures each thread creates a genuine TCP connection (no connection multiplexing)
- `threading.Barrier` synchronizes thread starts to maximize concurrent SNAT port pressure
- The source app uses `Connection: close` (no-pool mode) or `Connection: keep-alive` (pool mode) headers to explicitly control TCP connection reuse
- Test application source code is available in the `data/app-service/snat-exhaustion/` directory
- Monitor `TimeoutError` counts, not HTTP error codes — SNAT failures occur before HTTP negotiation

## 16. Related guide / official docs

- [Troubleshoot outbound connection errors - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-intermittent-outbound-connection-errors)
- [SNAT for outbound connections - Azure Load Balancer](https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-outbound-connections)
- [Use NAT gateway for outbound traffic - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/networking/nat-gateway-integration)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
