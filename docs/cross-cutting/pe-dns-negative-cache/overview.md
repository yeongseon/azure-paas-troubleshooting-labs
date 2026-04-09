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

# Private Endpoint Cutover and DNS Negative Caching

!!! info "Status: Planned"

## 1. Question

When enabling a private endpoint for an Azure service and updating DNS to resolve to the private IP, how does DNS negative caching affect the transition period, and can it cause extended outages beyond the expected DNS TTL?

## 2. Why this matters

Private endpoint migrations are high-risk operations. The expected flow is: create private endpoint → update DNS → traffic flows to private IP. But DNS negative caching (caching of NXDOMAIN or failed lookups) can cause problems:

- If the private DNS zone is created but the link to the VNet is delayed, clients may cache the negative result
- If the DNS query returns NXDOMAIN during the transition window, that negative response gets cached
- The negative cache TTL may be longer than the positive TTL, extending the outage

## 3. Customer symptom

- "We created the private endpoint and DNS zone, but resolution still shows the public IP after 30 minutes."
- "Some instances resolve the private IP, others still resolve the public IP."
- "After restart, everything works — but without restart, the old resolution persists for hours."

## 4. Hypothesis

1. DNS negative caching (NXDOMAIN caching) in the VNet resolver causes extended resolution failures during private endpoint cutover.
2. The negative cache TTL (SOA minimum) can be 5-60 minutes, independent of the A record TTL.
3. If the private DNS zone link is created after the first DNS query, the negative cache prevents the client from seeing the new private IP until the negative cache expires.
4. Different Azure compute services (App Service, Functions, Container Apps) handle DNS cache differently, leading to inconsistent behavior across services.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service, Functions, Container Apps (all three) |
| SKU / Plan | Various (VNet-integrated) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Hybrid (Config: does resolution switch? Performance: how long does it take?)

**Controlled:**

- Private endpoint target: Storage Account, SQL Database
- DNS configuration sequence: zone first vs link first vs simultaneous
- VNet DNS: Azure Default (168.63.129.16) vs custom DNS forwarder
- Client compute: App Service, Functions, Container Apps

**Observed:**

- DNS resolution result (public IP vs private IP) over time per client
- Negative cache duration
- Time from DNS change to consistent private resolution across all instances
- Connectivity success/failure to private endpoint during transition

**Independent run definition**: Clean VNet with no prior DNS cache, fresh deployment, create private endpoint and DNS zone with specified sequencing

**Planned runs per configuration**: 3 (minimum; this is expensive to set up)

**Warm-up exclusion rule**: None — the transition IS the measurement

**Primary metric**: Time from DNS zone link to consistent private IP resolution; meaningful effect threshold: >5 minutes

**Comparison method**: Descriptive statistics per sequencing strategy

## 7. Instrumentation

- Application code: DNS resolution polling every 30 seconds with resolved IP logging
- `nslookup`/`dig` from Kudu/console: direct DNS queries with TTL inspection
- Application Insights: dependency calls with resolved endpoint IP
- Azure Monitor: Private DNS Zone query logs

## 8. Procedure

_To be defined during execution._

## 9. Expected signal

- Zone-first deployment: brief NXDOMAIN period until A record is created → negative cache delays resolution by 5-30 minutes
- Simultaneous deployment: minimal negative cache impact, switch happens within positive TTL
- Custom DNS forwarder: additional caching layer adds 0-15 minutes delay
- Restart of compute service clears DNS cache and immediately resolves new IP

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

- DNS negative cache behavior depends on the VNet resolver implementation, which may change across regions
- Private DNS Zone link propagation has its own delay independent of DNS TTL
- Testing requires VNet integration on all compute services
- Clean up DNS zones and links completely between test runs to avoid cache contamination

## 16. Related guide / official docs

- [Azure Private Endpoint DNS configuration](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns)
- [Azure Private DNS zones](https://learn.microsoft.com/en-us/azure/dns/private-dns-overview)
- [What is Azure Private Link?](https://learn.microsoft.com/en-us/azure/private-link/private-link-overview)
- [Name resolution for resources in Azure virtual networks](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
