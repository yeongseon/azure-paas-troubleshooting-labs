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

# Always On Ping Behavior: Interaction with Cold Start, Health Checks, and Idle Shutdown

!!! info "Status: Planned"

## 1. Question

When Always On is enabled on an App Service plan, what exactly is pinged, at what interval, and does the ping prevent the worker process from recycling due to idle timeout — and when Always On is disabled, how long does it take for an idle app to shut down and what is the cold-start latency for the first subsequent request?

## 2. Why this matters

Always On is one of the most misunderstood App Service settings. Support engineers and customers assume it "keeps the app warm" in a generic sense, but the mechanism is specific: the platform sends a GET request to the application root every 5 minutes. This ping does not prevent application-layer caches from expiring, does not keep background threads alive in all runtimes, and does not substitute for a proper health check endpoint. When Always On is disabled on a Basic+ plan (where it is available), the app shuts down after approximately 20 minutes of inactivity — but the exact shutdown timing and cold-start behavior are rarely measured.

## 3. Customer symptom

"Even with Always On enabled, my app is slow on the first request of the day" or "I disabled Always On to save resources but now I get occasional timeouts on the first request" or "My health check passes but the app still feels cold on initial traffic."

## 4. Hypothesis

- H1: Always On sends a GET request to the application root path (`/`) every 5 minutes from the platform, not to the configured health check path. If the root path returns a non-2xx response, the ping is still considered successful from the Always On perspective (the platform does not use this response to drive instance eviction). The health check and Always On are independent mechanisms.
- H2: When Always On is disabled, the worker process is shut down after approximately 20 minutes of no inbound requests. The first request after shutdown triggers a cold start that includes worker process initialization, application framework startup, and dependency loading. The cold-start latency for a Python/Node.js application is measurably higher than a warm response.
- H3: Always On ping does not reset the application's own idle detection. Runtimes that implement their own idle timers (e.g., .NET garbage collection, connection pool eviction) will still recycle internal state based on their own timers, independent of the platform ping.
- H4: On a Free or Shared tier plan, Always On is not available. On these tiers, the worker process shuts down after 20 minutes of inactivity, and cold-start latency is higher than on Basic+ because the instance may also be shared with other tenants.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (Basic) and F1 (Free) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Platform behavior / Performance

**Controlled:**

- App Service on B1 plan with Always On enabled vs. disabled
- App Service on F1 plan (Always On unavailable)
- Application: Python FastAPI with a `/` root endpoint and a `/health` health check endpoint
- Idle period: 25 minutes of no inbound traffic (to exceed idle timeout)

**Observed:**

- Platform ping requests in application access log (source IP, path, User-Agent)
- Worker process PID before and after the idle period (process recycle detection)
- Response time for the first request after idle (cold-start latency)
- Response time for subsequent warm requests (baseline)

**Scenarios:**

- S1: B1 with Always On enabled — 25-minute idle — measure first request latency
- S2: B1 with Always On disabled — 25-minute idle — measure first request latency and process recycle
- S3: F1 with no Always On — 25-minute idle — measure cold-start latency and compare to S2
- S4: B1 with Always On enabled — inspect access log for ping requests; confirm path and interval

**Independent run definition**: One idle period + one first-request measurement per scenario.

**Planned runs per configuration**: 5

## 7. Instrumentation

- App Service access log (`/home/LogFiles/http/RawLogs/`) — capture platform ping requests (source IP, User-Agent, path)
- Application log: log worker PID at startup and per request — detect process recycle
- Response time: `curl -w "%{time_total}" https://<app>.azurewebsites.net/` — cold-start latency
- `az webapp log tail` — real-time log stream during idle period to catch shutdown event
- Metric: `Requests` per minute in Azure Monitor — confirm 0 requests during idle window

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy app to B1 plan; enable Always On; send a warm-up request; wait 25 minutes; send one request; record response time (S1).
2. Inspect access log for the 25-minute window; locate platform ping requests; record source IP, User-Agent, path, and interval (S4).
3. Disable Always On; repeat the 25-minute idle + first request test; compare response time to S1 (S2); confirm worker PID changed.
4. Deploy identical app to F1 plan; repeat 25-minute idle test; record cold-start latency (S3).
5. Compare cold-start latencies across S1, S2, S3; report worker recycle evidence.

## 9. Expected signal

- S1: First request latency is similar to warm latency (~100–300 ms); Always On ping prevents worker shutdown.
- S2: First request after idle takes 3–15 seconds (worker process restart); process PID changes; subsequent requests return to warm latency.
- S3: Cold-start latency on F1 is similar to or higher than S2; no Always On ping in log.
- S4: Access log shows GET `/` requests every ~5 minutes from a platform IP with a distinctive User-Agent (`AlwaysOn`); the health check path is not pinged by Always On.

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

- Always On is only available on Basic tier and above; it is unavailable on Free and Shared tiers.
- The Always On ping target is the application root (`/`), not the health check path configured under Health Check settings. These are independent features.
- Worker PID logging requires the application to log its own PID at startup (e.g., `os.getpid()` in Python); the platform does not expose this directly.
- Idle timeout (the 20-minute shutdown timer) is a platform behavior for plans without Always On; it is not configurable via App Settings.

## 16. Related guide / official docs

- [Configure an App Service app — Always On](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [Health check overview for App Service](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check)
- [App Service cold start and warm-up behavior](https://learn.microsoft.com/en-us/azure/app-service/overview-inbound-outbound-ips)
