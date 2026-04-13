---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-04-13"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Implicit / Default Probe Injection with Ingress

!!! info "Status: Published"
    Experiment completed with real data on 2026-04-13. Tested 4 scenarios: no probes without ingress, no probes with ingress (fast start), no probes with ingress (60s slow start), and no probes with ingress (normal app).

## 1. Question

If you do not configure probes yourself, what health behavior does Container Apps apply automatically, and how does that change when ingress is enabled vs disabled?

## 2. Why this matters

This question matters because probe behavior is a common source of misdiagnosis in Container Apps incidents. When an app starts slowly, returns unexpected HTTP responses, or appears healthy while users still see failures, support engineers need to know whether the platform injected any hidden health checks or whether the app simply had no probe-based gate at all.

This matters for support because:

- customers may assume ingress automatically creates default health probes even when none are configured
- a slow-starting container may be blamed on invisible probe restarts when the real issue is somewhere else
- an app can keep receiving traffic while only partially working if no readiness probe exists
- ingress-enabled and ingress-disabled apps can look similar operationally unless probe evidence is checked directly

## 3. Customer symptom

Typical ticket phrasing:

- "We never configured probes, but Container Apps seems to be health-checking us anyway."
- "Our app started slowly, but it did not restart. Is there a hidden startup probe?"
- "The process is running, but users still get broken behavior. Why is the app marked healthy?"
- "Does enabling ingress automatically add readiness or liveness probes?"

## 4. Hypothesis

1. Container Apps may inject default health probes when ingress is enabled.
2. A slow-starting app without explicit probes might be killed by auto-injected probes.
3. Apps returning non-200 on root path might fail default health checks.
4. Without probes, the platform relies solely on container process running state.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | `koreacentral` |
| Runtime | Python 3.11 + Flask + gunicorn (`1` worker, `8` threads) |
| OS | Linux |
| Container Apps Environment | `cae-health-probe-lab` (`victoriouswater-301ca985.koreacentral.azurecontainerapps.io`) |
| Image | `acrhealthprobelabb7db7c.azurecr.io/health-probe-lab:v1` |
| Date tested | 2026-04-13 |

### Deployed apps

All four apps were deployed **without any explicit probe configuration**.

| App | Ingress | Startup delay | Notes |
|---|---|---:|---|
| `ca-no-probe-no-ingress` | None | `0s` | No ingress, no probes |
| `ca-no-probe-ingress` | External | `0s` | External ingress, no probes |
| `ca-no-probe-slow` | External | `60s` | External ingress, no probes |
| `ca-no-probe-404` | External | `0s` | External ingress, no probes |

## 6. Variables

**Controlled:**

- same service type, region, Container Apps environment, and Consumption plan
- same image family and runtime stack across all apps
- no explicit startup, readiness, or liveness probe configuration on any app
- same observation method: app state, HTTP checks, API probe config query, and system logs

**Independent variables:**

- ingress disabled vs external ingress enabled
- startup delay (`0s` vs `60s`)
- application scenario represented by each deployed app

**Observed:**

- health state and running state
- whether ingress-exposed apps returned HTTP `200`
- whether the Container Apps API showed any probe configuration
- whether system logs contained any `ProbeFailed` events
- whether slow startup caused restarts or unhealthy transitions

## 7. Instrumentation

Evidence sources used in this run:

- **Container Apps app/revision state** to capture `Healthy` and `RunningAtMaxScale`
- **HTTP checks** against ingress-enabled apps to confirm whether traffic returned `200`
- **`az containerapp show` probe query** against `properties.template.containers[0].probes` to verify whether any probes were present in the resource model
- **ContainerAppSystemLogs_CL** to detect lifecycle events and confirm absence of `ProbeFailed` entries

Most important evidence points were:

- `az containerapp show ... --query "properties.template.containers[0].probes"` returned empty for all four apps
- system logs showed normal lifecycle progression: `PullingImage` → `PulledImage` → `ContainerCreated` → `ContainerStarted` → `RevisionReady`
- zero `ProbeFailed` events were recorded for every app, including the `60s` slow-start case

## 8. Procedure

1. Use the existing Container Apps environment `cae-health-probe-lab` in `koreacentral`.
2. Deploy `ca-no-probe-no-ingress` with no ingress and no explicit probe configuration.
3. Deploy `ca-no-probe-ingress` with external ingress and no explicit probe configuration.
4. Deploy `ca-no-probe-slow` with external ingress, no explicit probe configuration, and `STARTUP_DELAY_SECONDS=60`.
5. Deploy `ca-no-probe-404` with external ingress and no explicit probe configuration.
6. For each app, query the Container Apps resource and inspect `properties.template.containers[0].probes`.
7. For ingress-enabled apps, send HTTP requests and record the resulting status code.
8. Query system logs for lifecycle events and `ProbeFailed` entries for each app.
9. Compare no-ingress vs ingress-enabled behavior and compare fast-start vs slow-start behavior.

## 9. Expected signal

If the hypothesis is correct:

- ingress-enabled apps should show some probe configuration or probe-failure evidence if Container Apps injects defaults
- the slow-start app should show probe timeout failures or restarts if an implicit startup/readiness mechanism exists
- an app that does not match an assumed default HTTP health path should become unhealthy or show probe failures
- if no probes are injected, probe config should remain empty and health should track only whether the container process stays running

## 10. Results

**Execution date**: 2026-04-13  
**Service**: Azure Container Apps (Consumption)  
**Environment**: `cae-health-probe-lab`

### Scenario summary

| App | Ingress | Startup Delay | Health State | Running State | HTTP Status | Probe Config (API) | Probe Failures in System Logs |
|---|---|---|---|---|---|---|---|
| `ca-no-probe-no-ingress` | None | `0s` | `Healthy` | `RunningAtMaxScale` | N/A (no ingress) | Empty (none) | `0` |
| `ca-no-probe-ingress` | External | `0s` | `Healthy` | `RunningAtMaxScale` | `200` | Empty (none) | `0` |
| `ca-no-probe-slow` | External | `60s` | `Healthy` | `RunningAtMaxScale` | `200` | Empty (none) | `0` |
| `ca-no-probe-404` | External | `0s` | `Healthy` | `RunningAtMaxScale` | `200` | Empty (none) | `0` |

### Shared system-log behavior

- All four apps showed the same normal lifecycle pattern: `PullingImage` → `PulledImage` → `ContainerCreated` → `ContainerStarted` → `RevisionReady`.
- Zero `ProbeFailed` events were found for any of the four apps.
- No container restarts were observed in the slow-start scenario.

### Probe configuration evidence

- For every app, `az containerapp show ... --query "properties.template.containers[0].probes"` returned an empty result.
- No startup, readiness, or liveness probes appeared in the resource model after deployment.

### Slow-start scenario (`ca-no-probe-slow`)

- `ca-no-probe-slow` used `STARTUP_DELAY_SECONDS=60`.
- The app still reached `Healthy` / `RunningAtMaxScale`.
- System logs showed no probe timeout messages and no `ProbeFailed` entries.
- The container was not restarted during startup.

### Ingress comparison

- `ca-no-probe-no-ingress` and the three ingress-enabled apps all showed empty probe configuration.
- Enabling external ingress did not introduce visible probe configuration in the API.
- Enabling external ingress also did not produce probe-failure evidence in system logs.

## 11. Interpretation

- [Observed] No `ProbeFailed` events appeared in system logs for any of the four apps.
- [Observed] The Container Apps API returned an empty probes array for all four apps.
- [Measured] `ca-no-probe-slow` with `60s` startup delay reached `RunningAtMaxScale` without restarts.
- [Observed] Ingress-enabled apps returned HTTP `200` while still showing no configured probes.
- [Inferred] When no probes are configured, Container Apps uses container process running state as the effective health signal.
- [Inferred] In this experiment, ingress enabled vs disabled made no difference to probe injection because neither case produced probe configuration or probe-failure evidence.
- [Inferred] This behavior differs from the expectation some engineers bring from Kubernetes environments where default or implicit health behavior may be assumed.

## 12. What this proves

1. [Observed] In this experiment, Container Apps did not auto-inject startup, readiness, or liveness probes when none were configured.
2. [Observed] In this experiment, enabling external ingress did not cause probe injection.
3. [Observed] A `60s` slow-starting app survived and became healthy without probe failures, proving no probe was present to fail during startup.
4. [Observed] The resource model and system logs agreed: probes were absent in the API and absent operationally.
5. [Inferred] Without explicit probes, container-process running state was the practical health criterion used here.
6. [Observed] A probe-less app can still be marked healthy and serve traffic even though no readiness gate is defined.

## 13. What this does NOT prove

1. [Not Proven] This experiment does not prove behavior for every runtime, region, workload profile, or future Container Apps platform version.
2. [Not Proven] This experiment does not prove how Container Apps behaves when explicit probes are partially configured or changed after deployment.
3. [Not Proven] This experiment does not prove that every logically broken HTTP application will always return `Healthy`; only these four tested apps were observed.
4. [Unknown] This experiment did not test multi-container revisions, multiple replicas, or Jobs.
5. [Unknown] This experiment did not establish whether any undocumented internal checks exist outside the API/log evidence path, only that none were visible or operationally impactful here.

## 14. Support takeaway

When a customer says "I never configured probes, but my app is broken":

1. The issue is not auto-injected probes; this experiment found that Container Apps does not inject probes by default.
2. Check whether the app process is merely alive rather than actually ready to serve traffic.
3. Recommend configuring at least a readiness probe for production apps so traffic is gated on real application readiness.
4. For slow-starting apps, use explicit probes with thresholds large enough to cover startup time rather than relying on default behavior.
5. Treat "healthy" without probes as a limited signal: it means the container is running, not that the HTTP surface is correct.

## 15. Reproduction notes

- Keep all test apps on the same Container Apps environment and image so ingress and startup timing are the only meaningful differences.
- Verify probe absence from two angles: the API (`properties.template.containers[0].probes`) and system logs (`ProbeFailed` count).
- Include at least one slow-start case; in this run, `STARTUP_DELAY_SECONDS=60` was sufficient to show that startup was tolerated without restarts.
- Compare both ingress-disabled and ingress-enabled deployments because the common support assumption is that ingress causes default probe injection.
- Record lifecycle events as well as failures; here, normal revision readiness events were just as important as the absence of probe errors.

## 16. Related guide / official docs

- [Azure Container Apps health probes](https://learn.microsoft.com/azure/container-apps/health-probes)
- [Azure Container Apps ingress](https://learn.microsoft.com/azure/container-apps/ingress-how-to)
- [Azure Container Apps logs and monitoring](https://learn.microsoft.com/azure/container-apps/log-monitoring)
- [Dependency-Coupled Health](../dependency-coupled-health/overview.md)
