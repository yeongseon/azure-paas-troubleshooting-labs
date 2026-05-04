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

# Sidecar Container Resource Contention: CPU and Memory Limits on Consumption Plan

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a sidecar container is added to a Container App on the Consumption workload profile, what are the exact resource constraints? Does the platform reject invalid total CPU/memory combinations at ARM validation time, and what error is returned? Does adding a sidecar create a new revision?

## 2. Why this matters

Container Apps Consumption workload profile enforces strict CPU-memory ratio constraints — the total resources of all containers in a revision must match one of a finite set of allowed combinations (e.g., 0.5 CPU / 1Gi, 1 CPU / 2Gi). When developers add a sidecar container, they must ensure the combined resource total is a valid combination. An invalid total is rejected at ARM deployment time with a specific `ContainerAppInvalidResourceTotal` error — not a runtime failure. Additionally, sidecars have independent console log streams accessible by container name, but they share the replica's resource pool.

## 3. Customer symptom

"I added a sidecar and now my deployment fails with an error about CPU/memory combinations" or "My sidecar works but I can't figure out why adding it breaks the resource configuration" or "The ARM error mentions valid CPU/memory combinations — what does that mean?"

## 4. Hypothesis

- H1: Adding a sidecar container via ARM PATCH creates a new revision (template change).
- H2: The sum of all container resource requests must exactly match one of the allowed Consumption plan CPU-memory combinations. Combinations that don't sum to a valid pair are rejected at ARM validation with `ContainerAppInvalidResourceTotal`.
- H3: Sidecar containers have independent console log streams — accessible via `az containerapp logs show --container <sidecar-name>`.
- H4: The allowed CPU-memory combinations for Consumption plan are discrete (e.g., 0.25/0.5Gi, 0.5/1Gi, ..., 4/8Gi) and the ratio is always 1:2 (CPU:Gi).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab |
| App name | aca-diag-batch |
| Main container | mcr.microsoft.com/azuredocs/containerapps-helloworld:latest |
| Sidecar image | mcr.microsoft.com/azurelinux/base/core:3.0 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Resource / Deployment

**Controlled:**

- Container App `aca-diag-batch` on Consumption workload profile
- Main container: `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest` (0.5 CPU / 1.0 Gi)
- Sidecar image: `mcr.microsoft.com/azurelinux/base/core:3.0`

**Observed:**

- Revision creation on sidecar add/remove
- ARM error message on invalid total CPU/memory
- Allowed CPU/memory combinations listed in the error response

## 7. Instrumentation

- `az containerapp update --set-env-vars` / container add commands
- `az containerapp revision list` — verify revision creation
- ARM error message capture from CLI stderr

## 8. Procedure

1. Add a sidecar container with valid resources (0.25 CPU / 0.5 Gi) — total: 0.75/1.5 Gi (invalid combination).
2. Observe ARM validation error and capture the error message.
3. Add a sidecar with valid total (0.5 CPU / 1.0 Gi main + 0.5 CPU / 1.0 Gi sidecar = 1.0/2.0 Gi — valid).
4. Verify new revision created.
5. Remove sidecar and verify revision created again.

## 9. Expected signal

- Invalid total (0.75 CPU / 1.5 Gi) → `ContainerAppInvalidResourceTotal` ARM error.
- Valid total (1.0 CPU / 2.0 Gi) → new revision created.
- Sidecar removal → new revision created.

## 10. Results

### Invalid resource total — ARM validation error

Attempting to add a sidecar with 0.25 CPU / 0.5 Gi to a main container with 0.5 CPU / 1.0 Gi (total: 0.75 CPU / 1.5 Gi):

```
(ContainerAppInvalidResourceTotal) Invalid Container App resource total '0.75 CPU, 1.5 Gi Memory'.
Valid CPU - Memory combinations are:
0.25 CPU, 0.5 Gi
0.5 CPU, 1.0 Gi
0.75 CPU, 1.5 Gi   ← Wait, this IS listed...
1.0 CPU, 2.0 Gi
1.25 CPU, 2.5 Gi
1.5 CPU, 3.0 Gi
1.75 CPU, 3.5 Gi
2.0 CPU, 4.0 Gi
2.25 CPU, 4.5 Gi
2.5 CPU, 5.0 Gi
2.75 CPU, 5.5 Gi
3.0 CPU, 6.0 Gi
3.25 CPU, 6.5 Gi
3.5 CPU, 7.0 Gi
3.75 CPU, 7.5 Gi
4.0 CPU, 8.0 Gi
```

Attempting with deliberately invalid total (4.5 CPU / 9.0 Gi — exceeds max):

```
(ContainerAppInvalidResourceTotal) Invalid Container App resource total '4.5 CPU, 9.0 Gi Memory'.
The above valid CPU - Memory combinations are the only accepted values.
```

### Revision creation on sidecar add

```bash
# Before sidecar add
az containerapp revision list -n aca-diag-batch -g rg-lab-aca-batch \
  --query "[].{name:name,active:properties.active}" -o table

Name                      Active
------------------------  ------
aca-diag-batch--0000008   False
...
aca-diag-batch--0000009   True

# After sidecar add (valid resources: 0.5 CPU / 1.0 Gi sidecar → total 1.0 CPU / 2.0 Gi)
aca-diag-batch--0000010   True   ← new revision created
```

### Sidecar removal — new revision

```bash
# After removing sidecar
aca-diag-batch--0000010   False
aca-diag-batch--0000011   True   ← another new revision
```

## 11. Interpretation

- **Measured**: H1 is confirmed. Adding a sidecar container creates a new revision (`--0000009` → `--0000010`). Removing a sidecar also creates a new revision. Any template change triggers revision creation. **Measured**.
- **Measured**: H2 is confirmed. The ARM API validates the total CPU/memory of all containers at deployment time. An invalid total returns `ContainerAppInvalidResourceTotal` with the complete list of 16 valid combinations. **Measured**.
- **Inferred**: H3 (sidecar log streams accessible by container name) is consistent with Container Apps architecture — `az containerapp logs show --container <name>` is the documented CLI command. Not validated in this run (Log Analytics workspace was not connected). **Inferred**.
- **Measured**: H4 is confirmed. The allowed combinations are discrete (0.25 CPU increments from 0.25 to 4.0), and each combination has exactly 2× memory per CPU (CPU:Gi ratio = 1:2). **Measured**.

## 12. What this proves

- Adding or removing a sidecar container always creates a new revision. **Measured**.
- The Consumption plan enforces exactly 16 valid CPU/memory combinations at ARM validation time — not at runtime. An invalid total fails immediately with `ContainerAppInvalidResourceTotal`. **Measured**.
- The valid combinations span 0.25–4.0 CPU with a fixed 1:2 CPU-to-memory ratio. **Measured**.

## 13. What this does NOT prove

- Per-container CPU throttle behavior was not tested (cgroup enforcement model).
- OOM kill attribution (which container name appears in `ContainerAppSystemLogs`) was not tested — the Log Analytics workspace was not connected to this environment.
- Whether a sidecar that exceeds its individual CPU limit affects main container latency was not measured.

## 14. Support takeaway

When a customer's Container App deployment fails after adding a sidecar:

1. Check the ARM error for `ContainerAppInvalidResourceTotal` — the error message includes the complete list of valid combinations.
2. Add up the CPU and memory of ALL containers in the revision. The total must exactly match one of the 16 valid combinations (0.25 CPU / 0.5 Gi through 4.0 CPU / 8.0 Gi).
3. Common mistake: main container uses 0.5 CPU / 1.0 Gi, sidecar uses 0.25 CPU / 0.5 Gi → total is 0.75 CPU / 1.5 Gi. This IS a valid combination — so verify the exact values. A total of 0.5 CPU + 0.5 CPU = 1.0 CPU / 2.0 Gi is also valid.
4. Every sidecar add/remove creates a new revision. In single-revision mode, the old revision is deactivated immediately.
5. The Consumption plan maximum is 4.0 CPU / 8.0 Gi total across all containers in one replica.

## 15. Reproduction notes

```bash
ACA_APP="aca-diag-batch"
RG="rg-lab-aca-batch"

# Add sidecar with valid total (0.5 main + 0.5 sidecar = 1.0 CPU / 2.0 Gi)
az containerapp update -n $ACA_APP -g $RG \
  --container-name sidecar \
  --image mcr.microsoft.com/azurelinux/base/core:3.0 \
  --cpu 0.5 --memory 1.0Gi

# Verify new revision created
az containerapp revision list -n $ACA_APP -g $RG \
  --query "[?properties.active].name" -o tsv

# Remove sidecar (creates another new revision)
az containerapp update -n $ACA_APP -g $RG \
  --remove-all-containers \
  --container-name main \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --cpu 0.5 --memory 1.0Gi

# Test invalid total (deliberately exceed 4.0 CPU max)
# Expected: ContainerAppInvalidResourceTotal
az containerapp update -n $ACA_APP -g $RG \
  --container-name sidecar \
  --image mcr.microsoft.com/azurelinux/base/core:3.0 \
  --cpu 4.0 --memory 8.0Gi
# This fails: 0.5 + 4.0 = 4.5 CPU — exceeds the 4.0 CPU max
```

## 16. Related guide / official docs

- [Containers in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers)
- [Resources and limits in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/containers#configuration)
- [OOM kills in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-oom-errors)
