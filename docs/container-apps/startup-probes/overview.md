# Startup, Readiness, and Liveness Probe Interactions

!!! info "Status: Draft - Awaiting Execution"

## 1. Question

How do startup, readiness, and liveness probes interact in Azure Container Apps, and what failure patterns emerge when probe timing is shorter than the application's actual initialization time?

## 2. Why this matters

Probe misconfiguration creates support cases that look like platform instability but are often self-inflicted by timing or endpoint choices. The most confusing patterns are:

- repeated restarts during slow startup
- replicas that never receive traffic even though the process is running
- revisions that become available far later than expected after deployment
- deployments where all probes appear individually reasonable, but together create cascading failure

Understanding probe handoff is especially important in Azure Container Apps because startup protects the app from liveness during initialization, readiness controls traffic eligibility, and tight thresholds can amplify small delays into revision-level unavailability.

## 3. Customer symptom

Typical ticket phrasing:

- "My container keeps restarting after deployment."
- "The app process starts, but the revision never seems to receive traffic."
- "First request works only after several minutes even though the revision was created earlier."
- "Health probes all look configured, but deployment still flaps between healthy and unhealthy."

## 4. Hypothesis

If the application requires about 60 seconds before it can serve probe endpoints successfully, then:

1. a startup probe with only about 30 seconds of failure budget will cause repeated restarts before initialization completes
2. removing the startup probe will allow liveness to begin killing the container during the same slow-start window
3. a failing readiness probe will keep the replica out of rotation without necessarily killing it
4. combining all three probes with aggressive thresholds will produce the most unstable behavior because startup, readiness, and liveness will each contribute a different failure mode at different phases

## 5. Environment

| Parameter | Value |
|---|---|
| Service | Azure Container Apps |
| Hosting model | Managed environment |
| Region | `koreacentral` |
| Runtime | Custom Linux container |
| Application behavior | HTTP service with configurable startup delay and dedicated `/startup`, `/ready`, and `/live` endpoints |
| Ingress | Enabled on target port `8080` |
| Revision mode | Single revision for baseline, optional multiple revision retest for traffic-shift comparison |
| Logging | Log Analytics enabled |
| Date tested | Not yet executed |
| Status | Draft - Awaiting Execution |

## 6. Variables

**Controlled**

- startup delay inside the container (`STARTUP_DELAY_SECONDS=60` baseline)
- probe type, path, port, and protocol
- `initialDelaySeconds`
- `periodSeconds`
- `timeoutSeconds`
- `failureThreshold`
- revision mode and traffic weight

**Observed**

- replica restart count and restart timing
- revision healthy/unhealthy state
- readiness status and whether traffic is routed
- time from revision creation to first successful request
- system log messages indicating probe failures or revision instability
- application log timeline showing when the process began listening and when probe endpoints became healthy

## 7. Instrumentation

Planned evidence sources:

- **ContainerAppSystemLogs_CL** for revision lifecycle and platform-generated failure events
- **ContainerAppConsoleLogs_CL** for application timestamps such as "boot started", "HTTP listener bound", and endpoint-specific logs
- **Diagnose and solve problems > Health Probe Failures** in the Azure portal for per-probe failure breakdown
- revision and replica views in the Azure portal to confirm restart and readiness state
- synthetic HTTP requests against the public endpoint to measure when traffic first succeeds

Recommended application log markers:

- `BOOT_START`
- `HTTP_LISTENING`
- `STARTUP_ENDPOINT_OK`
- `READINESS_ENDPOINT_OK`
- `LIVENESS_ENDPOINT_OK`

## 8. Procedure

1. Build a test container that:
    - listens on port `8080`
    - waits `STARTUP_DELAY_SECONDS` before returning success on `/startup`
    - returns success on `/live` only after the main process loop is active
    - returns success on `/ready` only after initialization completes
2. Deploy a baseline Container App in `koreacentral` with Log Analytics enabled.
3. Confirm the baseline behaves normally with a generous startup probe and moderate readiness/liveness thresholds.
4. Create four revisions or four sequential deployments, one per scenario in the table below.
5. For each scenario, record:
    - revision creation time
    - first probe failure time
    - first restart time
    - time to first successful external request
    - whether the replica ever became ready
6. Run repeated HTTP requests every 5 seconds from an external client until one succeeds or until the scenario clearly stabilizes in failure.
7. Query system and console logs immediately after each scenario.
8. Compare the observed lifecycle against the expected state diagram and scenario matrix.

### Failure scenario matrix

| Scenario | Probe design | Misconfiguration | Expected behavior |
|---|---|---|---|
| 1. Startup probe too short | Startup + readiness + liveness | Startup failure budget covers ~30s while app needs ~60s | Replica restarts before startup completes; repeated restart loop; revision may stay unhealthy |
| 2. No startup probe | Readiness + liveness only | Liveness begins checking during slow startup | Liveness kills the container before initialization finishes; behavior resembles CrashLoopBackOff-style restart churn |
| 3. Readiness probe during init | Startup budget is sufficient; readiness is aggressive | Readiness checks fail until initialization completes | Process stays alive, but replica remains not ready and receives no traffic until readiness passes |
| 4. All probes too tight | Startup + readiness + liveness | All thresholds aggressive and close to actual startup time | Mixed failure pattern: startup failures on some attempts, readiness delay on others, and liveness restarts after partial initialization |

### Example probe configurations

#### Baseline: expected healthy configuration

```yaml
template:
  containers:
    - image: ghcr.io/example/probe-lab:latest
      name: probe-lab
      env:
        - name: STARTUP_DELAY_SECONDS
          value: "60"
      probes:
        - type: Startup
          httpGet:
            path: /startup
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 18
        - type: Readiness
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 12
        - type: Liveness
          httpGet:
            path: /live
            port: 8080
          initialDelaySeconds: 65
          periodSeconds: 10
          timeoutSeconds: 2
          failureThreshold: 3
```

#### Scenario 1: startup probe too short

```yaml
template:
  containers:
    - image: ghcr.io/example/probe-lab:latest
      name: probe-lab
      env:
        - name: STARTUP_DELAY_SECONDS
          value: "60"
      probes:
        - type: Startup
          httpGet:
            path: /startup
            port: 8080
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 6
        - type: Readiness
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 12
        - type: Liveness
          httpGet:
            path: /live
            port: 8080
          initialDelaySeconds: 65
          periodSeconds: 10
          timeoutSeconds: 2
          failureThreshold: 3
```

#### Scenario 2: no startup probe, liveness starts too early

```yaml
template:
  containers:
    - image: ghcr.io/example/probe-lab:latest
      name: probe-lab
      env:
        - name: STARTUP_DELAY_SECONDS
          value: "60"
      probes:
        - type: Readiness
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 12
        - type: Liveness
          httpGet:
            path: /live
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 3
```

#### Scenario 3: readiness blocks traffic during initialization

```yaml
template:
  containers:
    - image: ghcr.io/example/probe-lab:latest
      name: probe-lab
      env:
        - name: STARTUP_DELAY_SECONDS
          value: "60"
      probes:
        - type: Startup
          httpGet:
            path: /startup
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 18
        - type: Readiness
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 3
        - type: Liveness
          httpGet:
            path: /live
            port: 8080
          initialDelaySeconds: 70
          periodSeconds: 10
          timeoutSeconds: 2
          failureThreshold: 3
```

#### Scenario 4: all probes with tight thresholds

```yaml
template:
  containers:
    - image: ghcr.io/example/probe-lab:latest
      name: probe-lab
      env:
        - name: STARTUP_DELAY_SECONDS
          value: "60"
      probes:
        - type: Startup
          httpGet:
            path: /startup
            port: 8080
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 1
          failureThreshold: 8
        - type: Readiness
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 1
          failureThreshold: 2
        - type: Liveness
          httpGet:
            path: /live
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 5
          timeoutSeconds: 1
          failureThreshold: 2
```

## 9. Expected signal

Expected signals before execution:

- **Scenario 1**: `ContainerAppSystemLogs_CL` should show repeated unhealthy or crashing behavior shortly after revision creation; console logs should repeatedly show `BOOT_START` without reaching `HTTP_LISTENING` or probe-success markers.
- **Scenario 2**: console logs should show the app starting but liveness failures should appear before `/live` can return success; restart cadence should begin roughly after the liveness delay plus threshold window.
- **Scenario 3**: restart count should remain low or zero, while readiness remains false and external traffic fails or stalls until `/ready` returns success.
- **Scenario 4**: logs should show overlapping failure reasons across probe phases, producing the least deterministic but most unstable startup pattern.

Expected lifecycle model:

```mermaid
stateDiagram-v2
    [*] --> RevisionCreated
    RevisionCreated --> ContainerStarting
    ContainerStarting --> StartupProbeWindow
    StartupProbeWindow --> Restarted: startup failures exceed threshold
    StartupProbeWindow --> StartupPassed: startup probe succeeds
    StartupPassed --> ReadinessEvaluating
    ReadinessEvaluating --> NotReady: readiness failing
    NotReady --> Ready: readiness succeeds
    Ready --> ServingTraffic
    ReadinessEvaluating --> LivenessEvaluating
    ServingTraffic --> LivenessEvaluating
    LivenessEvaluating --> Restarted: liveness failures exceed threshold
    Restarted --> ContainerStarting
```

## 10. Results

This section is intentionally pre-populated as an execution worksheet and does **not** contain measured data yet.

| Scenario | Planned observation fields | Expected raw result placeholder |
|---|---|---|
| 1. Startup probe too short | startup failures, restart count, revision health, time to first successful request | Expect repeated restart attempts and no stable serving state until configuration is relaxed |
| 2. No startup probe | liveness failure timestamps, restart cadence, boot log gaps | Expect liveness-driven restarts during initialization |
| 3. Readiness during init | readiness status timeline, external request failures, restart count | Expect running process with no traffic until readiness succeeds |
| 4. All probes too tight | mixed probe failures, revision transitions, total time to stable state | Expect cascading instability and the longest time to usable availability |

### Planned KQL queries for probe failure detection

#### System log view by revision

```kusto
ContainerAppSystemLogs_CL
| where ContainerAppName_s == '<app-name>'
| where RevisionName_s contains '<revision-suffix>'
| project TimeGenerated, RevisionName_s, ReplicaName_s, Log_s, Reason_s, Type_s
| order by TimeGenerated asc
```

#### Probe-related failures and restart indicators

```kusto
ContainerAppSystemLogs_CL
| where ContainerAppName_s == '<app-name>'
| where Log_s has_any ('probe', 'health', 'restart', 'unhealthy', 'ContainerCrashing')
    or Reason_s has_any ('ProbeFailed', 'ContainerCrashing', 'HealthCheckFailed')
| project TimeGenerated, RevisionName_s, ReplicaName_s, Reason_s, Log_s, Type_s
| order by TimeGenerated asc
```

#### Application timeline around startup

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == '<app-name>'
| where Log_s has_any ('BOOT_START', 'HTTP_LISTENING', 'STARTUP_ENDPOINT_OK', 'READINESS_ENDPOINT_OK', 'LIVENESS_ENDPOINT_OK')
| project TimeGenerated, RevisionName_s, ContainerGroupName_g, Log_s
| order by TimeGenerated asc
```

#### Time-to-readiness estimate from logs

```kusto
let boot =
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == '<app-name>'
    | where Log_s has 'BOOT_START'
    | summarize BootTime=min(TimeGenerated) by RevisionName_s;
let ready =
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == '<app-name>'
    | where Log_s has 'READINESS_ENDPOINT_OK'
    | summarize ReadyTime=min(TimeGenerated) by RevisionName_s;
boot
| join kind=leftouter ready on RevisionName_s
| extend TimeToReadySeconds=datetime_diff('second', ReadyTime, BootTime)
| project RevisionName_s, BootTime, ReadyTime, TimeToReadySeconds
```

## 11. Interpretation

Planned interpretation rubric after execution:

- **Observed**: raw probe failures, restarts, revision state changes, request outcomes
- **Measured**: exact startup duration before readiness, restart interval, time to first successful request
- **Correlated**: probe-failure bursts aligned with restart bursts or traffic absence
- **Inferred**: startup/liveness handoff explains restart timing when failures line up with configured thresholds

Expected interpretation by scenario:

- **Scenario 1** should support the claim that startup probes protect slow initialization only when the failure budget exceeds realistic boot time.
- **Scenario 2** should show why omitting startup can make liveness act as a premature startup gate.
- **Scenario 3** should isolate traffic blackhole behavior from crash behavior.
- **Scenario 4** should demonstrate that probe settings must be evaluated as a system, not independently.

## 12. What this proves

If the planned results are observed, this experiment should be able to prove the following within this test setup:

- startup probe failure budget directly determines whether a slow-starting container survives long enough to finish initialization
- readiness failure can block traffic routing without necessarily causing restarts
- liveness without a protective startup probe can terminate an otherwise recoverable slow-start container
- aggressive settings across all probes can create compound availability problems that are worse than any single misconfigured probe alone

## 13. What this does NOT prove

Even after execution, this experiment will not by itself prove:

- behavior for every Container Apps workload profile or every region
- exact internal kubelet implementation details beyond what is externally observable in Container Apps
- that every restart loop in Container Apps is probe-related rather than image, dependency, or port-binding failure
- that production workloads with sidecars, Dapr, init dependencies, or external databases will fail in exactly the same timing pattern

## 14. Support takeaway

When a customer reports startup instability in Container Apps, check probe interaction in this order:

1. Confirm whether a **startup probe exists** at all.
2. Compare the application's real initialization time to the **startup failure budget** (`initialDelaySeconds + periodSeconds * failureThreshold`, approximated).
3. Verify whether **readiness** is delaying traffic rather than whether the process is crashing.
4. Check whether **liveness** starts before startup realistically completes.
5. Review portal diagnostics and `ContainerAppSystemLogs_CL` before treating the issue as platform instability.

Fast triage heuristic:

- **restarts increasing** -> inspect startup and liveness first
- **no restarts, no traffic** -> inspect readiness first
- **very delayed first success** -> inspect all three probes together, especially tight thresholds close to real startup time

## 15. Reproduction notes

- Keep the app logic intentionally simple so probe timing is the primary variable.
- Use explicit log messages with UTC timestamps inside the container; otherwise probe timing becomes difficult to reconstruct.
- Because Azure Container Apps can add default probes when ingress is enabled in some creation paths, verify the deployed revision's effective probe configuration before interpreting results.
- Prefer one scenario per revision so logs stay attributable.
- If execution shows platform-generated messages that differ from the assumed `Reason_s` values above, preserve the actual strings and update the KQL filters accordingly.

## 16. Related guide / official docs

- [Microsoft Learn: Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Microsoft Learn: Troubleshoot health probe failures in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-health-probe-failures)
- [Microsoft Learn: Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Microsoft Learn: Azure Monitor Logs reference - ContainerAppSystemLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/containerappsystemlogs)
- [Container Apps Labs Overview](../index.md)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
