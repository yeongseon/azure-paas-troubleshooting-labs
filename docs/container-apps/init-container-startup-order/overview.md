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

# Init Container Startup Order and Failure Impact

!!! info "Status: Planned"

## 1. Question

When an init container in a Container App fails or runs longer than expected, how does this affect the main application container's startup — and what signals in logs and system events indicate an init container failure rather than an application container failure?

## 2. Why this matters

Init containers are used in Container Apps to run prerequisite tasks (database migration, secret fetching, configuration hydration) before the main container starts. When an init container fails or exceeds its runtime, the main container never starts — but the platform's log surfaces make it difficult to distinguish an init container failure from a main container crash. Support engineers examining restart loops or container readiness failures may overlook the init container entirely if they focus only on application logs.

## 3. Customer symptom

"My Container App never becomes ready even though the image is correct" or "The container keeps restarting but there are no errors in the application log" or "Deployment shows as running but requests get 503."

## 4. Hypothesis

- H1: If an init container exits with a non-zero code, the main container does not start; the pod enters a restart loop, and the system log shows the init container name and exit code.
- H2: If an init container runs indefinitely (no timeout configured), the main container is blocked; the Container App stays in a `Waiting` state with no error signal in application logs.
- H3: Init container stdout/stderr is captured in `ContainerAppConsoleLogs` under the init container's name, not the main container's name; queries targeting only the main container name will miss these logs.
- H4: When the main container crashes and the replica restarts, the init container runs again before the main container starts. Init containers run once per **replica start**, not once per revision deployment — each replica restart triggers a full init container re-execution.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Reliability / Failure injection

**Controlled:**

- Container App with one init container and one main application container
- Init container behavior (success, failure, infinite loop)
- Main container (stateless HTTP echo app)

**Observed:**

- Main container readiness state after each init container outcome
- System log events (`ContainerAppSystemLogs`) — init container name, exit code, restart reason
- Console log entries for init container vs. main container
- Time from revision deploy to main container becoming ready

**Scenarios:**

- S1: Init container exits with code 0 after 5 seconds — baseline
- S2: Init container exits with code 1 (simulated failure)
- S3: Init container runs for 120 seconds before exiting 0 (slow init)
- S4: Init container never exits (infinite loop)
- S5: Main container crashes after init container completes (S1 baseline) — verify init container re-runs on replica restart

**Independent run definition**: One revision deployment per scenario; observe for 10 minutes.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `ContainerAppSystemLogs` KQL: `| where ContainerName == "<init-container-name>"` — init container events
- `ContainerAppConsoleLogs` KQL: `| where ContainerName == "<init-container-name>"` — init container stdout
- `az containerapp show --query "properties.template.initContainers"` — init container config
- `az containerapp revision show --query "properties.replicas"` — replica readiness state
- Time measurement: revision deploy timestamp → first successful HTTP 200 from main container

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container App with init container that sleeps 5 seconds then exits 0 (S1); measure time to main container ready.
2. Change init container exit code to 1 (S2); deploy new revision; observe restart loop and system log entries.
3. Change init to sleep 120 seconds then exit 0 (S3); measure time delay and check for timeout events.
4. Change init to infinite loop (`while true; do sleep 1; done`) (S4); observe platform behavior after 10 minutes.
5. For each scenario, query `ContainerAppConsoleLogs` with both init container name and main container name to confirm log routing.
6. S5: In the S1 baseline app, trigger a main container crash (`kill 1` via exec); observe whether init container stdout re-appears in console logs for the new restart cycle.

## 9. Expected signal

- S1: Main container starts ~5 seconds after revision deploy; no errors in system log.
- S2: Main container never starts; `ContainerAppSystemLogs` shows init container exit code 1 and restart events; restart loop begins.
- S3: Main container starts ~120 seconds after deploy; no errors; startup probe timeout may trigger if configured with short budget.
- S4: Main container never starts; no errors in main container logs; system log shows init container still running after 10 minutes.
- S5: After main container crash, init container re-executes before main container restarts; `ContainerAppConsoleLogs` shows init container stdout appearing again in the restart cycle; `ContainerAppSystemLogs` shows init container start event preceding main container start event.

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

- Init containers are configured under `initContainers` in the Container App template, separate from `containers`.
- The `ContainerAppConsoleLogs` table uses `ContainerName` to distinguish between init and main containers; always filter by init container name when investigating init failures.
- Container Apps does not support init container timeout configuration as of the current API version; a runaway init container will block the main container indefinitely.
- Init containers re-run on every **replica start** (including main container crash-restarts), not just on initial revision deployment. This means a slow or flaky init container adds latency to every restart cycle, not just the first one.
- Init containers share the same network namespace as the main container; they can use `localhost` to communicate with services on the same pod.

## 16. Related guide / official docs

- [Init containers in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers#init-containers)
- [Monitor logs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
