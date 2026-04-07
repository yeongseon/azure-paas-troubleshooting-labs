# Common Metric Misreads

Specific cases where Azure platform metrics are misinterpreted, leading to incorrect conclusions or misdirected troubleshooting.

## 1. Plan-level vs. instance-level metrics

**Metric:** App Service plan CPU or memory percentage.

**Common misread:** "The plan is at 85% CPU, so all apps are under pressure."

**Correct interpretation:** Plan-level metrics are aggregated across all instances. A single hot instance at 100% CPU and three idle instances at 0% will show 25% at the plan level — hiding the problem. Conversely, plan-level 85% may mean all instances are evenly loaded at 85%, or one instance is saturated while others are moderate.

**Action:** Always check per-instance metrics. In Azure Monitor, filter by instance name to see the distribution.

## 2. Average vs. percentile response time

**Metric:** Average response time in Application Insights or Azure Monitor.

**Common misread:** "Average response time is 200ms, so performance is fine."

**Correct interpretation:** Average hides tail latency. If 99% of requests complete in 50ms but 1% take 15 seconds, the average may look acceptable while 1% of users experience severe degradation. At scale, 1% can mean thousands of affected requests per hour.

**Action:** Always check p95 and p99 latency. Use Application Insights percentile queries or KQL `percentile()` functions.

## 3. CPU percentage on multi-core instances

**Metric:** CPU percentage on an instance with multiple cores.

**Common misread:** "CPU is at 50%, so there's plenty of headroom."

**Correct interpretation:** On a 2-core instance, 50% CPU can mean one core is fully saturated while the other is idle. If the application is single-threaded (common in Node.js, Python without multiprocessing), the saturated core is the bottleneck. The aggregate metric hides core-level saturation.

**Action:** Check per-core utilization if available (procfs `/proc/stat`). For single-threaded runtimes, treat `100% / core_count` as the practical maximum.

## 4. Request count including platform probes

**Metric:** Total request count in App Service or Container Apps metrics.

**Common misread:** "We're getting 10,000 requests/minute" (used to size infrastructure or calculate per-request cost).

**Correct interpretation:** The request count may include health check probes, platform keep-alive pings, and ARR affinity checks. These are not customer-initiated requests. On a plan with frequent health probes, platform traffic can be a significant fraction of total request count.

**Action:** Filter by URL path or user agent to exclude health probe requests. Check if health check frequency multiplied by instance count accounts for the unexpected volume.

## 5. Memory "available" vs. "committed"

**Metric:** Memory available or memory percentage on App Service.

**Common misread:** "Only 200MB available out of 1.75GB — we're almost out of memory."

**Correct interpretation:** "Available" memory in Linux includes memory used for buffer and page cache, which the kernel can reclaim under pressure. Low "available" memory does not necessarily mean the application is under memory pressure. Committed memory (RSS) is a better indicator of actual application memory consumption.

**Action:** Check `MemAvailable`, `Buffers`, `Cached`, and application RSS via procfs. Compare with cgroup memory usage (`memory.usage_in_bytes` minus `total_inactive_file` in cgroup v1).

## 6. Time granularity masking spikes

**Metric:** Any metric viewed at 5-minute or 1-hour aggregation.

**Common misread:** "CPU never exceeded 60% during the incident window."

**Correct interpretation:** A 10-second CPU spike to 100% that causes request timeouts will be averaged down to a much lower value at 5-minute granularity. The spike is real and caused user impact, but it is invisible at coarse time resolution.

**Action:** Use the finest available granularity (1-minute in Azure Monitor, or sub-minute via custom metrics / procfs polling). For incident investigation, collect high-resolution data during reproduction.

## Recommendation

!!! note
    When possible, cross-reference Azure Monitor metrics with procfs/cgroup data and Application Insights traces. Each data source has its own aggregation, sampling, and scope characteristics. Disagreement between sources is a diagnostic signal, not an error.

See also:

- [False Positives](false-positives.md) — signals that suggest problems that don't exist
- [Evidence Levels](../methodology/evidence-levels.md) — tagging system for calibrated confidence
