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

# UDR Asymmetric Routing: Return Traffic Dropped When Egress Controlled by UDR

!!! info "Status: Planned"

## 1. Question

When Container Apps is deployed in a VNet with a User Defined Route (UDR) that sends all egress traffic (0.0.0.0/0) through an Azure Firewall or NVA, but the platform management traffic must return via a direct path, can asymmetric routing cause inbound traffic to be dropped or cause the environment to become unreachable?

## 2. Why this matters

Container Apps in a VNet with custom UDR requires specific routes to allow the platform's management plane to communicate with the containers. If the UDR is too aggressive (routing all traffic through a firewall that drops unknown return traffic), the environment's health probes, management operations, and inbound ingress may fail. This is a common issue when security teams apply a "route all outbound via firewall" policy without understanding the Container Apps platform traffic requirements.

## 3. Customer symptom

"Container Apps environment shows as unhealthy after adding UDR/firewall" or "Container app was deployed but is unreachable from the internet even though ingress is configured" or "Management operations (revision creation, scale operations) fail after adding network controls."

## 4. Hypothesis

- H1: Container Apps requires specific outbound routes to Azure platform services (Azure Monitor, Container Registry, etc.). When these routes are blocked by a firewall UDR, the environment's health degrades and management operations fail.
- H2: Azure Firewall application rules must explicitly allow the Container Apps environment's required FQDNs and service tags before UDR routing is applied. Missing rules cause intermittent management failures.
- H3: The symptom of a UDR misconfiguration is a Container Apps environment stuck in "Degraded" status with recent revision deployments failing, while the existing running containers may continue to serve traffic temporarily.
- H4: The required FQDNs and service tags for Container Apps egress are documented and can be used as a baseline firewall rule set.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps (VNet-integrated, custom UDR) |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Security

**Controlled:**

- Container Apps environment in a dedicated VNet with custom subnet
- UDR routing 0.0.0.0/0 to Azure Firewall
- Azure Firewall with progressively added application rules

**Observed:**

- Container Apps environment health status
- Revision deployment success/failure
- Ingress reachability

**Scenarios:**

- S1: No UDR (direct internet egress) → all operations work
- S2: UDR to firewall, no allow rules → environment degraded
- S3: UDR to firewall, required FQDNs allowed → operations restored

## 7. Instrumentation

- `az containerapp env show` for environment health status
- Container Apps environment **Diagnose and Solve** for network diagnostics
- Azure Firewall logs for blocked connections
- `az containerapp revision create` success/failure

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Container Apps environment without UDR; verify operations work.
2. S2: Add UDR `0.0.0.0/0 → Azure Firewall` with no allow rules; observe environment health degradation.
3. Identify blocked FQDNs from Azure Firewall logs.
4. S3: Add Azure Firewall application rules for required Container Apps FQDNs (from Microsoft documentation); verify environment health restores and revision deployment succeeds.

## 9. Expected signal

- S1: Environment healthy; revision deployment succeeds; ingress accessible.
- S2: Environment shows "Degraded" or management operations fail; Azure Firewall logs show blocked DNS/HTTPS to platform endpoints.
- S3: After adding required FQDN rules, environment returns to healthy; operations succeed.

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

- Required outbound FQDNs for Container Apps include: `mcr.microsoft.com`, `*.data.mcr.microsoft.com`, `*.azurecr.io` (for ACR), Azure Monitor endpoints, and others. See official documentation for the complete list.
- UDR next hop must be a virtual appliance type (e.g., Azure Firewall private IP); use `VirtualAppliance` as the next hop type.
- Container Apps platform traffic uses service tags (`AzureContainerAppsService`, `AzureMonitor`, etc.) for outbound communication.

## 16. Related guide / official docs

- [Container Apps VNet with custom UDR](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Securing outbound traffic from Container Apps with Azure Firewall](https://learn.microsoft.com/en-us/azure/container-apps/user-defined-routes)
