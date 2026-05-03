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

# Traffic Manager Health Probe Misidentifying App Service as Unhealthy

!!! info "Status: Planned"

## 1. Question

When Azure Traffic Manager is fronting multiple App Service endpoints for multi-region failover, under what conditions does the Traffic Manager health probe incorrectly mark an App Service endpoint as degraded or offline, causing traffic to be routed to the secondary region unnecessarily?

## 2. Why this matters

Traffic Manager determines endpoint health based on HTTP/HTTPS probes to a configurable path. If the probe path requires authentication (returns 401/403), has a custom health check that fails transiently, or if the probe originates from IPs not whitelisted in App Service access restrictions, Traffic Manager marks the endpoint as unhealthy and failover occurs. This is a false positive failover — the app is serving production traffic correctly but Traffic Manager's probe fails, causing unnecessary cross-region latency for all users.

## 3. Customer symptom

"Traffic Manager shows our primary region as 'Degraded' but users can access the app directly" or "All traffic suddenly routed to our secondary region even though the primary app is healthy" or "Traffic Manager health probe fails intermittently but we can't reproduce the failure manually."

## 4. Hypothesis

- H1: When App Service access restrictions whitelist only corporate IP ranges and the Traffic Manager probe IPs (which change and come from Azure infrastructure ranges) are not whitelisted, probes return 403. Traffic Manager marks the endpoint as degraded.
- H2: When the probe path is set to `/` and the root path redirects to `/login` (302) rather than returning 200, Traffic Manager (which by default only accepts 200 as healthy) marks the endpoint as degraded.
- H3: When the probe interval is set to 30 seconds and a transient App Service recycle causes probe failures for one cycle, Traffic Manager requires a configured number of consecutive failures before failover. The exact failover threshold and recovery time are observable.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service (two regions: Korea Central, Japan East) |
| SKU / Plan | P1v3 |
| Region | Korea Central (primary), Japan East (secondary) |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Reliability

**Controlled:**

- Traffic Manager profile with Priority routing (Korea Central = 1, Japan East = 10)
- Health probe: HTTPS, path `/health`, interval 30s, timeout 10s, tolerated failures 3

**Observed:**

- Traffic Manager endpoint status (Healthy / Degraded / Offline)
- Failover time from probe failure to traffic rerouting
- Recovery time from restored probe health to traffic return

**Scenarios:**

- S1: `/health` returns 200 → endpoint healthy
- S2: Add access restriction blocking Traffic Manager probe IPs → endpoint degraded (false positive)
- S3: Change probe path to `/` which returns 302 → endpoint degraded
- S4: Trigger App Service restart → measure failover latency and recovery time

## 7. Instrumentation

- Traffic Manager **Endpoint monitoring** status in portal
- `dig <tm-profile>.trafficmanager.net` to observe DNS resolution changes
- App Service access log to confirm probe requests and response codes
- Azure Monitor Traffic Manager metrics: `EndpointStatus`, `QuerysServedByEndpoint`

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy identical apps in two regions; create Traffic Manager profile.
2. S1: Verify `/health` returns 200; confirm endpoint shows "Online."
3. S2: Add access restriction `Deny All` except `10.0.0.0/8`; wait for probe failures; observe endpoint status change and failover.
4. S3: Remove restrictions; change probe path to `/` (which redirects); observe degraded status.
5. S4: Restore `/health` probe; trigger App Service restart in primary; time from restart to failover start and from recovery to traffic return.

## 9. Expected signal

- S1: Endpoint shows "Online"; all DNS queries resolve to primary region.
- S2: After 3 failed probes (90 seconds), endpoint shows "Degraded"; DNS resolves to secondary.
- S3: 302 response causes "Degraded" status (Traffic Manager does not follow redirects by default).
- S4: Failover occurs within `tolerance × interval` seconds of restart; recovery occurs within 1-2 probe cycles after app is healthy.

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

- Traffic Manager probe IPs come from the Azure infrastructure range, not a fixed set. To allow probes through access restrictions, allow `AzureTrafficManager` service tag.
- Traffic Manager health probe does not follow HTTP redirects. The probe path must return 200 directly.
- The `Expected Status Code Ranges` feature allows accepting non-200 codes as healthy (e.g., 200-299 or specific 4xx codes for auth-protected paths).

## 16. Related guide / official docs

- [Traffic Manager endpoint monitoring](https://learn.microsoft.com/en-us/azure/traffic-manager/traffic-manager-monitoring)
- [Traffic Manager and App Service](https://learn.microsoft.com/en-us/azure/app-service/web-sites-traffic-manager)
- [AzureTrafficManager service tag](https://learn.microsoft.com/en-us/azure/virtual-network/service-tags-overview)
