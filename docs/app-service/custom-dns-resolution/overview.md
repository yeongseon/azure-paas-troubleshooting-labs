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

# Custom DNS and Private Name Resolution Drift

!!! info "Status: Planned"

## 1. Question

When an App Service with VNet integration uses custom DNS settings or Private DNS Zones, can DNS resolution drift (stale cache, zone link changes, or conditional forwarder misconfiguration) cause intermittent connectivity failures to private endpoints?

## 2. Why this matters

VNet-integrated App Service apps rely on DNS to resolve private endpoint FQDNs. When DNS configuration changes — zone links added/removed, forwarder rules updated, or TTL-based cache entries expire — there can be a window where some instances resolve the old (public) IP while others resolve the new (private) IP. This creates intermittent failures that are extremely difficult to diagnose because they depend on which instance handles the request and when its DNS cache refreshed.

## 3. Customer symptom

- "Connections to our database randomly fail after we added a private endpoint."
- "Some requests go to the public IP and get blocked by the firewall, others work fine."
- "The problem goes away if we restart the app, but comes back after a few hours."

## 4. Hypothesis

After modifying Private DNS Zone links or custom DNS forwarder rules for a VNet-integrated App Service:

1. DNS resolution on existing instances will continue using cached entries until TTL expires.
2. During the cache transition window, different instances may resolve different IPs for the same FQDN.
3. New instances (from scale-out or restart) will immediately use the updated DNS configuration.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | P1v3 (VNet integration required) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Private DNS Zone configuration (link/unlink to VNet)
- Custom DNS server settings
- VNet integration configuration
- Number of instances (2+)

**Observed:**

- DNS resolution results per instance (nslookup/dig output)
- Connectivity success/failure to private endpoint
- DNS TTL values and cache expiry timing
- Resolution consistency across instances

## 7. Instrumentation

- Kudu/SSH console: `nslookup`, `dig` commands from each instance
- Application Insights: dependency call success/failure with resolved IP
- Application logging: DNS resolution results with timestamps
- Azure Monitor: VNet integration status

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- After DNS change, existing instances continue resolving old IP for TTL duration
- New instances or restarted instances immediately resolve new IP
- Intermittent failures during the transition window correlate with instance-level DNS cache state

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

- VNet integration is required (P1v3 or higher, or Regional VNet Integration on lower SKUs)
- Private DNS Zone must be linked to the integration VNet
- DNS TTL values affect the transition window duration

## 16. Related guide / official docs

- [Azure App Service VNet integration](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration)
- [Azure Private DNS](https://learn.microsoft.com/en-us/azure/dns/private-dns-overview)
- [Name resolution for resources in Azure virtual networks](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
