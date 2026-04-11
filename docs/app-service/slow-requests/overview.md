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

# Slow Requests Under Pressure

!!! info "Status: Planned"

## 1. Question

When an App Service worker is under memory or CPU pressure, how do slow requests manifest in telemetry, and can we distinguish frontend (ARR) timeout from worker-side processing delay from downstream dependency latency?

## 2. Why this matters

"Slow requests" is one of the most common support symptoms, but the root cause can originate at three different layers: the platform frontend/load balancer (ARR), the application worker, or a downstream dependency. Each layer produces different diagnostic signals, and misidentifying the layer wastes investigation time.

Support engineers need a reliable method to determine which layer is responsible based on available telemetry.

## 3. Customer symptom

"Some requests take 30+ seconds and then timeout" or "We see 504 errors but our app should respond in under a second."

## 4. Hypothesis

Under controlled delay injection, telemetry will show distinguishable patterns for each bottleneck layer: worker-side delay will inflate request duration without matching dependency duration, dependency-side delay will inflate dependency spans with correlated request delay, and frontend timeout behavior will produce timeout signatures that differ from normal long-running worker responses.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 and P1v3 |
| Region | Korea Central |
| Runtime | Node.js 20 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Performance

**Controlled:**

- Delay injection point (worker, dependency, thread pool)
- Delay duration
- Concurrent request load

**Observed:**

- Application Insights request duration vs. dependency duration
- ARR timeout logs (230-second default)
- HTTP status codes (504 vs. 500 vs. 200 slow)
- Time-to-first-byte vs. total response time

**Independent run definition**: Fresh app restart, fixed load profile, fixed delay scenario, and one complete capture window per scenario.

**Planned runs per configuration**: 5

**Warm-up exclusion rule**: Exclude the first 2 minutes after restart for each run before collecting comparison data.

**Primary metric and meaningful-effect threshold**: p95 end-to-end request duration; meaningful effect is >=20% relative shift between scenarios.

**Comparison method**: Bootstrap confidence interval on per-run p95 deltas, with directional consistency check across runs.

## 7. Instrumentation

- Application Insights requests, dependencies, exceptions, and operation correlation fields
- Azure Monitor metrics for CPU percentage, memory working set, and HTTP queue indicators
- App Service diagnostics and web server logs for timeout and upstream status signals
- Synthetic load generator (k6) with scenario labels and synchronized timestamps
- Application-level structured logs for injected delay markers

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Worker-delay scenario shows increased request duration with minimal dependency-duration change.
- Dependency-delay scenario shows dependency spans tracking request slowdowns and preserved worker health metrics.
- Thread-exhaustion/front-end stress scenario increases timeout-like outcomes and queue-related latency patterns.
- Telemetry signatures remain directionally consistent across repeated runs for each injected scenario.

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

- Keep one injected delay source active at a time to avoid overlapping signals.
- Pin load profile and request mix across runs so layer-specific comparisons stay valid.
- Align all logs to UTC and retain a run identifier in each request for trace stitching.
- Restart the app between run sets when changing major delay scenarios.

## 16. Related guide / official docs

- [Microsoft Learn: Troubleshoot slow app performance](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-performance-degradation)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
