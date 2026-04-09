---
hide:
  - toc
---

# False Positives and Misleading Signals

A catalog of situations where metrics or diagnostic signals suggest a problem that does not actually exist, or point to the wrong root cause. Recognizing these patterns prevents unnecessary escalation and misdirected remediation.

## 1. "High memory percentage" on App Service plan

**Signal:** App Service plan shows memory percentage at 80-90%.

**Why it's misleading:** The plan-level memory metric reflects committed memory across all apps on the plan. A single app allocating a large heap does not necessarily mean all apps are under pressure. Additionally, the OS uses available memory for buffer/cache, which inflates the metric without indicating actual memory pressure.

**What to check instead:** Per-instance memory metrics, individual app memory consumption via procfs (`/proc/meminfo`), and whether swap usage is increasing. OOM kill events in container logs are a more reliable pressure indicator than the plan-level percentage.

## 2. CPU spikes during deployment

**Signal:** CPU usage spikes to 80-100% for several minutes during or after a deployment.

**Why it's misleading:** Zip extraction, file copy operations, dependency installation, and application warm-up all consume CPU as part of normal deployment behavior. This is transient and expected.

**What to check instead:** Whether the CPU spike resolves within a few minutes after deployment completes. If CPU remains elevated after warmup, investigate the application code. Compare CPU patterns between deployment periods and normal operation periods.

## 3. Health check failures during scale-out

**Signal:** Health check probe failures appear in logs when new instances are added.

**Why it's misleading:** New instances need time to start the application, load dependencies, and begin responding to health probes. Transient probe failures during this window are expected behavior, not an indication of application instability.

**What to check instead:** Whether health check failures persist after the expected startup duration. Review the startup probe configuration (if applicable) and ensure the initial delay and failure threshold are set appropriately for the application's startup time.

## 4. Increased error rate after deployment

**Signal:** Error rate increases immediately after a new deployment.

**Why it's misleading:** During deployment with in-place updates or slot swaps, old instances may be draining connections while new instances are starting. The transient overlap can produce errors that are not caused by the new code. Connection resets during instance recycling are a platform behavior, not a code defect.

**What to check instead:** Whether the error rate stabilizes after all instances are running the new version. Check if errors occur only on specific instances (old vs. new). Compare the error types — connection resets differ from application exceptions.

## 5. High response time in Application Insights

**Signal:** Application Insights shows average response time of 2-3 seconds for an endpoint that should respond in milliseconds.

**Why it's misleading:** Application Insights request duration may include time spent in the platform request queue before the application handler is invoked. Under load, queue time can dominate the measured duration without reflecting actual application processing time.

**What to check instead:** Add custom telemetry to measure handler execution time independently. Compare App Insights duration with server-side timing (e.g., middleware-measured duration). Check if the discrepancy correlates with high request volume.

## 6. "Memory leak" pattern in managed runtimes

**Signal:** Memory usage steadily increases over hours, suggesting a memory leak.

**Why it's misleading:** Managed runtimes (Node.js, .NET, Java, Python) use garbage collectors that may not return memory to the OS immediately. The heap may grow to fill available memory before GC runs a major collection. This looks like a leak but is normal GC behavior.

**What to check instead:** Monitor GC collection frequency and reclaimed memory. Check if memory stabilizes after a GC cycle. Compare heap used vs. heap committed. A true leak shows heap used growing continuously even after GC collections.

## Takeaway

!!! note
    Always validate metrics against multiple data sources before concluding. A single metric showing an anomaly is a signal to investigate, not a diagnosis. Cross-reference with platform events, application logs, and alternative measurement sources (procfs, cgroup, custom telemetry).

See also:

- [Metric Misreads](metric-misreads.md) — misinterpreted metric values
- [Symptom to Hypothesis](symptom-to-hypothesis.md) — structured investigation starting points
