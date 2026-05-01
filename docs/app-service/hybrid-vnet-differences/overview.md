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

# Hybrid Connections vs VNet Integration: Outbound Connectivity Behavioral Differences

!!! info "Status: Planned"

## 1. Question

For outbound connectivity from App Service to on-premises or private network resources, what are the observable behavioral differences between Hybrid Connections and VNet Integration in terms of DNS resolution, connection latency, reliability under relay disruption, and IP address visibility at the target?

## 2. Why this matters

App Service offers two distinct outbound connectivity mechanisms: Hybrid Connections (relay-based, no VNet required) and VNet Integration (VNet-based, requires a delegated subnet). Customers frequently choose between them without understanding the underlying transport differences. Hybrid Connections route traffic through Azure Service Bus relay, introducing relay-specific latency and failure modes. VNet Integration routes traffic through the VNet, inheriting VNet-level DNS and routing rules. When connectivity fails, the error message at the application layer is often identical — a connection timeout — regardless of which mechanism failed. Support engineers need concrete behavioral anchors to distinguish the two.

## 3. Customer symptom

"My app can reach the on-premises database via Hybrid Connection but sometimes gets random timeouts" or "After enabling VNet Integration, my app can't reach on-premises resources even though Hybrid Connection worked" or "I can't tell whether the problem is the relay or the VNet routing."

## 4. Hypothesis

- H1: Hybrid Connections add measurable relay latency over direct VNet routing. Round-trip time via Hybrid Connection is higher than via VNet Integration for the same target endpoint, by an amount attributable to the Service Bus relay hop.
- H2: When the Hybrid Connection Relay is disrupted (e.g., Hybrid Connection Manager service stopped on-premises), the app receives a connection timeout after the TCP connect timeout expires. The error is a transport-level timeout, not a DNS failure, and the error message does not identify the relay as the failure point.
- H3: DNS resolution behavior differs between the two mechanisms. With VNet Integration, the app resolves private hostnames via the VNet's DNS server (Azure DNS or custom). With Hybrid Connections, DNS resolution occurs at the on-premises Hybrid Connection Manager host — the app sends the hostname to the relay, which resolves it locally. An app using VNet Integration cannot reach a hostname that is only resolvable on-premises via Hybrid Connection DNS.
- H4: At the target resource, the source IP of traffic arriving via VNet Integration is the VNet Integration subnet IP (or NAT Gateway IP). Traffic arriving via Hybrid Connection appears as the on-premises Hybrid Connection Manager host's IP. This difference affects firewall rules at the target.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Connectivity

**Controlled:**

- App Service with both Hybrid Connection and VNet Integration configured
- Target: a private HTTP endpoint reachable via both paths
- Hybrid Connection Manager installed on a VM in the target network
- VNet Integration subnet: `/28` delegated to App Service

**Observed:**

- Round-trip latency per connectivity method (measured at application layer)
- DNS resolution path (VNet DNS vs. on-premises resolver via HCM)
- Source IP at target endpoint (application log at target)
- Error type and message when relay is disrupted vs. when VNet route is disrupted
- Connection timeout duration per method

**Scenarios:**

- S1: Normal operation — measure latency via Hybrid Connection
- S2: Normal operation — measure latency via VNet Integration (same target)
- S3: Stop Hybrid Connection Manager on-premises — observe app error type and timing
- S4: Block VNet Integration subnet at NSG — observe app error type and timing
- S5: Private-only hostname (resolvable only on-premises) — test resolution via each method

**Independent run definition**: 100 sequential HTTP requests per method for latency measurement; one disruption event per fault scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- Application log: request timestamp, response time, source/target, error type
- `curl -w "%{time_namelookup} %{time_connect} %{time_total}"` — latency breakdown (DNS, TCP, total)
- Target endpoint log: source IP per request — identify VNet IP vs. HCM IP
- Hybrid Connection Manager Windows Event Log — relay connection status
- NSG flow logs — VNet Integration traffic confirmation
- `WEBSITE_PRIVATE_IP` app setting or `env` endpoint — confirm VNet Integration is active

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy app with Hybrid Connection to target VM; measure 100-request latency baseline (S1).
2. Enable VNet Integration to the same target; measure 100-request latency (S2); compare distributions.
3. Stop Hybrid Connection Manager service on the VM (S3); send request via Hybrid Connection; record error type, message, and timeout duration.
4. Apply NSG deny rule to VNet Integration subnet outbound (S4); send request via VNet Integration; record error type and timeout duration.
5. Configure a hostname resolvable only via on-premises DNS; attempt resolution via VNet Integration (S5a) and Hybrid Connection (S5b); confirm which method resolves successfully.

## 9. Expected signal

- S1 vs S2: VNet Integration shows lower RTT than Hybrid Connection by a consistent relay-overhead delta.
- S3: App receives TCP connect timeout after ~20–75 seconds; error message is generic `Connection refused` or `Connection timed out`; no relay-specific message.
- S4: NSG deny produces a TCP timeout with the same generic message as S3; indistinguishable at the application layer.
- S5: VNet Integration fails to resolve the private hostname (uses Azure DNS, not on-premises resolver); Hybrid Connection resolves successfully via HCM local DNS.

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

- Hybrid Connections require port 443 outbound from the HCM host to Azure Service Bus (`*.servicebus.windows.net`). If this port is blocked at the corporate firewall, HCM cannot connect and all Hybrid Connection traffic fails silently.
- VNet Integration requires a dedicated subnet with at least `/28` (16 IPs) delegated to `Microsoft.Web/serverFarms`. The subnet cannot be shared with other resources.
- The `WEBSITE_VNET_ROUTE_ALL=1` app setting (or equivalent routing configuration) is required for all outbound traffic to flow through the VNet; without it, only RFC 1918 traffic routes through the VNet.
- To isolate which connectivity method is active for a given request, the application should log the `X-Forwarded-For` header or the actual source IP as seen at the target.

## 16. Related guide / official docs

- [Hybrid Connections in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-hybrid-connections)
- [Integrate your app with an Azure virtual network](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration)
- [App Service networking features — comparison](https://learn.microsoft.com/en-us/azure/app-service/networking-features)
