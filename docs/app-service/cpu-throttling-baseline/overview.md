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

# CPU Throttling: Baseline vs. Burstable Behavior Across SKUs

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

App Service SKUs have defined CPU limits. When an application exceeds the CPU allocation for its SKU, does App Service hard-throttle (kill/restart) the process, soft-throttle (rate-limit CPU cycles), or allow burst above the nominal limit? What does the cgroup CPU configuration look like on a B1 Linux plan?

## 2. Why this matters

CPU throttling behavior is poorly understood by customers who observe slow response times without corresponding CPU metric alerts. On burstable SKUs (B1, B2, B3), the nominal CPU allocation can be temporarily exceeded (CPU credits model), but once credits are exhausted, the vCPU is throttled to the baseline — causing sudden performance degradation without any obvious signal. On premium SKUs, the CPU allocation is more consistent but still subject to noisy-neighbor effects at the physical host level. Understanding this behavior is critical for capacity planning and for explaining performance degradation patterns.

## 3. Customer symptom

"The app performs fine most of the time but slows dramatically during peak hours" or "CPU usage shows 50% but response times are 10× worse than expected" or "Performance degrades exactly when CPU credits run out on the B1 plan."

## 4. Hypothesis

- H1: On B1 SKU Linux, the cgroup `cpu.cfs_quota_us` is set to `-1` (no hard CFS quota), meaning the app can use the full host CPU without a hard cap from the cgroup. ✅ **Confirmed**
- H2: The cgroup `cpu.shares` is set to `1024` (default full-share weight), indicating the container gets a normal CPU share weight rather than a reduced allocation. ✅ **Confirmed**
- H3: 4 concurrent CPU-burn workers on B1 (1 vCPU) all complete in approximately the same wall time as a single sequential burn — because the Python gunicorn workers are separate processes that each get scheduled on the vCPU. ✅ **Confirmed** (4 concurrent 3s burns: 3s wall time)
- H4: Single CPU burn (`/cpu-burn?secs=3`) completes in approximately 3 seconds with low variance on B1. ✅ **Confirmed** (3.09s, 3.11s, 3.09s across 3 runs)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (Basic, Linux, 1 vCPU) |
| Region | Korea Central |
| Runtime | Python 3.11, gunicorn 4 sync workers |
| OS | Linux (kernel 6.6.126.1-1.azl3, glibc 2.31) |
| Host CPU | Intel Xeon E5-2673 v4 @ 2.30 GHz |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Performance / Platform behavior

**Controlled:**

- `/cpu-burn?secs=N` endpoint: tight Python loop (`sum(i*i for i in range(10000))`) for N seconds
- Baseline: 3 sequential single-burst measurements for variance
- Concurrency test: 4 concurrent requests vs. 1 sequential

**Observed:**

- Wall-clock time for single CPU burns (response time via `curl -w "%{time_total}"`)
- Wall-clock time for 4 concurrent CPU burns (measures OS-level CPU sharing vs. serialization)
- cgroup `cpu.cfs_quota_us` and `cpu.shares` via Kudu command API

**Scenarios:**

- S1: 3 sequential 3s CPU burns → baseline latency and variance
- S2: 4 concurrent 3s CPU burns (4 workers, 1 vCPU) → observe CPU sharing behavior
- S3: cgroup introspection → confirm quota and share configuration

## 7. Instrumentation

- `curl -w "%{time_total}"` for response time measurement
- Background subshell `curl` + `wait` for concurrent execution
- Kudu command API (`POST /api/command`) for `cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us` and `cpu.shares`

## 8. Procedure

1. Queried cgroup CPU configuration via Kudu command API.
2. S1: 3 sequential `GET /cpu-burn?secs=3` with `curl -w "%{time_total}"` — recorded per-run time.
3. S2: 4 concurrent background `curl` to `/cpu-burn?secs=3` — measured wall-clock total with `date +%s`.

## 9. Expected signal

- cgroup quota: `-1` (no hard quota per Linux cgroup v1 default)
- Shares: `1024` (default weight)
- S1: ~3.1s per run, low variance (< 0.1s)
- S2: ~3s wall time (OS scheduler time-shares 1 vCPU across 4 processes concurrently)

## 10. Results

**Cgroup CPU configuration (S3):**

```
/sys/fs/cgroup/cpu/cpu.cfs_quota_us:  -1    (no CFS hard quota)
/sys/fs/cgroup/cpu/cpu.shares:        1024  (default weight)
Host CPU model: Intel(R) Xeon(R) CPU E5-2673 v4 @ 2.30GHz
```

**S1: Sequential 3s CPU burns:**

```
Run 1: 3.086s
Run 2: 3.113s
Run 3: 3.092s
Mean: ~3.10s, variance <0.03s
```

**S2: 4 concurrent 3s CPU burns (4 workers, 1 vCPU):**

```
Wall clock total: 3 seconds
(All 4 completed in the same 3-second window)
```

Note: 2 concurrent 3s CPU burns completed in 4 seconds (measured in an earlier experiment run).

## 11. Interpretation

- **Measured**: The cgroup `cpu.cfs_quota_us = -1` on B1 Linux means there is no hard CPU quota imposed by cgroups. The container is not restricted to a fixed fraction of CPU time via CFS bandwidth control.
- **Measured**: `cpu.shares = 1024` is the default weight. This only comes into play when the host is CPU-constrained; under light host load, the container can use up to the full host CPU.
- **Observed**: Single CPU burns complete in ~3.1s with <3% variance — B1 delivers consistent CPU performance for short bursts.
- **Observed**: 4 concurrent CPU burns (4 gunicorn worker processes, 1 vCPU) complete in 3s wall time — the same as a single sequential burn. This is because each worker is a separate process; the OS scheduler time-shares the single vCPU across all 4 processes simultaneously, and Python's compute loop releases the CPU regularly (loop iterations are not atomic from the OS scheduler's perspective).
- **Inferred**: The B1 "burstable" CPU credit model is enforced at the hypervisor/VM level (Azure's virtual machine CPU credit mechanism), not via cgroup CFS quotas. The cgroup sees an uncapped vCPU, but the underlying vCPU itself may be throttled by Azure's infrastructure when credits are exhausted. This is not visible at the cgroup level.
- **Inferred**: Extended sustained CPU load (15+ minutes) on B1 may show credit exhaustion, but this was not reproduced in this experiment (would require long-running load test with Azure Monitor metrics collection).

## 12. What this proves

- B1 Linux App Service does not impose a hard cgroup CFS quota (`cpu.cfs_quota_us = -1`).
- `cpu.shares = 1024` (default) — no deliberate CPU share reduction at the container level.
- Single CPU burns on B1 are consistent (~3.1s for a 3s burn) with low variance under short-burst conditions.
- 4 concurrent Python process CPU burns on 1 vCPU all complete in ~3s wall time — the OS scheduler interleaves them effectively.

## 13. What this does NOT prove

- Credit exhaustion behavior (B1 sustained load for 15+ minutes until credits run low) was **Not Tested** — this requires Azure Monitor metric collection over a sustained period.
- Comparison with P1v3 SKU was **Not Tested** in this lab run.
- Noisy-neighbor effects (physical host CPU overcommit) were **Not Measured**.
- The relationship between `CpuPercentage` Azure Monitor metric and actual process CPU time was **Not Measured** — App Insights was not configured.

## 14. Support takeaway

- "B1 app performs fine initially but gets slow after sustained CPU load" — this matches the B-series credit exhaustion model. The cgroup has no hard quota, but the underlying vCPU credits determine burst duration. Moving to a P-series plan removes the credit model.
- To inspect cgroup CPU config via Kudu: `POST /api/command {"command": "cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us", "dir": "/"}` — `-1` means no hard quota.
- 4 gunicorn workers on 1 vCPU (B1) do not queue CPU-bound requests the same way they queue I/O-bound requests. The OS scheduler interleaves them, so all 4 workers' CPU burns run concurrently — but each takes longer (CPU contention) compared to sequential execution.
- For sustained CPU workloads, B-series SKUs are not appropriate. Use P1v3+ (dedicated vCPU, no credit model).

## 15. Reproduction notes

```bash
# Check cgroup CPU quota via Kudu command API
NETRC_FILE="/tmp/scm_netrc"  # contains Kudu credentials
curl -s --netrc-file $NETRC_FILE \
  -X POST -H "Content-Type: application/json" \
  -d '{"command": "cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us", "dir": "/"}' \
  "https://<app>.scm.azurewebsites.net/api/command"
# Returns: {"Output":"-1\n", ...}

# CPU burn endpoint
@app.route("/cpu-burn")
def cpu_burn():
    secs = float(request.args.get("secs", 2))
    start = time.time()
    while time.time() - start < secs:
        _ = sum(i*i for i in range(10000))
    return jsonify({"burned_secs": secs, "pid": os.getpid()})
```

## 16. Related guide / official docs

- [App Service pricing and SKU comparison](https://azure.microsoft.com/pricing/details/app-service/linux/)
- [Monitor your app in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/web-sites-monitor)
- [B-series burstable virtual machines](https://learn.microsoft.com/en-us/azure/virtual-machines/bsv2-series)
