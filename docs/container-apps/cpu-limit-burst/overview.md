---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-03"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# CPU Limit and Burst: Consumption Plan CPU/Memory Pairing Constraints

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-03.

## 1. Question

On Container Apps Consumption plan, CPU and memory are configured as a pair. What are the valid CPU/memory combinations? What happens when an invalid combination (e.g., 0.25 CPU with 4Gi memory, or CPU > 4.0) is specified? And does changing CPU resources on a running app trigger a new revision?

## 2. Why this matters

Unlike VM-based services where CPU and memory can be sized independently, Container Apps Consumption plan enforces a fixed CPU-to-memory ratio (1 vCPU = 2 GiB). Teams migrating from Kubernetes (where CPU and memory are independent) or configuring via Bicep/Terraform templates often specify mismatched CPU/memory pairs. The deployment fails with a validation error — but the error message from the portal is often truncated, while the CLI provides the complete valid combination list.

## 3. Customer symptom

"Container App deployment fails with 'invalid resource total' error" or "We set 0.25 CPU and 1Gi memory but the deployment fails" or "Changing CPU causes the app to restart — is that expected?"

## 4. Hypothesis

- H1: Consumption plan CPU/memory must follow a fixed ratio (1 CPU = 2Gi memory). Invalid combinations are rejected at deployment time with `ContainerAppInvalidResourceTotal`. ✅ **Confirmed**
- H2: The error message includes the complete list of valid CPU/memory combinations. ✅ **Confirmed**
- H3: CPU values above 4.0 are rejected regardless of the memory value. ✅ **Confirmed**
- H4: Changing CPU/memory on a running Container App triggers a new revision (CPU is a revision-scoped property). ✅ **Confirmed**

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Azure Container Apps Hello World image |
| OS | Linux |
| Date tested | 2026-05-03 |

## 6. Variables

**Experiment type**: Configuration / Resource limits

**Controlled:**

- Container Apps Consumption environment
- Various CPU/memory combinations tested via `az containerapp create` and `az containerapp update`

**Observed:**

- Deployment success/failure and exact error message for invalid combinations
- Revision creation on CPU update

**Scenarios:**

| Scenario | CPU | Memory | Result |
|----------|-----|--------|--------|
| S1 (valid) | 0.25 | 0.5Gi | ✅ Created |
| S2 (invalid ratio) | 0.25 | 4Gi | ❌ `ContainerAppInvalidResourceTotal` |
| S3 (cpu=0) | 0.0 | 0.5Gi | ❌ `ContainerAppInvalidCpuResource` |
| S4 (cpu > 4.0) | 4.5 | 9Gi | ❌ `ContainerAppInvalidResourceTotal` |
| S5 (mismatch) | 0.5 | 0.5Gi | ❌ `ContainerAppInvalidResourceTotal` |
| S6 (valid update) | 2.0 | 4Gi | ✅ Updated, new revision created |

## 7. Instrumentation

- `az containerapp create` error output for validation failures
- `az containerapp show --query "properties.template.containers[0].resources"` to verify deployed values
- `az containerapp revision list` to verify revision creation on CPU change

## 8. Procedure

1. Created valid Container Apps (0.25/0.5Gi and 0.5/1Gi) to establish baseline.
2. **S2**: Attempted 0.25 CPU / 4Gi → captured `ContainerAppInvalidResourceTotal` with valid combination list.
3. **S3**: Attempted 0.0 CPU → captured `ContainerAppInvalidCpuResource`.
4. **S4**: Attempted 4.5 CPU / 9Gi → captured rejection (4.0 is the maximum).
5. **S5**: Attempted 0.5 CPU / 0.5Gi (wrong ratio) → captured `ContainerAppInvalidResourceTotal`.
6. **S6**: Updated 0.25/0.5Gi → 2.0/4Gi → confirmed new revision created.

## 9. Expected signal

- Invalid combinations: immediate `ContainerAppInvalidResourceTotal` or `ContainerAppInvalidCpuResource` error at API level.
- Valid combinations: deployment succeeds.
- CPU update: new revision created (revision-scoped property).

## 10. Results

**S1 — Valid (0.25 CPU / 0.5Gi):**
```json
{"cpu": 0.25, "memory": "0.5Gi"}
```
Deployed successfully.

**S2 — Invalid (0.25 CPU / 4Gi):**
```
ERROR: (ContainerAppInvalidResourceTotal) The total requested CPU and memory resources for this application (CPU: 0.25, memory: 4) is invalid. Total CPU and memory for all containers defined in a Consumption Container App must add up to one of the following CPU - Memory combinations:
[cpu: 0.25, memory: 0.5Gi]; [cpu: 0.5, memory: 1.0Gi]; [cpu: 0.75, memory: 1.5Gi]; [cpu: 1.0, memory: 2.0Gi];
[cpu: 1.25, memory: 2.5Gi]; [cpu: 1.5, memory: 3.0Gi]; [cpu: 1.75, memory: 3.5Gi]; [cpu: 2.0, memory: 4.0Gi];
[cpu: 2.25, memory: 4.5Gi]; [cpu: 2.5, memory: 5.0Gi]; [cpu: 2.75, memory: 5.5Gi]; [cpu: 3, memory: 6.0Gi];
[cpu: 3.25, memory: 6.5Gi]; [cpu: 3.5, memory: 7Gi]; [cpu: 3.75, memory: 7.5Gi]; [cpu: 4, memory: 8Gi]
```

**S3 — CPU = 0.0:**
```
ERROR: (ContainerAppInvalidCpuResource) Container with name 'app-cpu-zero' has an invalid CPU resource request: '0.0'. The 'cpu' field for each container, if provided, must contain a decimal value to no more than two decimal places. Example: '0.25'.
```

**S4 — CPU = 4.5 (above maximum):**
Same `ContainerAppInvalidResourceTotal` error — 4.5/9Gi is not in the valid combination list. Maximum is 4.0/8Gi.

**S5 — CPU/memory ratio mismatch (0.5 / 0.5Gi):**
Same `ContainerAppInvalidResourceTotal` error — 0.5 CPU requires 1.0Gi, not 0.5Gi.

**S6 — CPU update (0.25→2.0) triggers new revision:**
```
Name                  Active
app-cpu-025--j3ky7qb  True   ← original (0.25 CPU)
app-cpu-025--0000001  True   ← new revision (2.0 CPU)
```

**Valid Consumption plan CPU/memory combinations (complete list from API):**

| CPU | Memory |
|-----|--------|
| 0.25 | 0.5Gi |
| 0.5 | 1.0Gi |
| 0.75 | 1.5Gi |
| 1.0 | 2.0Gi |
| 1.25 | 2.5Gi |
| 1.5 | 3.0Gi |
| 1.75 | 3.5Gi |
| 2.0 | 4.0Gi |
| 2.25 | 4.5Gi |
| 2.5 | 5.0Gi |
| 2.75 | 5.5Gi |
| 3.0 | 6.0Gi |
| 3.25 | 6.5Gi |
| 3.5 | 7.0Gi |
| 3.75 | 7.5Gi |
| 4.0 | 8.0Gi |

**Ratio**: Memory (GiB) = CPU × 2. Maximum: 4.0 CPU / 8.0Gi.

## 11. Interpretation

**Observed**: Container Apps Consumption plan enforces a strict 1:2 CPU-to-memory ratio. The API rejects any combination that does not match one of 16 predefined tiers. The error message from the API contains the complete valid combination list, which is useful for diagnosing the issue.

**Observed**: The minimum CPU allocation is 0.25 vCPU (with 0.5Gi memory). CPU value of 0.0 is rejected with a separate error (`ContainerAppInvalidCpuResource`) that clarifies the format requirement.

**Observed**: The maximum CPU allocation on the Consumption plan is 4.0 vCPU (with 8.0Gi memory). Values above 4.0 are rejected.

**Observed**: Changing CPU/memory triggers a new revision. CPU is a revision-scoped property — the old revision remains active until traffic is shifted.

**Inferred**: Teams using Terraform or Bicep templates copied from Kubernetes configurations (where CPU and memory are specified independently) are the most common source of `ContainerAppInvalidResourceTotal` errors. The fix is always to align to the 1:2 ratio.

## 12. What this proves

- **Proven**: Consumption plan enforces exactly 16 valid CPU/memory combinations with a fixed 1:2 ratio.
- **Proven**: Invalid combinations are rejected immediately at the API level — no container is started.
- **Proven**: The error message includes the complete valid combination list, making self-service diagnosis possible.
- **Proven**: CPU changes are revision-scoped — a new revision is created when CPU is updated.
- **Proven**: Maximum CPU on Consumption plan is 4.0 vCPU / 8.0Gi.

## 13. What this does NOT prove

- CPU/memory behavior on Dedicated or Consumption-Dedicated workload profiles — different limits may apply.
- Whether CPU bursting (exceeding the allocated CPU limit briefly) is possible on the Consumption plan.
- Behavior when multiple containers in a single revision have combined CPU that exceeds the limit.

## 14. Support takeaway

When a customer gets `ContainerAppInvalidResourceTotal`:

1. **Identify the configured CPU and memory** values from the failed template.
2. **Apply the 1:2 ratio**: Memory (GiB) = CPU × 2. Round CPU to the nearest 0.25 increment.
   - e.g., 0.5 CPU → 1.0Gi; 1.0 CPU → 2.0Gi; 2.0 CPU → 4.0Gi
3. **Maximum**: 4.0 CPU / 8.0Gi. For larger workloads, use Dedicated workload profiles.
4. **Common Kubernetes migration mistake**: Setting `cpu: "500m"` and `memory: "512Mi"` → on Container Apps this translates to 0.5 CPU / 0.5Gi which is invalid (should be 0.5 CPU / 1.0Gi).

## 15. Reproduction notes

```bash
# Valid combinations
az containerapp create -n myapp -g myrg --environment myenv \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --cpu 0.25 --memory 0.5Gi --ingress external --target-port 80

# Invalid (mismatched ratio) → ContainerAppInvalidResourceTotal
az containerapp create -n myapp -g myrg --environment myenv \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --cpu 0.5 --memory 0.5Gi --ingress external --target-port 80

# Update CPU (triggers new revision)
az containerapp update -n myapp -g myrg --cpu 2.0 --memory 4Gi
```

## 16. Related guide / official docs

- [Container Apps resource allocation](https://learn.microsoft.com/en-us/azure/container-apps/containers#allocations)
- [Container Apps Consumption plan](https://learn.microsoft.com/en-us/azure/container-apps/plans)
- [Container Apps workload profiles](https://learn.microsoft.com/en-us/azure/container-apps/workload-profiles-overview)
