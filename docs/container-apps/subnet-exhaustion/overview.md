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

# Environment Subnet IP Exhaustion: Impact on New Replica Provisioning

!!! info "Status: Planned"

## 1. Question

When a Container Apps environment's delegated subnet runs out of available IP addresses, what happens to new replica provisioning — and how does this failure manifest in system logs, scaling events, and application availability?

## 2. Why this matters

Container Apps environments deployed in a custom VNet require a delegated subnet with sufficient IP addresses. Each replica consumes at least one IP from the subnet. In Consumption profiles, replicas are ephemeral and IPs are released quickly; in Dedicated (Workload Profiles) environments, IPs may be held longer. When the subnet is exhausted, new replicas cannot be provisioned. This means scale-out events silently fail — the Container App does not scale up even under high load — and new revision deployments stall without a clear error in the portal. The root cause (subnet IP exhaustion) is not surfaced directly in Container App logs.

## 3. Customer symptom

"My Container App stops scaling under load even though the scaling rules are configured correctly" or "A new revision was deployed but replicas never started" or "The environment seems healthy but I can't provision new containers."

## 4. Hypothesis

- H1: When the subnet is exhausted, new replica provisioning fails. The failure is recorded in `ContainerAppSystemLogs` as a provisioning error; the error message references a network allocation failure rather than an application error. The existing replicas continue running and serving traffic.
- H2: Scale-out triggered by a scaling rule does not produce an explicit error visible to the operator when it fails due to subnet exhaustion. The `ReplicaCount` metric does not increase; the scaling rule fires but the additional replicas are never created. No alert is raised by default.
- H3: After freeing subnet IPs (by removing replicas or deleting apps in the environment), new replicas can be provisioned immediately without redeploying the Container App.
- H4: The minimum subnet size recommended for a Container Apps environment (`/23` for Workload Profiles, `/27` for Consumption) is sufficient for typical workloads, but environments with many apps and high autoscale ceilings can exhaust even a `/23` under sustained load.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption (custom VNet) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Infrastructure

**Controlled:**

- Container Apps environment in custom VNet with a `/28` subnet (14 usable IPs — intentionally small for the experiment)
- Multiple Container Apps deployed to the same environment to consume IPs
- Scaling rules configured to scale out under load

**Observed:**

- IP allocation per replica (inferred from subnet available IPs before and after provisioning)
- `ContainerAppSystemLogs` provisioning failure message when subnet is exhausted
- `ReplicaCount` metric during a load test that should trigger scale-out
- Recovery time after freeing IPs

**Scenarios:**

- S1: Fresh environment with `/28` subnet — baseline IP consumption per app per replica
- S2: Fill subnet by deploying apps until no IPs remain — observe first provisioning failure
- S3: Apply load to scale-out-eligible app when subnet is full — observe scale-out failure behavior
- S4: Delete one app to free IPs — observe whether pending replicas start automatically

**Independent run definition**: One provisioning attempt or scale event per scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Azure Portal: VNet subnet > IP addresses in use — monitor available IPs
- `az network vnet subnet show --query "ipConfigurations[].id | length(@)"` — IP usage count
- `ContainerAppSystemLogs` KQL: `| where Reason contains "Failed" or Message contains "network" or Message contains "IP"` — provisioning failures
- Azure Monitor metric: `ReplicaCount` — scale-out effectiveness during load test
- Load generator: `hey -n 10000 -c 50` — sustained concurrent load to trigger scale-out

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container Apps environment with `/28` subnet; confirm 14 usable IPs; deploy one app and note IPs consumed per replica (S1).
2. S2: Deploy additional apps with `minReplicas=2` each; continue until subnet exhaustion; record the provisioning failure in system log at the point of exhaustion.
3. S3: While subnet is full, send load to a scale-out-eligible app; observe `ReplicaCount` metric — confirm it does not increase; check system log for scale-out failure reason.
4. S4: Delete one of the deployed apps to free IPs; wait 2 minutes; check if the pending replica from S3 starts automatically.

## 9. Expected signal

- S1: Each Consumption replica consumes 1 IP from the subnet; environment infrastructure consumes a fixed baseline of IPs at creation.
- S2: First provisioning failure after subnet exhaustion produces a system log entry referencing network/IP allocation; the error is not surfaced as an application error.
- S3: `ReplicaCount` stays flat despite load; no scale-out error is visible in application logs or Azure Monitor alerts (unless explicitly configured); scale-out silently fails.
- S4: After IP is freed, pending replicas start within 1–2 minutes without requiring a new revision deployment.

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

- Use a `/28` subnet (14 usable IPs) intentionally for this experiment to trigger exhaustion with a small number of apps. In production, use at least `/27` for Consumption or `/23` for Workload Profiles.
- The Container Apps environment itself reserves several IPs at creation; the exact count varies by environment type. Measure the baseline IP usage immediately after environment creation before deploying any apps.
- Subnet IP exhaustion does not trigger a platform alert by default; configure an Azure Monitor alert on subnet IP usage (`Microsoft.Network/virtualNetworks/subnets/availableIpAddressCount`) to detect this condition proactively.
- In Consumption environments, IPs are released when replicas are removed. Scale-to-zero releases all replica IPs. In Dedicated (Workload Profiles) environments, the underlying nodes retain IPs even when replica count is 0.

## 16. Related guide / official docs

- [Networking in Azure Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Custom VNet integration in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom)
- [Plan IP addressing for Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/networking#subnet-requirements)
