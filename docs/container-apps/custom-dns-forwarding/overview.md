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

# Custom DNS Forwarding Failure in Container Apps Environment

!!! info "Status: Planned"

## 1. Question

When a Container Apps environment is configured with custom DNS servers and those servers are unreachable or misconfigured, what is the failure behavior for the application's outbound DNS resolution?

## 2. Why this matters

Container Apps environments in VNet can be configured with custom DNS servers for private name resolution. If the custom DNS is unreachable (firewall, routing, or server failure), all DNS resolution fails — including resolution of public endpoints that the app needs to function. This creates a total outage from a DNS infrastructure issue, not an application issue. The failure is especially confusing because the app starts successfully (DNS isn't needed at container start) but fails on the first outbound call.

## 3. Customer symptom

- "All outbound HTTP calls fail with `Name or service not known` after VNet configuration change."
- "The app worked fine until we changed the DNS server in the VNet."
- "Public APIs are unreachable from our Container App, but the container itself starts fine."

## 4. Hypothesis

When custom DNS servers configured for the Container Apps environment VNet are unreachable:

1. Container starts successfully (DNS not required at boot)
2. All outbound DNS queries fail, including for public FQDNs
3. The failure manifests as connection errors in the application, not as platform errors
4. There is no automatic fallback to Azure Default DNS (168.63.129.16)

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption (VNet-injected) |
| Region | Korea Central |
| Runtime | Python 3.11 (custom container) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- VNet DNS configuration: Azure Default, custom DNS (reachable), custom DNS (unreachable)
- DNS server scenarios: wrong IP, correct IP but port blocked, intermittent availability
- Resolution targets: private endpoint FQDN, public FQDN (e.g., microsoft.com)

**Observed:**

- DNS resolution success/failure per target
- Outbound HTTP request success/failure
- Container startup behavior
- System-level DNS resolver behavior (`/etc/resolv.conf`)

## 7. Instrumentation

- Container console: `nslookup`, `dig`, `cat /etc/resolv.conf`
- Application logging: DNS resolution timing and results
- Application Insights: dependency call failures
- Azure Monitor: container restart events

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Container starts successfully regardless of DNS server reachability
- First outbound DNS query fails immediately (unreachable) or times out (blocked port)
- All subsequent outbound HTTP calls fail with name resolution errors
- `/etc/resolv.conf` shows the custom DNS server configured in the VNet
- No fallback to Azure Default DNS

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

- VNet injection is required for custom DNS
- DNS changes propagate through VNet settings, not container configuration
- The container environment inherits DNS from the VNet; there's no container-level DNS override

## 16. Related guide / official docs

- [Networking in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Provide a custom DNS for your Container Apps environment](https://learn.microsoft.com/en-us/azure/container-apps/environment-custom-dns)
- [Name resolution for resources in Azure virtual networks](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
