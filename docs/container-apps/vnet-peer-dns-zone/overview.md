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

# VNet Peer Private DNS Zone Not Visible from Container Apps Environment

!!! warning "Status: Draft - Blocked"
    Execution blocked: VNet peering + private DNS zone required.

## 1. Question

When Container Apps is deployed in a VNet-integrated environment and a private DNS zone (e.g., `privatelink.database.windows.net`) is linked to a peered VNet but not to the Container Apps environment VNet directly, can the container app resolve private DNS names for services in the peered VNet?

## 2. Why this matters

Enterprise architectures often use VNet peering to connect a Container Apps environment VNet to a hub VNet where private endpoints and private DNS zones live. Private DNS zone auto-registration links zones to specific VNets. If the DNS zone is linked only to the hub VNet and not to the Container Apps VNet (spoke), the containers cannot resolve private endpoint FQDNs — they fall through to public DNS and get the public IP, bypassing the private endpoint entirely. This causes connections to fail or to route over the public internet, violating security requirements.

## 3. Customer symptom

"Container app can't connect to our private Azure SQL — it worked in the hub VNet but not from Container Apps" or "DNS resolves to a public IP instead of the private endpoint IP" or "We have VNet peering set up but the private endpoint is unreachable."

## 4. Hypothesis

- H1: When a private DNS zone is linked to the hub VNet only (not to the Container Apps spoke VNet), DNS queries from containers in the spoke resolve via the default Azure DNS resolver, which does not have visibility into the hub-linked private DNS zone. The FQDN resolves to the public IP.
- H2: Linking the private DNS zone to the Container Apps environment VNet (spoke) resolves the issue — containers can resolve the private endpoint FQDN to its private IP.
- H3: Alternatively, deploying a custom DNS server in the hub VNet that is configured as the DNS resolver for the spoke VNet can forward queries to the hub's DNS, resolving the private zone without linking it to the spoke.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption (VNet-integrated) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / DNS

**Controlled:**

- Container Apps environment VNet (spoke) peered with hub VNet
- Azure SQL with private endpoint in hub VNet
- Private DNS zone `privatelink.database.windows.net` linked to hub VNet

**Observed:**

- DNS resolution result for the SQL FQDN from inside the container
- Connection success/failure to the private endpoint

**Scenarios:**

- S1: DNS zone linked to hub VNet only → private FQDN resolves to public IP (failure)
- S2: DNS zone linked to both hub and spoke VNets → private FQDN resolves to private IP (success)
- S3: Custom DNS forwarder in hub as spoke DNS server → private FQDN resolves to private IP (alternative solution)

## 7. Instrumentation

- Container debug shell: `nslookup <sql-server>.database.windows.net` and `dig <sql-server>.privatelink.database.windows.net`
- Python `/dns-check` endpoint that resolves the FQDN and returns the IP
- Azure Private DNS zone records (verify A record for the private endpoint)
- Network Watcher connection check from container to SQL private endpoint

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Azure SQL with private endpoint in hub VNet; private DNS zone linked to hub only.
2. Deploy Container Apps in VNet-integrated environment (spoke VNet); peer spoke to hub.
3. S1: From container, resolve SQL FQDN; confirm it returns the public IP; attempt connection (expect failure or public routing).
4. S2: Link private DNS zone to spoke VNet; wait for DNS propagation; resolve SQL FQDN again; confirm private IP returned; connection succeeds.
5. S3: Remove zone link from spoke; deploy custom DNS server in hub; configure spoke VNet DNS server setting to hub DNS server IP; verify resolution.

## 9. Expected signal

- S1: `nslookup` returns public IP (`104.x.x.x`); TCP connection to port 1433 fails or routes over public internet.
- S2: `nslookup` returns private IP (`10.x.x.x`); TCP connection succeeds via private endpoint.
- S3: Same resolution result as S2 via custom DNS forwarding.

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

- Private DNS zone must be linked to every VNet that needs to resolve names in that zone. VNet peering does NOT automatically extend DNS zone visibility.
- Container Apps environment VNet is created by the platform; find it in the resource group under **VNet Integration**.
- Azure DNS Private Resolver can be used as an alternative to custom DNS servers for hub-and-spoke DNS forwarding.

## 16. Related guide / official docs

- [Private endpoints and DNS in Azure](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns)
- [Container Apps VNet integration](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom)
- [Azure DNS Private Resolver](https://learn.microsoft.com/en-us/azure/dns/dns-private-resolver-overview)
