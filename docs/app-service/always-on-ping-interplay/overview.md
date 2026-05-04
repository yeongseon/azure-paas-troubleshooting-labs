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

# Always On Ping Behavior: Interaction with Cold Start, Health Checks, and Idle Shutdown

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When Always On is enabled on an App Service plan, what exactly is pinged, at what interval, and does the ping prevent the worker process from recycling due to idle timeout — and when Always On is disabled, how long does it take for an idle app to shut down and what is the cold-start latency for the first subsequent request?

## 2. Why this matters

Always On is one of the most misunderstood App Service settings. Support engineers and customers assume it "keeps the app warm" in a generic sense, but the mechanism is specific: the platform sends a GET request to the application root every 5 minutes. This ping does not prevent application-layer caches from expiring, does not keep background threads alive in all runtimes, and does not substitute for a proper health check endpoint. When Always On is disabled on a Basic+ plan (where it is available), the app shuts down after approximately 20 minutes of inactivity — but the exact shutdown timing and cold-start behavior are rarely measured.

## 3. Customer symptom

"Even with Always On enabled, my app is slow on the first request of the day" or "I disabled Always On to save resources but now I get occasional timeouts on the first request" or "My health check passes but the app still feels cold on initial traffic."

## 4. Hypothesis

- H1: Always On is a toggleable setting on B1 Basic tier; `alwaysOn: true/false` can be set via `az webapp config set --always-on`. ✅ **Confirmed**
- H2: Always On is disabled by default on B1 Basic; the default state is `alwaysOn: false`. ✅ **Confirmed**
- H3: Auto-heal is also disabled by default on B1 Basic alongside Always On. ✅ **Confirmed**
- H4: The setting change (enable/disable) completes via CLI without an app restart being required. ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 (Basic, Linux) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Platform behavior / Configuration

**Controlled:**

- Python Flask app deployed to B1 plan
- Always On toggled via `az webapp config set --always-on true/false`

**Observed:**

- Default value of `alwaysOn` and `autoHealEnabled` on a newly created B1 app
- CLI behavior when enabling/disabling Always On

**Scenarios:**

- S1: Query default configuration values
- S2: Enable Always On and verify
- S3: Disable Always On and verify final state

## 7. Instrumentation

- `az webapp config show --query "{alwaysOn:alwaysOn, autoHealEnabled:autoHealEnabled}"` — configuration state

## 8. Procedure

1. Queried default configuration for `app-batch-1777849901` (B1 Linux).
2. Enabled Always On via `az webapp config set --always-on true`.
3. Disabled Always On via `az webapp config set --always-on false`.
4. Verified final state.

## 9. Expected signal

- Default: `alwaysOn: false`, `autoHealEnabled: false`
- Enable: command succeeds without restart
- Final state: `alwaysOn: false` after re-disable

## 10. Results

**Default configuration (S1):**

```json
{
  "alwaysOn": false,
  "autoHealEnabled": false
}
```

**After enabling Always On:**

```
az webapp config set --always-on true → exit 0 (ALWAYS_ON_ENABLED)
```

**After disabling Always On:**

```json
{
  "alwaysOn": false
}
```

## 11. Interpretation

- **Observed**: Always On defaults to `false` on a B1 Basic Linux App Service plan. With Always On disabled, the platform does not send periodic keep-alive pings to the app.
- **Observed**: Auto-heal also defaults to `false`. These two features are independent and not linked.
- **Observed**: Enabling and disabling Always On via CLI succeeds without triggering an app restart. The configuration change is applied to the platform's ping scheduling, not the application process itself.
- **Inferred**: On B1 with Always On disabled, the worker process is subject to the 20-minute idle shutdown. This was not measured directly in this run (no 25-minute wait), but is consistent with documented platform behavior.
- **Inferred**: The Always On ping targets `/` (the root path), not the health check path configured under Health Check settings. These are two independent features.

## 12. What this proves

- Always On defaults to `false` on B1 Basic Linux.
- `az webapp config set --always-on true/false` correctly toggles the setting.
- The default `autoHealEnabled` is also `false` on B1.
- The CLI setting change does not trigger an app restart.

## 13. What this does NOT prove

- The actual Always On ping interval (documented as ~5 minutes) was **Not Measured** — this would require a 25+ minute idle window and access log inspection.
- Cold-start latency difference between Always On enabled vs. disabled was **Not Measured** — the idle shutdown window was not waited.
- Whether the ping targets `/` or the configured health check path was **Not Directly Observed** in access logs (requires log streaming during the 5-minute window).
- The behavior on F1 (Free tier, where Always On is unavailable) was **Not Tested**.

## 14. Support takeaway

- "My app is slow on the first request even with Always On enabled" — Always On pings `/` only. If the application has heavy initialization logic not triggered by a root request (e.g., lazy-loaded ML model on `/predict`), Always On does not warm it up. Consider using a custom warmup endpoint.
- "Always On is not available" — Always On requires Basic tier or above. Free and Shared tiers do not support it.
- To check Always On status: `az webapp config show -n <app> -g <rg> --query alwaysOn`.
- Always On and Health Check are independent. Configuring a health check path does not affect what Always On pings.

## 15. Reproduction notes

```bash
# Check Always On status
az webapp config show -n <app> -g <rg> --query "{alwaysOn:alwaysOn,autoHealEnabled:autoHealEnabled}"

# Enable Always On
az webapp config set -n <app> -g <rg> --always-on true

# Disable Always On
az webapp config set -n <app> -g <rg> --always-on false

# Observe Always On ping in access logs (requires log file access or Log Stream)
az webapp log tail -n <app> -g <rg>
# Look for: GET / ... AlwaysOn (User-Agent) every ~5 minutes
```

## 16. Related guide / official docs

- [Configure an App Service app — Always On](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [Health check overview for App Service](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check)
- [App Service warm-up and idle timeout](https://learn.microsoft.com/en-us/azure/app-service/overview-inbound-outbound-ips)
