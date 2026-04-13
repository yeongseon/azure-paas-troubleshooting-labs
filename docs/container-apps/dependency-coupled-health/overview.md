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

# Dependency-Coupled Health Endpoints

!!! info "Status: Published"
    Experiment completed with real data on 2026-04-13. Tested 5 scenarios: baseline (dependency healthy), readiness-only dependency check with outage, both readiness+liveness dependency check with outage, slow dependency timeout, and intermittent dependency failures.

## 1. Question

What happens when readiness or liveness endpoints depend on an external dependency that is slow, down, or intermittently failing?

## 2. Why this matters

Probe endpoints often begin as simple local process checks, but many production apps later add dependency validation to `/ready` or `/live` so the probe reflects downstream health. That design can create severe support confusion in Azure Container Apps because a dependency outage may appear to be a platform restart problem rather than an application probe design issue.

This matters for support because:

- customers may report that Azure Container Apps is "randomly restarting" an otherwise healthy container
- a dependency outage can block traffic without any restart, or can trigger nonstop restarts, depending only on which probe calls the dependency
- slow dependency responses can behave the same as outright dependency failure when probe timeouts are tight
- intermittent dependency failures can create unstable readiness state that looks like traffic routing inconsistency

## 3. Customer symptom

Typical ticket phrasing:

- "Our app stays up locally, but Container Apps stops sending traffic during a backend outage."
- "The platform keeps restarting my app whenever the database or API is unavailable."
- "Everything recovered, but one app never came back and stayed in a failed state."
- "We only see failures when the dependency becomes slow, not fully down."
- "Health status keeps flapping even though the app itself is still running."

## 4. Hypothesis

If readiness probe endpoints check an external dependency:

1. Dependency outage will cause readiness failure → traffic blocked but container stays alive
2. If liveness also checks the dependency → container will be killed and enter restart loop
3. When dependency recovers, readiness-only apps will auto-recover, but liveness-coupled apps may remain stuck in restart loop
4. Slow dependency responses that exceed probe timeout will cause the same readiness failure pattern as a complete outage
5. Intermittent dependency failures will cause flapping readiness state based on failure threshold sensitivity

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | `koreacentral` |
| Runtime | Python 3.11 + Flask + gunicorn (`1` worker, `8` threads, timeout `0`) |
| Container Apps Environment | `cae-health-probe-lab` (`victoriouswater-301ca985.koreacentral.azurecontainerapps.io`) |
| Container Registry | `acrhealthprobelabb7db7c` |
| Image | `health-probe-lab:v1` |
| Date tested | 2026-04-13 |

### Deployed apps

| App | Role / probe design |
|---|---|
| `ca-dependency` | Internal ingress, `APP_MODE=dependency` |
| `ca-dep-baseline` | readiness=`dep`, liveness=`local` |
| `ca-dep-ready-only` | readiness=`dep`, liveness=`local` |
| `ca-dep-both` | readiness=`dep`, liveness=`dep` |
| `ca-dep-slow` | readiness=`dep`, `DEPENDENCY_TIMEOUT_MS=1000` |
| `ca-dep-intermittent` | readiness=`dep`, later toggled to `50%` fail rate |

### Probe configuration used on all main apps

| Probe | Path | Initial delay | Period | Timeout | Failure threshold |
|---|---|---:|---:|---:|---:|
| Startup | `/startup` | 5s | 5s | 2s | 12 |
| Readiness | `/ready` | 5s | 5s | 3s | 3 |
| Liveness | `/live` | 10s | 10s | 3s | 3 |

## 6. Variables

**Controlled:**

- same Container Apps environment, region, SKU, runtime, and image family
- same startup/readiness/liveness probe timings across all main apps
- same dependency service (`ca-dependency`) used by the test apps
- same probe paths (`/startup`, `/ready`, `/live`)
- same dependency-health manipulation model, changing only dependency behavior by scenario

**Independent variables:**

- whether readiness checks the dependency
- whether liveness checks the dependency
- dependency state: healthy, unhealthy, slow, intermittent
- per-app dependency timeout (`1000 ms` vs `2000 ms` where applicable)

**Observed:**

- app health state and running state
- whether external HTTP requests returned `200` or were blocked
- readiness and liveness probe failure behavior
- restart behavior inferred from `PullingImage` events and probe-failure logs
- recovery behavior after dependency restoration
- probe failure counts from Log Analytics

## 7. Instrumentation

Evidence sources used in this run:

- **Container Apps revision/app state** to capture `Healthy` / `Unhealthy` and `Running` / `Activating` / `Failed`
- **HTTP checks** against the app endpoints to confirm whether traffic was accepted (`200`) or blocked
- **ContainerAppSystemLogs_CL** to correlate first probe failures, liveness-triggered termination, and restart cadence
- **Log Analytics counts** for `ProbeFailed` and `PullingImage` events to quantify readiness/liveness failures and restart activity

Most important system log evidence came from `ca-dep-both`, including:

- `2026-04-13 14:48:56 UTC` — first readiness probe failed (`503`)
- `2026-04-13 14:49:01 UTC` — first liveness probe failed (`503`)
- `2026-04-13 14:49:21 UTC` — `Container ca-dep-both failed liveness probe, will be restarted`
- `2026-04-13 14:49:21 UTC` — `Container 'ca-dep-both' was terminated with exit code '' and reason 'ProbeFailure'`

## 8. Procedure

1. Deploy the dependency app `ca-dependency` with internal ingress and `APP_MODE=dependency`.
2. Deploy five test apps using the same `health-probe-lab:v1` image and common probe timings.
3. Confirm the baseline state with the dependency healthy.
4. Run **Scenario 1** baseline validation and record HTTP behavior and probe success.
5. At `14:48:32 UTC`, set the dependency to unhealthy (`DEPENDENCY_HEALTHY=false`).
6. Observe `ca-dep-ready-only` and `ca-dep-both` for health state, running state, probe failures, and restart behavior.
7. Restore dependency health at `14:56:56 UTC` and observe whether each app recovers automatically.
8. At `15:00:41 UTC`, set the dependency to slow (`3000 ms` delay) and observe timeout behavior on `ca-dep-slow` and `ca-dep-baseline`.
9. At `15:03:21 UTC`, set the dependency to intermittent (`50%` fail rate) and observe flapping behavior on `ca-dep-intermittent`.
10. Query Log Analytics for per-app `ProbeFailed` counts and `PullingImage` counts.
11. Compare outage, slow, and intermittent scenarios against probe design (`readiness` only vs `readiness + liveness`).

## 9. Expected signal

If the hypothesis is correct:

- readiness-only apps should stay alive but stop receiving traffic when the dependency fails or exceeds timeout
- apps whose liveness endpoint also checks the dependency should be restarted after liveness failures accumulate
- restoring dependency health should allow readiness-only apps to recover automatically once readiness succeeds again
- slow dependency behavior that exceeds timeout should look operationally similar to outage for readiness
- intermittent dependency failures should cause readiness flapping rather than stable failure or stable success

## 10. Results

**Execution date**: 2026-04-13  
**Service**: Azure Container Apps (Consumption)  
**Environment**: `cae-health-probe-lab`

### Scenario summary

| Scenario | Trigger | Primary app observed | Outcome |
|---|---|---|---|
| S1. Baseline | Dependency healthy | `ca-dep-baseline` | Healthy, running, HTTP `200` |
| S2. Readiness-only outage | `DEPENDENCY_HEALTHY=false` at `14:48:32 UTC` | `ca-dep-ready-only` | Traffic blocked, no restarts, auto-recovered after dependency restore |
| S3. Readiness + liveness outage | `DEPENDENCY_HEALTHY=false` at `14:48:32 UTC` | `ca-dep-both` | `ProbeFailure` restart loop; did not self-recover |
| S4. Slow dependency | `3000 ms` dependency delay at `15:00:41 UTC` | `ca-dep-slow` and `ca-dep-baseline` | Readiness timed out; traffic blocked; no restarts |
| S5. Intermittent dependency | `50%` fail rate at `15:03:21 UTC` | `ca-dep-intermittent` | Readiness flapped; some HTTP requests still succeeded |

### S1: Baseline (dependency healthy)

- All apps were healthy and `Running`.
- `ca-dep-baseline` returned HTTP `200` and reported dependency check OK.
- Measured dependency check duration on `ca-dep-baseline` was about `6.77 ms`.
- All readiness and liveness probes were passing.

### S2: Dependency set to UNHEALTHY

Dependency state changed at `14:48:32 UTC`.

| App | Health state | Running state | Observed behavior |
|---|---|---|---|
| `ca-dep-ready-only` | `Healthy` | `Activating` | Readiness failed, traffic blocked, no restarts |
| `ca-dep-both` | `Unhealthy` | `Failed` | Liveness failed, container killed, restart loop |

#### `ca-dep-both` system log timeline

| Time (UTC) | Evidence |
|---|---|
| `14:48:56` | First readiness probe failed (`503`) |
| `14:49:01` | First liveness probe failed (`503`) |
| `14:49:21` | `Container ca-dep-both failed liveness probe, will be restarted` |
| `14:49:21` | `Container 'ca-dep-both' was terminated with exit code '' and reason 'ProbeFailure'` |

Additional observed behavior:

- restart cycle repeated with about `30-40 s` cadence
- container restarted `8` times total, evidenced by `8` `PullingImage` events

#### Recovery after dependency restoration

Dependency health was restored at `14:56:56 UTC`.

| App | Post-recovery result |
|---|---|
| `ca-dep-ready-only` | Auto-recovered to `Running`, HTTP `200` |
| `ca-dep-both` | Still `Failed`; remained stuck in restart loop |

### S3: Dependency set to SLOW

Dependency delay changed to `3000 ms` at `15:00:41 UTC`.

| App | App dependency timeout | Health state | Running state | Observed behavior |
|---|---:|---|---|---|
| `ca-dep-slow` | `1000 ms` | `Healthy` | `Activating` | Readiness probe timing out; traffic blocked; no restart |
| `ca-dep-baseline` | `2000 ms` | `Healthy` | `Activating` | Also timing out; traffic blocked; no restart |

### S4: Dependency set to INTERMITTENT

Dependency fail rate changed to `50%` at `15:03:21 UTC`.

| App | Health state | Running state | Observed behavior |
|---|---|---|---|
| `ca-dep-intermittent` | `Healthy` | `Activating` | Flapping readiness; HTTP `200` sometimes |

Additional observed behavior:

- `170` readiness probe failures were observed for `ca-dep-intermittent`
- some requests succeeded when readiness passed between failure-threshold resets
- other apps recovered to `Running` because intermittent success occasionally reset the failure threshold

### Probe failure summary from Log Analytics

| App | ProbeFailed count | PullingImage count (restarts) |
|---|---:|---:|
| `ca-dep-baseline` | 157 | 1 (initial only) |
| `ca-dep-ready-only` | 161 | 1 (initial only) |
| `ca-dep-both` | 80 | 8 (7 restarts) |
| `ca-dep-intermittent` | 170 | 1 (initial only) |
| `ca-dep-slow` | 158 | 1 (initial only) |

## 11. Interpretation

- [Observed] When readiness depended on the external dependency, dependency outage blocked traffic without killing the container. `ca-dep-ready-only` stayed `Healthy` / `Activating` and did not restart.
- [Observed] When liveness also depended on the external dependency, dependency outage caused container termination and repeated restarts. `ca-dep-both` became `Unhealthy` / `Failed` and logged `ProbeFailure` termination events.
- [Measured] `ca-dep-both` showed `8` `PullingImage` events, indicating repeated restart attempts, while the readiness-only and slow/intermittent apps stayed at the single initial image pull.
- [Observed] Restoring dependency health allowed the readiness-only app to auto-recover to `Running` with HTTP `200`.
- [Observed] The liveness-coupled app did not self-recover after dependency restoration and remained stuck in restart behavior.
- [Observed] A `3000 ms` dependency delay produced the same operational effect as outage for readiness when app-side dependency timeouts were `1000 ms` or `2000 ms`: both apps stayed alive but traffic was blocked.
- [Observed] A `50%` intermittent dependency failure rate caused readiness flapping rather than stable failure; some requests succeeded between failed probe streaks.
- [Strongly Suggested] Tight coupling between liveness and dependency reachability creates a restart bomb pattern in Container Apps during downstream outages.
- [Inferred] Once the liveness-coupled app entered repeated restart behavior, dependency recovery alone was insufficient to guarantee clean service recovery for that revision state.

## 12. What this proves

1. [Observed] In this experiment, a readiness probe that depended on an external dependency blocked traffic during dependency outage without restarting the container.
2. [Observed] In this experiment, adding the same dependency check to liveness caused Container Apps to terminate the container with `ProbeFailure` and enter a restart loop.
3. [Observed] Readiness-only dependency coupling was self-healing after dependency recovery; `ca-dep-ready-only` returned to `Running` and served HTTP `200` again.
4. [Observed] Liveness-coupled dependency checking was not self-healing here; `ca-dep-both` remained failed after the dependency was restored.
5. [Observed] Slow dependency responses that exceeded effective timeout caused the same readiness-blocking pattern as full dependency outage.
6. [Observed] Intermittent dependency failure caused unstable readiness state and occasional request success rather than total outage.

## 13. What this does NOT prove

1. [Not Proven] This experiment does not prove the exact internal Container Apps recovery logic that kept `ca-dep-both` in failed state after the dependency recovered.
2. [Not Proven] This experiment does not prove that every liveness-coupled dependency outage in every region, runtime, or revision history will always remain stuck until redeployment.
3. [Not Proven] This experiment does not quantify the precise failure-rate threshold at which intermittent dependencies become effectively unusable across all probe settings.
4. [Not Proven] This experiment does not establish a universal safe probe timeout for all downstream services.
5. [Unknown] The effect of different CPU/memory sizing, multiple replicas, or different probe intervals was not tested here.

## 14. Support takeaway

When a customer reports "my healthy app keeps restarting" or "platform killed my app during an external outage":

1. Check whether the liveness probe calls an external dependency. In this experiment, that was the primary cause of destructive restart behavior.
2. Advise customers to keep **liveness = local process health only**.
3. Advise customers that **readiness can include dependency checks** if they want traffic blocked when a downstream service is unavailable.
4. If the app is already stuck in a dependency-driven restart loop, redeploy with corrected probe design rather than waiting for downstream recovery alone.
5. Treat slow dependencies the same as failed dependencies when probe timeout is tight enough to force readiness timeout.

## 15. Reproduction notes

- This experiment depended on switching the same dependency app through healthy, unhealthy, slow, and intermittent modes on the same day (`2026-04-13`).
- Probe timing sensitivity matters: readiness used `period=5`, `timeout=3`, `failureThreshold=3`, while liveness used `period=10`, `timeout=3`, `failureThreshold=3`.
- The slow-dependency scenario used a `3000 ms` downstream delay; both `1000 ms` and `2000 ms` app-side dependency timeouts were low enough to trigger the same readiness-blocking pattern.
- The intermittent scenario used `50%` failure probability. With threshold-based probes, occasional success can reset counters and create apparent flapping rather than a steady failed state.
- For support reproduction, keep one app as readiness-only and one as readiness+liveness against the same dependency so the contrast is visible immediately.

## 16. Related guide / official docs

- [Azure Container Apps health probes](https://learn.microsoft.com/azure/container-apps/health-probes)
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions)
- [Azure Container Apps logs and monitoring](https://learn.microsoft.com/azure/container-apps/log-monitoring)
- [Startup, Readiness, and Liveness Probe Interactions](../startup-probes/overview.md)
