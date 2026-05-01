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

# Egress IP and SNAT Behavior: Outbound IP Changes After Environment Updates

!!! info "Status: Planned"

## 1. Question

When a Container Apps environment is updated — by adding a new workload profile, changing the environment infrastructure, or rotating platform-managed infrastructure — does the environment's outbound IP address change, and how does this manifest for dependent resources (firewall rules, allowlists) that are pinned to the previous outbound IP?

## 2. Why this matters

Container Apps environments expose a set of static outbound IPs that customers use to allowlist traffic at downstream firewalls, storage accounts, databases, and third-party APIs. Unlike App Service, which provides a documented set of outbound IPs per instance, Container Apps environment outbound IPs are associated with the environment's infrastructure and may change during platform operations or environment updates. When an outbound IP changes without notice, downstream allowlists become stale, causing connection failures that appear as network errors or authentication failures at the application layer, not as IP change notifications.

## 3. Customer symptom

"Our Container App suddenly can't reach the database — the connection was working yesterday" or "The third-party API is blocking our requests even though we allowlisted the IP" or "After we updated the environment, our firewall rules stopped working."

## 4. Hypothesis

- H1: The outbound IP(s) of a Container Apps environment are stable under normal operations but may change when the environment's underlying infrastructure is updated (e.g., workload profile addition, platform-managed node pool rotation). The change is not announced proactively by the platform.
- H2: In a Consumption-only environment without a custom VNet, outbound IPs are shared with other tenants and are managed by the platform. They can change without customer action. The current outbound IPs are discoverable via `az containerapp env show` but are not guaranteed to be stable across platform maintenance windows.
- H3: In a custom VNet environment with a NAT Gateway attached, the outbound IP is the NAT Gateway's public IP — which is customer-controlled and stable. Attaching a NAT Gateway is the only mechanism to guarantee a static outbound IP for Container Apps.
- H4: SNAT port exhaustion (too many concurrent outbound connections from a single environment to a single downstream IP) produces connection failures that appear as connection timeouts at the application layer, not as SNAT-specific errors. The failure is intermittent and load-dependent, making it difficult to distinguish from network instability.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption (with and without custom VNet + NAT Gateway) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Stability

**Controlled:**

- Container Apps environment (Consumption-only, no custom VNet) — outbound IP discovery
- Container Apps environment (custom VNet + NAT Gateway) — static IP verification
- Target: an HTTP endpoint that logs the caller's source IP per request
- Environment update trigger: adding a new app to the environment, scaling event

**Observed:**

- Outbound IP before and after environment update (`az containerapp env show --query "properties.staticIp"`)
- Source IP as seen at the target endpoint per request
- SNAT port exhaustion: concurrent connection count vs. connection failure rate
- NAT Gateway IP stability across environment updates

**Scenarios:**

- S1: Consumption-only environment — record outbound IP; deploy new app; record outbound IP again
- S2: Custom VNet + NAT Gateway — record NAT Gateway public IP; trigger environment update; confirm IP unchanged
- S3: SNAT exhaustion — open many concurrent connections from one environment to one downstream IP; observe failure rate and error type
- S4: Allowlist at target based on old outbound IP; trigger IP change; observe connection failure from application

**Independent run definition**: One environment update or connection test per scenario.

**Planned runs per configuration**: 3

## 7. Instrumentation

- `az containerapp env show --name <env> --resource-group <rg> --query "properties.staticIp"` — outbound IP before/after update
- Target endpoint log: `X-Forwarded-For` or direct connection source IP per request
- `curl -s https://api.ipify.org` from inside the container — actual outbound IP in use
- SNAT test: `hey -n 10000 -c 500 https://<target>` — high-concurrency load to one downstream IP
- NAT Gateway: `az network public-ip show --name <pip> --query "ipAddress"` — public IP of NAT Gateway

## 8. Procedure

_To be defined during execution._

### Sketch

1. S1: Deploy app to Consumption-only environment; call `curl https://api.ipify.org` from container to record outbound IP; deploy a second app; re-check outbound IP from first app.
2. S2: Deploy app to custom VNet environment with NAT Gateway; record NAT Gateway public IP; add a new workload profile to the environment; re-check outbound IP from container.
3. S3: Generate 500 concurrent connections from the Container App to a single downstream HTTP endpoint; record connection error rate as concurrency increases; identify the failure type (reset, timeout).
4. S4: Allowlist the outbound IP from S1 at the target; trigger an environment update that changes the outbound IP; confirm subsequent requests are blocked at the allowlist.

## 9. Expected signal

- S1: Outbound IP may change after deploying additional apps or triggering a platform infrastructure update; the IP is not guaranteed stable in Consumption-only environments without custom VNet.
- S2: NAT Gateway public IP is stable across environment updates; all outbound traffic uses the NAT Gateway IP regardless of platform infrastructure changes.
- S3: At high concurrency (several hundred connections to one downstream IP), SNAT port exhaustion produces TCP connect timeouts; the error message is `connection timed out`, not a SNAT-specific message.
- S4: After IP change, requests from the Container App are blocked at the target allowlist; the failure appears as a connection refused or timeout from the application perspective, with no indication that an IP change occurred.

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

- `az containerapp env show --query "properties.staticIp"` returns the environment's static IP, but this may differ from the actual outbound IP used for egress in Consumption-only environments. Use `curl https://api.ipify.org` from within the container for the true outbound IP.
- Attaching a NAT Gateway to a custom VNet is the only supported mechanism for a stable, customer-controlled outbound IP in Container Apps. Consumption-only environments without custom VNet do not support NAT Gateway attachment.
- SNAT port exhaustion in Container Apps environments is less common than in App Service (where per-instance SNAT limits are well-documented), but can occur at high concurrency to a single downstream IP. Use connection pooling and HTTP keep-alive to reduce SNAT port consumption.
- For custom VNet environments, outbound IPs are determined by the VNet routing (UDR, NAT Gateway, or default internet routing); the `properties.staticIp` field reflects the environment's internal IP, not the public egress IP.

## 16. Related guide / official docs

- [Networking in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Control outbound traffic with NAT Gateway in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking#nat-gateway)
- [SNAT in Azure — outbound connections](https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-outbound-connections)
- [Outbound IPs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking#outbound-ip-addresses)
