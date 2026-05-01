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

# Private Endpoint DNS Misconfiguration: Missing or Wrong Zone Link

!!! info "Status: Planned"

## 1. Question

When a Private Endpoint is attached to an App Service but the required Private DNS Zone (`privatelink.azurewebsites.net`) is not linked to the VNet, or the zone contains incorrect A records, what failure modes occur for inbound and SCM traffic — and how does the failure surface differ from a correctly configured Private Endpoint?

## 2. Why this matters

Private Endpoint for App Service requires a Private DNS Zone linked to the consumer VNet to resolve the app's FQDN to the private IP. When this zone is missing, incorrectly scoped, or linked to the wrong VNet, the app may resolve to its public IP (bypassing the private endpoint) or fail to resolve entirely. Support engineers frequently confuse this with a Private Endpoint connectivity issue rather than a DNS misconfiguration.

## 3. Customer symptom

"I configured a Private Endpoint for my App Service but requests still go over the public internet" or "My app is unreachable from my VNet even though the Private Endpoint shows as Approved."

## 4. Hypothesis

- H1: Without a Private DNS Zone link, `nslookup <app>.azurewebsites.net` from within the VNet resolves to the public IP, not the private endpoint IP.
- H2: With the zone linked but missing the A record for the SCM hostname (`<app>.scm.azurewebsites.net`), ZIP Deploy and Kudu fail while the main site is reachable.
- H3: With the Private DNS Zone linked to a different VNet than the one containing the client VM, DNS resolution still falls through to public DNS.
- H4: Application-layer reachability (HTTP 200) is not sufficient to confirm private endpoint routing; the resolved IP must be validated separately.

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

**Experiment type**: Networking / Configuration

**Controlled:**

- App Service with Private Endpoint enabled, public network access disabled
- Client VM in the same VNet as the Private Endpoint
- DNS resolution tool (`nslookup`, `dig`, `curl`)

**Observed:**

- Resolved IP address for main FQDN and SCM FQDN under each DNS zone configuration
- HTTP reachability from client VM (main site, SCM, zipdeploy)
- Error message and error type at the client
- Time-to-failure for DNS resolution

**Scenarios:**

- S1: No Private DNS Zone — zone does not exist
- S2: Zone exists but not linked to the client VNet
- S3: Zone linked to client VNet, but SCM A record (`<app>.scm.azurewebsites.net`) is missing
- S4: Correct zone, correct records, correct link (baseline / control)

**Independent run definition**: One DNS resolution attempt + HTTP request pair per scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `nslookup <app>.azurewebsites.net` from client VM in VNet
- `nslookup <app>.scm.azurewebsites.net` from client VM
- `curl -v https://<app>.azurewebsites.net` — connection details including resolved IP
- Azure Portal: Private Endpoint > DNS Configuration — verify A record presence
- App Service Activity Log — access log entries to distinguish public vs. private IP hits
- Network Watcher: IP flow verify — confirm routing path

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy App Service with Private Endpoint; disable public network access.
2. Run Scenario S1 (no Private DNS Zone): resolve main FQDN and SCM FQDN from client VM; record IPs and HTTP result.
3. Create Private DNS Zone without VNet link (S2): repeat DNS + HTTP test.
4. Link zone to client VNet but omit SCM A record (S3): test main site and SCM separately.
5. Complete configuration (S4): validate full resolution and reachability.
6. Record resolved IPs and HTTP status codes across all scenarios.

## 9. Expected signal

- S1: Resolves to public CNAME/IP; HTTP may succeed (public IP still accessible) or fail (public access disabled).
- S2: Same as S1 — zone link is required for resolution to private IP.
- S3: Main FQDN resolves correctly to private IP; SCM FQDN resolves to public IP or NXDOMAIN.
- S4: Both FQDNs resolve to private IPs; full reachability confirmed.

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

- The Private DNS Zone must contain A records for both `<app>` and `<app>.scm` pointing to the private endpoint IP.
- Disabling public network access is essential to isolate the private path; with public access enabled, failures may be masked.
- Client VM must be in the same VNet that the Private DNS Zone is linked to (or a peered VNet with zone linking).
- DNS TTL is typically 300 seconds; flush the DNS cache on the client VM between scenario switches.

## 16. Related guide / official docs

- [Private Endpoint DNS configuration values](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns)
- [Use Private Endpoints for Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/networking/private-endpoint)
- [Access restrictions and Private Endpoints (SCM)](https://learn.microsoft.com/en-us/azure/app-service/overview-access-restrictions)
