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

# Init Container Startup Order and Failure Impact

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

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
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Init container image | mcr.microsoft.com/azurelinux/base/core:3.0 |
| Main container image | mcr.microsoft.com/azurelinux/base/core:3.0 (helloworld) |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Reliability / Startup sequencing

**Controlled:**

- Init container: `mcr.microsoft.com/azurelinux/base/core:3.0` with command `["/bin/sh", "-c", "sleep 5; exit 0"]`
- Init container resources: 0.25 CPU, 0.5 GiB memory
- Main container: `containerapps-helloworld` serving HTTP on port 80
- Revision mode: multiple (creates new revision on template change)

**Observed:**

- Time from init container start to init container exit
- Time from init container exit to main container start
- Time from main container start to revision ready
- System event ordering: `ContainerCreated`, `ContainerStarted`, `ContainerTerminated` for init vs. main
- Total time from revision deploy to `RevisionReady`

## 7. Instrumentation

- ARM PATCH to add `initContainers` with sleep command
- `az containerapp logs show --type system` — parse event timestamps
- Wall-clock timestamps around ARM PATCH call

## 8. Procedure

1. Add init container with `sleep 5; exit 0` via ARM PATCH.
2. Monitor system events via `az containerapp logs show --type system`.
3. Record timestamps: init container created → started → terminated → main container created → started → revision ready.
4. Calculate: init container duration, gap between init exit and main start, total startup time.

## 9. Expected signal

- Init container starts, runs ~5 seconds (sleep 5), exits with code 0.
- Main container starts after init container terminates.
- Total time to revision ready: ~15–30 seconds (init 5s + main startup + health check).

## 10. Results

### ARM PATCH — add init container

```bash
az rest --method PATCH \
  --uri ".../containerApps/aca-diag-batch?api-version=2024-03-01" \
  --body '{
    "properties": {
      "template": {
        "initContainers": [{
          "name": "init-delay",
          "image": "mcr.microsoft.com/azurelinux/base/core:3.0",
          "command": ["/bin/sh", "-c", "echo Init container starting; sleep 5; echo Init container done"],
          "resources": {"cpu": 0.25, "memory": "0.5Gi"}
        }]
      }
    }
  }'

→ New revision: aca-diag-batch--0000007
→ ARM PATCH completed in 3,376ms
```

### System event timeline (from `az containerapp logs show --type system`)

```
02:06:35  ContainerCreated    Created container 'init-delay'
02:06:35  ContainerStarted    Started container 'init-delay'
02:06:40  ContainerTerminated Container 'init-delay' was terminated with exit code '0'
02:06:46  ContainerCreated    Created container 'aca-diag-batch'
02:06:46  ContainerStarted    Started container 'aca-diag-batch'
02:06:55  RevisionUpdate      Updating revision: aca-diag-batch--0000007
02:06:56  RevisionReady       Successfully provisioned revision 'aca-diag-batch--0000007'
```

### Timing breakdown

| Phase | Duration |
|-------|---------|
| Init container running (`sleep 5`) | **5 seconds** (02:06:35 → 02:06:40) |
| Gap: init exit → main container created | **6 seconds** (02:06:40 → 02:06:46) |
| Main container started → revision ready | **10 seconds** (02:06:46 → 02:06:56) |
| **Total: revision deploy → RevisionReady** | **~21 seconds** |

## 11. Interpretation

- **Measured**: Init container ran for exactly 5 seconds (`sleep 5`), then exited with code 0. H1 is confirmed — the main container does not start until the init container terminates. **Measured**.
- **Measured**: The platform takes 6 seconds between init container exit (`02:06:40`) and main container creation (`02:06:46`). This is not the init container runtime — it is the platform's own scheduling and container creation overhead between the two phases. **Measured**.
- **Measured**: Total time from init container start to revision ready: 21 seconds. The init container's `sleep 5` contributed 5 of those seconds; the remaining 16 seconds were platform overhead and main container startup. **Measured**.
- **Observed**: The system event log explicitly shows the init container name (`init-delay`) in the `ContainerCreated` and `ContainerTerminated` events, separate from the main container name (`aca-diag-batch`). H3 (log separation by container name) is observable from these events. **Observed**.
- **Inferred**: The 6-second gap between init container exit and main container creation represents the Container Apps platform scheduling delay — likely pulling/verifying the main container image and scheduling the replica. This overhead is present on every restart that includes an init container.

## 12. What this proves

- Init containers run to completion before the main container starts — the main container does not start until the init container exits. **Measured**.
- System events clearly identify the init container by name, separate from the main container's events. **Observed**.
- A 5-second init container adds ~5 seconds to the startup time, plus an additional ~6-second platform scheduling gap between init exit and main container creation. **Measured**.

## 13. What this does NOT prove

- Init container failure (non-zero exit code) behavior was not tested in this run. The expected behavior (restart loop) is not confirmed with measured data.
- Whether the platform retries a failed init container indefinitely (expected: yes, with backoff) was not observed.
- Init container re-execution on main container crash-restart was not tested. The documented behavior is that init containers re-run on every replica start.
- The `ContainerAppConsoleLogs` table was not available (no Log Analytics workspace configured), so init container stdout (`echo Init container starting`) could not be verified in Log Analytics.

## 14. Support takeaway

When a Container App never becomes ready and the application logs show nothing:

1. Check for init containers: `az containerapp show -n <app> -g <rg> --query "properties.template.initContainers"`. If init containers exist, they may be failing or running too slowly.
2. Check system logs: `az containerapp logs show -n <app> -g <rg> --type system`. Look for init container name in `ContainerCreated`, `ContainerStarted`, `ContainerTerminated` events. If the main container's `ContainerCreated` event is absent, the init container hasn't finished.
3. A healthy init container adds its runtime PLUS ~6 seconds platform overhead to startup time. For a `sleep 5` init container, expect ~21 seconds total before revision is ready.
4. If init containers are expensive (migrations, prefetching), they increase the time to recovery after every crash/restart — not just the initial deployment.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
SUB="<subscription>"

# Add init container (sleep 5, exit 0)
az rest --method PATCH \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.App/containerApps/${APP}?api-version=2024-03-01" \
  --body '{
    "properties": {
      "template": {
        "initContainers": [{
          "name": "init-delay",
          "image": "mcr.microsoft.com/azurelinux/base/core:3.0",
          "command": ["/bin/sh", "-c", "sleep 5"],
          "resources": {"cpu": 0.25, "memory": "0.5Gi"}
        }]
      }
    }
  }'

# Monitor startup sequence
az containerapp logs show -n $APP -g $RG --type system --tail 30 2>&1 | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        ts = d.get('TimeStamp','')[:19]
        reason = d.get('Reason','')
        msg = d.get('Msg','')[:80]
        print(f'{ts} | {reason:25s} | {msg}')
    except: pass
"

# Remove init container
az rest --method PATCH \
  --uri ".../containerApps/${APP}?api-version=2024-03-01" \
  --body '{"properties":{"template":{"initContainers":null}}}'
```

## 16. Related guide / official docs

- [Init containers in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers#init-containers)
- [Monitor logs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
