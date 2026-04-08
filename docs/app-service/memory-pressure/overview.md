# Memory Pressure on Shared App Service Plans

!!! info "Status: Published"
    Experiment completed with real data collected on 2026-04-02 from Azure App Service B1 (koreacentral).
    Runtime comparison includes Flask/ZIP Deploy and Node.js/Custom Container variants.

## 1. Question

When multiple applications share a single Azure App Service Plan and aggregate memory utilization climbs above 85%, what breaks first? Does steady-state request latency degrade, or do failures only appear during state transitions such as startup, restart, and scaling events? And does the Linux kernel's page reclaim machinery (kswapd, direct reclaim, swap I/O) impose a measurable CPU tax even when application code is idle?

## 2. Why this matters

Memory pressure on shared App Service Plans is one of the most common sources of Azure support tickets. Customers report "my app is slow but CPU looks normal," or "all apps on the plan went down at the same time." The challenge is that Azure Monitor exposes plan-level averages (`MemoryPercentage`, `CpuPercentage`) that obscure what is actually happening inside the Linux worker: page cache eviction, swap thrashing, cgroup OOM kills, and process restart loops.

Support engineers need to understand the relationship between plan-level metrics and the underlying Linux memory management behavior to give accurate guidance. Without this understanding, engineers may recommend scaling up when the real problem is app density, or dismiss high memory readings as harmless when a restart cascade is imminent.

### Background: How Memory Works on App Service Linux

Azure App Service Linux runs each plan on one or more dedicated VMs (workers). All apps on the plan share the worker's physical RAM and swap space.

**B1 SKU specifications:**

- 1 vCPU (shared with all apps + platform processes)
- 1.75 GB RAM (MemTotal ~1,855 MB as reported by `/proc/meminfo`)
- 2,048 MB swap partition (confirmed via `/proc/meminfo` SwapTotal)
- Single worker instance (no horizontal scaling at B1)

**What consumes memory before your app even starts:**

The platform runtime (App Service sandbox, Kudu/SCM sidecar, container runtime processes) and the Linux page cache consume a significant baseline. In our measurements, a B1 plan with two minimal apps already reports 74-76% `MemoryPercentage` in Azure Monitor. This means your applications are competing for roughly 400-450 MB of effective headroom, not the full 1.75 GB.

**Azure Monitor `MemoryPercentage` is a plan-level average.** It includes kernel page cache (which is reclaimable) and platform overhead (which is not). A reading of 85% does not mean your apps are using 85% of RAM. It means the kernel has allocated 85% of physical pages for something, and you need `/proc/meminfo` or cgroup stats to understand what.

**Deployment mode affects memory accounting.** ZIP-deployed apps run as processes within the platform container. Container-deployed apps (Web App for Containers) run in their own Docker containers with separate cgroup limits. The same `MemoryPercentage` reading can mean very different things depending on deployment mode.

## 3. Customer symptom

- "My app is slow but CPU usage looks normal in the portal."
- "All apps on the plan became slow at the same time. None of them are doing anything unusual."
- "A new app I deployed caused all existing apps to restart."
- "My app takes 5-6 minutes to start after a restart. It used to take 30 seconds."
- "CPU spikes every few minutes but there is no traffic increase."

## 4. Hypothesis

We tested two related hypotheses:

**H1 (Degradation zones):** Increasing memory density on a B1 plan produces three distinct degradation modes, each triggered at different utilization thresholds:

1. **Startup degradation** at 85-90% — cold start times increase proportionally to memory pressure
2. **Capacity cliff** at 85-87% with high app count — new apps cannot start, existing apps show latency increase
3. **Restart cascade** at 93%+ — simultaneous restarts trigger a death spiral with no self-recovery

**H2 (CPU from reclaim):** When plan memory utilization stays above 85% for 30+ minutes with flat traffic, the Linux kernel's page reclaim mechanisms (kswapd, direct reclaim, swap I/O) cause CPU to increase by at least 1.5x, independent of application workload.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 Linux (1 vCPU, 1.75 GB RAM) |
| Region | Korea Central |
| Instance count | 1 (fixed, no autoscale) |
| Date tested | 2026-04-02 |
| Always On | Enabled |

**Experiment A (Flask / ZIP deploy):**

| Parameter | Value |
|-----------|-------|
| Runtime | Python 3.11, Flask + Gunicorn |
| Deployment | ZIP deploy (Oryx build disabled after initial test) |
| App code | Allocates `ALLOC_MB` bytes on startup, serves `/health` and `/ping` |
| Traffic | 1 request per ~10s per app (external curl probe) |
| Duration | ~5 hours (all phases) |

**Experiment B (Node.js / Container deploy, kernel-level instrumentation):**

| Parameter | Value |
|-----------|-------|
| Runtime | Node.js 20 LTS (node:20-slim base image) |
| Deployment | ZIP deploy + Web App for Containers (ACR) |
| App code | Allocates `ALLOC_MB` via Buffer, exposes `/diag/proc` for procfs capture |
| Traffic | 1 request per ~10s per app (steady-traffic.mjs) |
| Duration | ~4-5 hours per deployment mode |
| Instrumentation | `/proc/meminfo`, `/proc/vmstat`, `/proc/pressure/memory`, `process.memoryUsage()` |

## 6. Variables

**Controlled (what we set deliberately):**

- Number of apps on the plan (2, 3, 4, 5, 6, 8)
- Memory allocation per app (`ALLOC_MB`: 50, 75, 100, 125, 150, 175)
- Deployment mode (ZIP deploy vs. Web App for Containers)
- Traffic rate (fixed at ~1 request per 10 seconds per app)
- Plan SKU and instance count (B1, 1 instance, no autoscale)

**Observed (what we measured):**

- Plan `MemoryPercentage` and `CpuPercentage` (Azure Monitor, PT1M)
- Per-app `MemoryWorkingSet`, `AverageResponseTime`, `Http5xx` (Azure Monitor)
- External response latency and HTTP status codes (curl probes)
- Cold start time (time from deployment to first successful health check)
- `/proc/meminfo`: MemFree, MemAvailable, SwapFree, Cached (Node.js experiment only)
- `/proc/vmstat`: pgscan_kswapd, pgscan_direct, pgsteal_kswapd, pswpin, pswpout, allocstall (Node.js experiment only)
- `/proc/pressure/memory`: PSI some/full avg300 (Node.js experiment only)

## 7. Instrumentation

**Azure Monitor metrics** (plan-level, PT1M granularity):

- `MemoryPercentage` — plan-level physical memory usage average across instances
- `CpuPercentage` — plan-level CPU usage average
- `HttpQueueLength`, `DiskQueueLength` — request queueing indicators

**Azure Monitor metrics** (app-level):

- `AverageResponseTime` — server-side response time per app
- `MemoryWorkingSet` — per-app working set in bytes
- `Http5xx` — server error count per app

**External probing** (custom Python script `traffic-gen.py`):

- Curl-based HTTP probes at ~10s intervals per app
- Records timestamp, URL, HTTP status, and elapsed time in milliseconds
- Output: `traffic.csv` with ~2,900 rows per baseline session

**Kernel-level instrumentation** (Node.js experiment, custom `/diag/proc` endpoint):

- Parses `/proc/meminfo` for memory breakdown
- Parses `/proc/vmstat` for page reclaim counters
- Reads `/proc/pressure/memory` for PSI (Pressure Stall Information) metrics
- Captures `process.memoryUsage()` for per-process RSS, heapUsed, external, arrayBuffers

**Infrastructure as Code**: Bicep templates for reproducible deployment (App Service Plan + N Web Apps + optional ACR).

**KQL queries for investigating memory pressure in production:**

Detect plan memory and CPU trend over time:

```kusto
AzureMetrics
| where ResourceProvider == "MICROSOFT.WEB"
| where MetricName in ("MemoryPercentage", "CpuPercentage")
| summarize AvgValue = avg(Total) by MetricName, bin(TimeGenerated, 5m), Resource
| order by TimeGenerated asc
```

Correlate startup-time 503 failures:

```kusto
AppServiceHTTPLogs
| where ScStatus == 503
| summarize Failures = count() by SiteName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

Identify restart or crash-loop periods:

```kusto
AppServiceConsoleLogs
| where Message has_any ("restart", "stopping site", "starting site", "container", "failed")
| project TimeGenerated, SiteName, Message
| order by TimeGenerated asc
```

## 8. Procedure

### Phase A: App count scaling (Flask, ZIP deploy)

Hold per-app memory at 50 MB. Increase app count to find the capacity cliff.

1. Deploy 2 apps x 100 MB as baseline. Collect traffic for ~2.5 hours (2,916 probes). Record plan metrics.
2. Attempt 3 apps x 100 MB. Observe startup failure (container exit code 3). Conclude 100 MB is too aggressive.
3. Reduce to 3 apps x 50 MB. Collect 3 minutes of traffic (72 probes). Record plan metrics.
4. Increase to 4 apps x 50 MB. Disable Oryx build after observing CPU 100% during build. Collect 5 minutes (120 probes).
5. Increase to 5 apps x 50 MB. Collect 5 minutes (125 probes). Note cold start time.
6. Increase to 6 apps x 50 MB. Collect 5 minutes (150 probes). Observe memory plateau.
7. Increase to 8 apps x 50 MB. Collect 128 probes. Observe first 503 errors on apps 7-8.

### Phase B: Memory density scaling (Flask, ZIP deploy)

Hold app count at 4. Increase per-app allocation to find the density limit.

1. Attempt 6 apps x 75 MB. Observe cascade crash (all 6 apps enter restart loop). Roll back.
2. Deploy 4 apps x 75 MB. Confirm stability. Record baseline for density scaling.
3. Increase to 4 x 100 MB. Record cold start time and metrics.
4. Increase to 4 x 125 MB. Record cold start time and metrics.
5. Increase to 4 x 150 MB. Record cold start time and metrics.
6. Increase to 4 x 175 MB. Record cold start time and metrics. Observe peak memory 95%.

### Phase C: Node.js comparison (ZIP deploy + Container deploy)

Repeat Phase A and Phase B with Node.js containers. Add kernel-level instrumentation.

1. Deploy 2 Node.js apps x 100 MB as baseline. Collect 60 probes.
2. Scale from 3 to 8 apps x 50 MB (Phase A equivalent).
3. Scale from 4 x 75 MB to 4 x 175 MB (Phase B equivalent).
4. Repeat with container deployment via ACR.
5. At each step, capture `/proc/meminfo`, `/proc/vmstat`, and `/proc/pressure/memory`.
6. Run traffic burst (10 RPS x 60 seconds) at peak memory pressure.

## 9. Expected signal

If H1 is correct:

- Cold start time increases monotonically with `MemoryPercentage`
- At some threshold, new app deployments fail (503 or container exit codes)
- At a higher threshold, existing apps enter restart loops and the plan does not self-recover
- Steady-state latency remains relatively stable until a restart or scaling event occurs

If H2 is correct:

- `CpuPercentage` increases by >=1.5x over baseline while traffic remains flat
- `pgscan_kswapd` and `pgscan_direct` counters increase by orders of magnitude
- `SwapFree` drops to near zero
- PSI `some avg300` exceeds 1.0
- CPU increase correlates temporally with reclaim counter growth, not with traffic changes

## 10. Results

### 10.1 Flask Phase A — App Count Scaling (ALLOC_MB=50)

```vegalite
{
  "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
  "title": "Phase A: Plan Metrics vs App Count (Flask, ZIP Deploy)",
  "width": 600,
  "height": 300,
  "data": {
    "values": [
      {"config": "2x100MB (base)", "apps": 2, "memory_pct": 76, "cpu_pct_stable": 14, "avg_latency_ms": 934, "errors_5xx": 0, "cold_start_s": 60},
      {"config": "3x50MB", "apps": 3, "memory_pct": 86, "cpu_pct_stable": 14, "avg_latency_ms": 963, "errors_5xx": 0, "cold_start_s": 60},
      {"config": "4x50MB", "apps": 4, "memory_pct": 83.6, "cpu_pct_stable": 14, "avg_latency_ms": 970, "errors_5xx": 0, "cold_start_s": 60},
      {"config": "5x50MB", "apps": 5, "memory_pct": 85.6, "cpu_pct_stable": 17.5, "avg_latency_ms": 984, "errors_5xx": 0, "cold_start_s": 135},
      {"config": "6x50MB", "apps": 6, "memory_pct": 85.7, "cpu_pct_stable": 32, "avg_latency_ms": 948, "errors_5xx": 0, "cold_start_s": 135},
      {"config": "8x50MB", "apps": 8, "memory_pct": 85.7, "cpu_pct_stable": 87.2, "avg_latency_ms": 1070, "errors_5xx": 6, "cold_start_s": null}
    ]
  },
  "layer": [
    {
      "mark": {"type": "bar", "color": "#4C78A8", "opacity": 0.7},
      "encoding": {
        "x": {"field": "config", "type": "ordinal", "sort": null, "title": "Configuration"},
        "y": {"field": "memory_pct", "type": "quantitative", "title": "Memory % (plan avg)", "scale": {"domain": [0, 100]}}
      }
    },
    {
      "mark": {"type": "line", "color": "#E45756", "point": true, "strokeWidth": 2},
      "encoding": {
        "x": {"field": "config", "type": "ordinal", "sort": null},
        "y": {"field": "avg_latency_ms", "type": "quantitative", "title": "Avg Latency (ms)", "scale": {"domain": [800, 1200]}, "axis": {"titleColor": "#E45756"}}
      }
    }
  ],
  "resolve": {"scale": {"y": "independent"}}
}
```

| Configuration | Memory % | CPU % (stable) | Avg Latency (ms) | 5xx Errors | Cold Start (s) |
|---|---|---|---|---|---|
| 2 apps x 100 MB (baseline) | 76 | 14 | 934 | 0 | ~60 |
| 3 apps x 50 MB | 86 | 14 | 963 | 0 | ~60 |
| 4 apps x 50 MB | 83.6 | 14 | 970 | 0 | ~60 |
| 5 apps x 50 MB | 85.6 | 17.5 | 984 | 0 | ~135 |
| 6 apps x 50 MB | 85.7 | 32 | 948 | 0 | ~135 |
| 8 apps x 50 MB | 85.7 | 87.2 | 1,070 (apps 1-6) / 4,000 (apps 7-8) | 6 | apps 7-8 FAILED |

**Key observations from Phase A:**

- Memory plateaued at ~85.7% regardless of app count beyond 5 apps. Adding more 50 MB apps did not raise plan memory further — the kernel compensated by swapping/compressing existing working sets.
- At 8 apps, apps 7-8 could not start. They returned 503 errors with response times up to 16 seconds. Apps 1-6 remained functional with +11-22% latency increase.
- CPU remained low (14-32%) until the 8-app threshold, where startup contention from apps 7-8 pushed CPU to 87%.

### 10.2 Flask Phase B — Memory Density Scaling (4 apps fixed)

```vegalite
{
  "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
  "title": "Phase B: Cold Start Time vs Memory Allocation (Flask, 4 Apps)",
  "width": 500,
  "height": 300,
  "data": {
    "values": [
      {"alloc_mb": 75, "memory_pct_avg": 85.3, "memory_pct_peak": 90, "cold_start_s": 90, "avg_latency_ms": 986, "errors_5xx": 0},
      {"alloc_mb": 100, "memory_pct_avg": 87, "memory_pct_peak": 89, "cold_start_s": 120, "avg_latency_ms": 896, "errors_5xx": 0},
      {"alloc_mb": 125, "memory_pct_avg": 90.5, "memory_pct_peak": 92, "cold_start_s": 150, "avg_latency_ms": 915, "errors_5xx": 0},
      {"alloc_mb": 150, "memory_pct_avg": 88.5, "memory_pct_peak": 91, "cold_start_s": 300, "avg_latency_ms": 881, "errors_5xx": 0},
      {"alloc_mb": 175, "memory_pct_avg": 91.5, "memory_pct_peak": 95, "cold_start_s": 360, "avg_latency_ms": 891, "errors_5xx": 0}
    ]
  },
  "layer": [
    {
      "mark": {"type": "bar", "color": "#F58518", "opacity": 0.6},
      "encoding": {
        "x": {"field": "alloc_mb", "type": "ordinal", "title": "ALLOC_MB per App"},
        "y": {"field": "cold_start_s", "type": "quantitative", "title": "Cold Start Time (seconds)"}
      }
    },
    {
      "mark": {"type": "line", "color": "#4C78A8", "point": true, "strokeWidth": 2},
      "encoding": {
        "x": {"field": "alloc_mb", "type": "ordinal"},
        "y": {"field": "memory_pct_peak", "type": "quantitative", "title": "Peak Memory %", "scale": {"domain": [80, 100]}, "axis": {"titleColor": "#4C78A8"}}
      }
    }
  ],
  "resolve": {"scale": {"y": "independent"}}
}
```

| Configuration | Memory % (avg) | Memory % (peak) | CPU % (stable) | Avg Latency (ms) | 5xx | Cold Start (s) |
|---|---|---|---|---|---|---|
| 4 x 75 MB | 85.3 | 90 | 14-28 | 986 | 0 | ~90 |
| 4 x 100 MB | 87 | 89 | 12-44 | 896 | 0 | ~120 |
| 4 x 125 MB | 90.5 | 92 | 13-28 | 915 | 0 | ~150 |
| 4 x 150 MB | 88.5 | 91 | 12-46 | 881 | 0 | ~300 |
| 4 x 175 MB | 91.5 | 95 | 10-46 | 891 | 0 | ~360 |
| **6 x 75 MB** | **93 (crash)** | **100** | **100 (crash)** | **N/A** | **N/A** | **CRASH LOOP** |

**Key observations from Phase B:**

- Cold start time grew from 90s at 75 MB to 360s at 175 MB — a 4x increase driven entirely by memory pressure.
- Steady-state latency remained within the 880-990 ms range across all configurations. Average response times did not degrade meaningfully even at 95% peak memory.
- The 6 x 75 MB configuration (total ~450 MB allocated) crossed a critical threshold. All 6 apps simultaneously entered a restart loop: memory hit 93%, CPU hit 100%, and the plan could not recover without manual intervention.
- CPU during restart spikes hit 99-100% for 2-4 minutes at 100 MB+ allocations, but returned to 10-46% once apps stabilized.

### 10.3 Node.js Phase A — App Count Scaling (ALLOC_MB=50)

```vegalite
{
  "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
  "title": "Flask vs Node.js: Memory Usage by App Count (Phase A)",
  "width": 500,
  "height": 300,
  "data": {
    "values": [
      {"config": "3x50MB", "runtime": "Flask (ZIP)", "memory_pct": 86},
      {"config": "3x50MB", "runtime": "Node.js (Container)", "memory_pct": 75},
      {"config": "4x50MB", "runtime": "Flask (ZIP)", "memory_pct": 83.6},
      {"config": "4x50MB", "runtime": "Node.js (Container)", "memory_pct": 76},
      {"config": "5x50MB", "runtime": "Flask (ZIP)", "memory_pct": 85.6},
      {"config": "5x50MB", "runtime": "Node.js (Container)", "memory_pct": 73},
      {"config": "6x50MB", "runtime": "Flask (ZIP)", "memory_pct": 85.7},
      {"config": "6x50MB", "runtime": "Node.js (Container)", "memory_pct": 74},
      {"config": "8x50MB", "runtime": "Flask (ZIP)", "memory_pct": 85.7},
      {"config": "8x50MB", "runtime": "Node.js (Container)", "memory_pct": 77}
    ]
  },
  "mark": {"type": "bar", "opacity": 0.8},
  "encoding": {
    "x": {"field": "config", "type": "ordinal", "sort": null, "title": "Configuration"},
    "y": {"field": "memory_pct", "type": "quantitative", "title": "Plan Memory %", "scale": {"domain": [0, 100]}},
    "color": {"field": "runtime", "type": "nominal", "title": "Runtime / Deploy Mode", "scale": {"range": ["#4C78A8", "#72B7B2"]}},
    "xOffset": {"field": "runtime"}
  }
}
```

| Configuration | Node.js Memory % | Node.js CPU % | Node.js Avg Latency | Node.js Errors |
|---|---|---|---|---|
| 2 x 100 MB (baseline) | 74 | 19 | 883 ms | 0 |
| 3 x 50 MB | 75 | 33 | 940 ms | 0 |
| 4 x 50 MB | 76 | 44 | 902 ms | 0 |
| 5 x 50 MB | 73 | 54 | 890 ms | 0 |
| 6 x 50 MB | 74 | 32 | 859 ms | 0 |
| 8 x 50 MB | 77 | 35 | 850 ms | 0 |

All 8 Node.js apps remained healthy with zero errors — in contrast to Flask, where apps 7-8 failed with 503 errors at the same configuration.

### 10.4 Node.js Phase B — Memory Density Scaling (4 apps fixed)

```vegalite
{
  "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
  "title": "Flask vs Node.js: Memory % at Each Density Level (Phase B, 4 Apps)",
  "width": 500,
  "height": 300,
  "data": {
    "values": [
      {"alloc_mb": "75", "runtime": "Flask (ZIP)", "memory_pct": 85.3, "cold_start_s": 90},
      {"alloc_mb": "75", "runtime": "Node.js (Container)", "memory_pct": 73, "cold_start_s": 60},
      {"alloc_mb": "100", "runtime": "Flask (ZIP)", "memory_pct": 87, "cold_start_s": 120},
      {"alloc_mb": "100", "runtime": "Node.js (Container)", "memory_pct": 75, "cold_start_s": 60},
      {"alloc_mb": "125", "runtime": "Flask (ZIP)", "memory_pct": 90.5, "cold_start_s": 150},
      {"alloc_mb": "125", "runtime": "Node.js (Container)", "memory_pct": 75, "cold_start_s": 60},
      {"alloc_mb": "150", "runtime": "Flask (ZIP)", "memory_pct": 88.5, "cold_start_s": 300},
      {"alloc_mb": "150", "runtime": "Node.js (Container)", "memory_pct": 73, "cold_start_s": 60},
      {"alloc_mb": "175", "runtime": "Flask (ZIP)", "memory_pct": 91.5, "cold_start_s": 360},
      {"alloc_mb": "175", "runtime": "Node.js (Container)", "memory_pct": 73, "cold_start_s": 60}
    ]
  },
  "mark": {"type": "bar", "opacity": 0.8},
  "encoding": {
    "x": {"field": "alloc_mb", "type": "ordinal", "sort": null, "title": "ALLOC_MB per App"},
    "y": {"field": "memory_pct", "type": "quantitative", "title": "Plan Memory %", "scale": {"domain": [0, 100]}},
    "color": {"field": "runtime", "type": "nominal", "title": "Runtime / Deploy", "scale": {"range": ["#4C78A8", "#72B7B2"]}},
    "xOffset": {"field": "runtime"}
  }
}
```

Node.js container memory stayed flat at 73-75% across all density levels, while Flask climbed from 85% to 95%. Node.js containers showed no cold start degradation within the tested range.

### 10.5 Kernel Reclaim Activity (Node.js, ZIP Deploy, Phase 2b)

This data comes from the deeper-instrumented Node.js experiment that captured `/proc/vmstat` counters.

```vegalite
{
  "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
  "title": "Kernel Reclaim Counters: Baseline vs Peak Pressure (ZIP Deploy)",
  "width": 500,
  "height": 300,
  "data": {
    "values": [
      {"counter": "pgscan_kswapd", "phase": "Baseline (2x50MB)", "value": 16500000},
      {"counter": "pgscan_kswapd", "phase": "Peak (6x100MB, 60min)", "value": 40400000},
      {"counter": "pgscan_direct", "phase": "Baseline (2x50MB)", "value": 1164},
      {"counter": "pgscan_direct", "phase": "Peak (6x100MB, 60min)", "value": 33372},
      {"counter": "pswpin", "phase": "Baseline (2x50MB)", "value": 121000},
      {"counter": "pswpin", "phase": "Peak (6x100MB, 60min)", "value": 1940000},
      {"counter": "pswpout", "phase": "Baseline (2x50MB)", "value": 321000},
      {"counter": "pswpout", "phase": "Peak (6x100MB, 60min)", "value": 2410000}
    ]
  },
  "mark": {"type": "bar", "opacity": 0.8},
  "encoding": {
    "x": {"field": "counter", "type": "nominal", "title": "Kernel Counter"},
    "y": {"field": "value", "type": "quantitative", "title": "Cumulative Count", "scale": {"type": "log"}},
    "color": {"field": "phase", "type": "nominal", "scale": {"range": ["#72B7B2", "#E45756"]}},
    "xOffset": {"field": "phase"}
  }
}
```

| Counter | Baseline (2 x 50 MB) | Peak (6 x 100 MB, 60 min) | Change |
|---|---|---|---|
| pgscan_kswapd | 16.5M | 40.4M | +179% |
| pgscan_direct | 1,164 | 33,372 | +14,200% |
| pswpin | 121K | 1.94M | +1,500% |
| pswpout | 321K | 2.41M | +650% |
| SwapFree | 1,063 MB | 12-17 MB | 99.2% exhausted |
| PSI some avg300 | — | 5.79 | Significant pressure |
| PSI full avg300 | — | 1.03 | Measurable stall |
| allocstall | 0 | 121 (50 normal + 71 movable) | Present |

### 10.6 ZIP Deploy vs Container Deploy (Node.js, Peak Pressure)

```vegalite
{
  "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
  "title": "ZIP vs Container: Burst Latency Comparison",
  "width": 400,
  "height": 300,
  "data": {
    "values": [
      {"metric": "Avg Latency", "deploy": "ZIP Deploy", "value": 16.8},
      {"metric": "Avg Latency", "deploy": "Container", "value": 173.9},
      {"metric": "p95 Latency", "deploy": "ZIP Deploy", "value": 30},
      {"metric": "p95 Latency", "deploy": "Container", "value": 185},
      {"metric": "p99 Latency", "deploy": "ZIP Deploy", "value": 62},
      {"metric": "p99 Latency", "deploy": "Container", "value": 715}
    ]
  },
  "mark": {"type": "bar", "opacity": 0.8},
  "encoding": {
    "x": {"field": "metric", "type": "nominal", "title": "Latency Metric"},
    "y": {"field": "value", "type": "quantitative", "title": "Milliseconds"},
    "color": {"field": "deploy", "type": "nominal", "scale": {"range": ["#4C78A8", "#F58518"]}},
    "xOffset": {"field": "deploy"}
  }
}
```

| Metric | ZIP Deploy (6 x 100 MB) | Container (4 x 75 MB) |
|---|---|---|
| Max capacity (B1) | 6 apps at 100 MB | 4 apps at 75 MB (6 apps failed) |
| Steady-state CPU avg | 35.2% | 18.8% |
| Memory avg | 84.3% | 80.7% |
| Swap utilization | 99.2% | 49.0% |
| pgscan_kswapd delta (test window) | +25.9M | +1.1M |
| Burst latency avg | 16.8 ms | 173.9 ms |
| Burst latency p99 | 62 ms | 715 ms |
| PSI some / full | 5.79 / 1.03 | 1.57 / 0.51 |

Container deployment reached its stability limit earlier (6 apps at 100 MB caused OOM kills and 503 errors) but showed lower swap utilization due to container cgroup isolation. Under burst traffic, container latency was 10x worse than ZIP deploy.

### 10.7 Deployment Anomalies

During the 4-app Flask deployment with Oryx build enabled, the build process consumed 99-100% CPU for ~5 minutes, causing all existing apps to restart. This was not caused by memory pressure — it was a CPU contention issue from the Python wheel compilation and venv creation.

After disabling Oryx build (`SCM_DO_BUILD_DURING_DEPLOYMENT=false`) and using pre-built ZIP packages, deployment CPU impact was minimal.

## 11. Interpretation

### Degradation zones (H1): SUPPORTED {: .evidence-measured }

The data confirms three distinct degradation modes, each with different triggers and severity:

**Mode 1 — Startup degradation** {: .evidence-measured }

Cold start times increased monotonically with memory allocation:

- 50 MB: ~60s (baseline)
- 100 MB: ~120s (2x baseline)
- 150 MB: ~300s (5x baseline)
- 175 MB: ~360s (6x baseline)

This degradation was observed exclusively in Flask/ZIP deploy. Node.js containers showed no cold start degradation in the tested range, likely because container deployment uses a different startup path that is less sensitive to plan-level memory contention.

**Mode 2 — Capacity cliff** {: .evidence-measured }

At 8 apps x 50 MB (Flask), the plan could not allocate enough resources to start apps 7-8. These apps returned 503 errors with individual request timeouts up to 16 seconds, while apps 1-6 continued serving with +11-22% latency. CPU reached 87% from competing startup processes. The same configuration on Node.js containers (8 x 50 MB) showed zero errors and stable 77% memory — a direct consequence of different memory accounting in container deployments.

**Mode 3 — Restart cascade** {: .evidence-observed }

At 6 x 75 MB (Flask), memory peaked at 93%, all 6 apps entered a simultaneous restart loop, CPU hit 100%, and the plan did not self-recover. This is the most dangerous failure mode because it requires manual intervention (reducing app count or scaling up the plan) and cannot be predicted from memory percentage alone — the threshold depends on the rate of simultaneous memory allocation during app startup, not just the steady-state memory level.

### CPU from kernel reclaim (H2): PARTIALLY SUPPORTED {: .evidence-correlated }

**ZIP Deploy**: The hypothesis is strongly supported for this deployment mode. CPU rose from 20% baseline to 35% average (1.75x) under sustained memory pressure with flat traffic. This increase correlates with massive growth in kernel reclaim counters: pgscan_direct increased by 14,200%, swap was 99.2% exhausted, and PSI some avg300 reached 5.79. The temporal correlation between reclaim counter growth and CPU increase, combined with the absence of any traffic change, provides strong evidence that CPU overhead came from kernel memory management activity.

**Container Deploy**: The primary observation was destabilization rather than gradual CPU creep. The container runtime introduced enough overhead that the plan failed before sustained memory pressure could develop. However, request latency under pressure was 10x worse for containers (avg 174 ms vs 17 ms), suggesting that container isolation does not protect against performance impact — it shifts the failure mode from gradual degradation to earlier catastrophic failure.

### Memory plateau effect {: .evidence-inferred }

An unexpected finding: plan memory percentage plateaued at ~85.7% for Flask regardless of how many 50 MB apps were added beyond 5. The kernel compensated by reclaiming pages from existing apps' working sets and moving them to swap. This means `MemoryPercentage` can appear stable while the actual memory situation is deteriorating — apps are being swapped out, startup times are increasing, and a restart cascade may be imminent. The metric alone is not sufficient to assess memory health.

### Steady-state resilience {: .evidence-measured }

Under the light probe workload (~1 request/10s/app), steady-state response times remained within the 880-990 ms range across all Flask configurations, even at 95% peak memory. The ~900 ms baseline (for a trivial Flask app returning a 200-byte response) is dominated by external network and App Service frontend overhead, which may mask smaller server-side latency shifts. More intensive workloads would likely show greater sensitivity to memory pressure.

## 12. What this proves

1. **Cold start time degrades proportionally to memory pressure on B1 plans.** At 175 MB per app, cold starts took 6x longer than baseline (360s vs 60s). This was measured across multiple configurations with consistent trends. {: .evidence-measured }

2. **There is a capacity cliff, not a gradual decline.** At 8 apps x 50 MB, new apps could not start while existing apps continued operating. The transition from "all apps healthy" to "new apps fail" happened between 6 and 8 apps with no intermediate warning in plan metrics. {: .evidence-measured }

3. **Restart cascades are a real failure mode at 93%+ memory.** At 6 x 75 MB, all apps crashed simultaneously and could not recover. This requires manual intervention. {: .evidence-observed }

4. **Kernel page reclaim causes measurable CPU increase under memory pressure.** CPU rose 1.75x (20% to 35%) with flat traffic, correlated with 179% growth in pgscan_kswapd and 14,200% growth in pgscan_direct. {: .evidence-correlated }

5. **ZIP deploy and container deploy behave differently under the same plan.** Container deployment reported 10-12 percentage points lower `MemoryPercentage` than ZIP deploy at the same allocation level, and failed at lower app density (6 containers vs 8 ZIP apps). {: .evidence-measured }

6. **`MemoryPercentage` can plateau while actual pressure increases.** The metric stayed at ~85.7% while the kernel was actively swapping pages and cold start times were degrading. {: .evidence-inferred }

## 13. What this does NOT prove

1. **These thresholds are not universal.** All measurements were taken on a single B1 plan in Korea Central with synthetic workloads. Different SKUs, regions, runtimes, and application profiles will produce different threshold values. The degradation modes are expected to be general, but the specific memory percentages are not.

2. **Steady-state latency degradation under real workloads.** Our probe workload (~1 request/10s) showed minimal latency impact even at 95% memory. Applications with heavier computation, database connections, file I/O, or larger response payloads may show measurable latency degradation well before the thresholds observed here.

3. **Container memory accounting is understood.** The 10-12 percentage point gap between ZIP and container `MemoryPercentage` readings is observed but not fully explained. It likely relates to differences in cgroup memory accounting, but we did not instrument cgroup v1/v2 limits in this experiment.

4. **Causation between reclaim and CPU is proven.** We demonstrated strong correlation (CPU rises when reclaim counters grow, with no traffic change), but this is not strict causal proof. There may be other kernel-level activities contributing to the CPU increase that we did not instrument.

5. **Long-term cumulative effects.** Our longest observation window was ~60 minutes at peak pressure. Multi-hour or multi-day sustained pressure may reveal additional degradation modes (e.g., memory fragmentation, gradual cache starvation) not captured here.

6. **Windows App Service behavior.** This experiment was conducted entirely on Linux. Windows App Service uses a fundamentally different memory management model (no `/proc`, no swap partition, different process isolation).

## 14. Support takeaway

### Diagnostic checklist for memory pressure cases

1. **Check `MemoryPercentage` in Azure Monitor (plan level).** If it is above 80%, memory pressure is likely. If it is above 90%, restart cascades are a risk.

2. **Do not trust a stable `MemoryPercentage` reading alone.** The metric can plateau at ~85% while the kernel is actively swapping pages. Check cold start times and app restart frequency as secondary indicators.

3. **Ask the customer about recent deployments or restarts.** Most degradation in this experiment appeared during state transitions, not steady-state operation. If the customer reports "my app became slow after I deployed a new app," this is consistent with our findings.

4. **Check CPU during app startup events.** If CPU spikes to 90-100% during deployments but returns to normal afterward, this is expected behavior on B1 plans under memory pressure. It is not an application bug.

5. **Compare app count with plan SKU headroom.** B1 with 6+ apps of any non-trivial size is in the danger zone. The practical safe limit observed in this experiment was 4-5 Flask apps at 50 MB or 4 Node.js containers at 75 MB.

6. **If all apps crash simultaneously, suspect a restart cascade.** This is the most dangerous failure mode. Recovery requires reducing app count or scaling up the plan. It will not self-resolve.

### Recommended actions

| Symptom | Likely cause | Action |
|---|---|---|
| Slow cold starts (>2 min) | Memory pressure during startup | Scale up plan or reduce app count |
| New app deploys, existing apps restart | Insufficient headroom for startup | Scale up before deploying new apps |
| All apps down, CPU 100% | Restart cascade | Immediately reduce app count, then investigate |
| CPU spikes with no traffic increase | Kernel page reclaim | Check `MemoryPercentage`; if >85%, scale up or reduce density |
| Container apps 503 on scale-out | OOM kill from container runtime overhead | Limit to 2-3 containers on B1 |

### General guidance

- **Keep `MemoryPercentage` below 80% on B1 Linux plans.** This provides buffer for startup events and prevents kernel reclaim from stealing CPU cycles.
- **Monitor cold start times as an early warning.** A doubling of startup time is the first observable signal of memory pressure, appearing before latency or error rate increases.
- **Container deployments need more headroom than ZIP deploy.** Plan for roughly 30% fewer apps when using Web App for Containers compared to ZIP deploy on the same SKU.
- **If sustained above 85%, scale up to B2/B3 or reduce app count.** The additional RAM reduces reliance on the 2 GB swap partition and stabilizes CPU.

## 15. Reproduction notes

- **Oryx build creates CPU contention.** Set `SCM_DO_BUILD_DURING_DEPLOYMENT=false` and use pre-built ZIP packages to isolate memory effects from build CPU effects.
- **Allow 5-10 minutes settling time between configuration changes.** Cold starts under pressure can take up to 6 minutes. Measuring too early will capture startup noise rather than steady-state behavior.
- **Baseline measurement matters.** The ~930 ms baseline for a trivial Flask app on B1 in Korea Central includes significant network and frontend overhead. Results from other regions or with Application Insights instrumentation will show different baseline latencies.
- **Container deployment requires ACR setup.** Use Basic SKU ACR with admin auth for simplicity. Multi-stage Docker builds minimize image size.
- **The `/diag/proc` endpoint approach for kernel metrics works on Linux App Service.** Node.js can read `/proc/meminfo`, `/proc/vmstat`, and `/proc/pressure/memory` directly. Note that these files show host-level data on ZIP deploy but may show container-scoped data on container deploy.
- **Traffic generation should be external.** Running the load generator on a separate machine or Azure VM avoids competing for resources on the plan being tested.

## 16. Related resources

- [lab-memory-pressure](https://github.com/yeongseon/lab-memory-pressure) — Flask / ZIP deploy experiment (source data)
- [lab-node-memory-pressure](https://github.com/yeongseon/lab-node-memory-pressure) — Node.js / kernel instrumentation experiment (source data)
- [Azure App Service diagnostics overview](https://learn.microsoft.com/en-us/azure/app-service/overview-diagnostics)
- [App Service Plan metrics reference](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-web-serverfarms-metrics)
- [Understanding memory usage in App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-best-practices#memory)
- [Experiment framework](../../methodology/experiment-framework.md) — methodology used in this experiment
- [Evidence levels](../../methodology/evidence-levels.md) — how evidence tags are applied
