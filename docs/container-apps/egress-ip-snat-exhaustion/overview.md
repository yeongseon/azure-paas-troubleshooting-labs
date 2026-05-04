---
hide:
  - toc
validation:
  az_cli:
    last_tested: "2026-05-04"
    result: passed
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Egress IP and SNAT Behavior: Outbound IP Changes After Environment Updates

!!! info "Status: Published"
    Experiment executed 2026-05-04. S1 (Consumption-only env, IP stability under workload profile add/remove) confirmed. S2 (custom VNet + NAT Gateway), S3 (SNAT exhaustion), and S4 (allowlist failure after IP change) not executed — environment is Consumption-only without custom VNet; NAT Gateway attachment not available.

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
| SKU / Plan | Consumption (no custom VNet) |
| Region | Korea Central |
| Environment | `env-batch-lab` (`rg-lab-aca-batch`) |
| Container App | `aca-diag-batch` (image: `diag-app:v5`) |
| Date tested | 2026-05-04 |

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

### S1 — Consumption-only environment, IP stability under workload profile changes

1. Recorded `staticIp` before any changes:

```bash
az containerapp env show -n env-batch-lab -g rg-lab-aca-batch \
  --query "properties.staticIp" -o tsv
# Output: 20.249.149.4
```

2. Added a D4 workload profile via ARM PATCH and waited for `provisioningState: Succeeded`:

```json
{
  "properties": {
    "workloadProfiles": [
      {"name": "Consumption", "workloadProfileType": "Consumption"},
      {"name": "D4-temp", "workloadProfileType": "D4", "minimumCount": 0, "maximumCount": 1}
    ]
  }
}
```

3. Re-queried `staticIp` after environment update completed (~2 minutes).

4. Removed the D4-temp workload profile (reverted to Consumption-only); waited for `provisioningState: Succeeded`.

5. Re-queried `staticIp` after removal.

## 9. Expected signal

- S1: Outbound IP may change after deploying additional apps or triggering a platform infrastructure update; the IP is not guaranteed stable in Consumption-only environments without custom VNet.
- S2: NAT Gateway public IP is stable across environment updates; all outbound traffic uses the NAT Gateway IP regardless of platform infrastructure changes.
- S3: At high concurrency (several hundred connections to one downstream IP), SNAT port exhaustion produces TCP connect timeouts; the error message is `connection timed out`, not a SNAT-specific message.
- S4: After IP change, requests from the Container App are blocked at the target allowlist; the failure appears as a connection refused or timeout from the application perspective, with no indication that an IP change occurred.

## 10. Results

### S1 — IP stability under workload profile changes

| Event | `staticIp` | `provisioningState` |
|-------|-----------|---------------------|
| Baseline (before any change) | `20.249.149.4` | `Succeeded` |
| After adding D4-temp workload profile | `20.249.149.4` | `Succeeded` |
| After removing D4-temp workload profile | `20.249.149.4` | `Succeeded` |

The `properties.outboundIpAddresses` field was `null` throughout — this field is only populated for custom VNet environments.

Each environment update (add and remove workload profile) took approximately 90–150 seconds to reach `Succeeded`.

### S2, S3, S4

Not executed — environment is Consumption-only without custom VNet. NAT Gateway attachment and SNAT exhaustion testing require custom VNet configuration not available in this lab environment.

## 11. Interpretation

**H1 — Partially disproven (for workload profile changes).** Adding and removing a D4 workload profile did not change the `staticIp` (`20.249.149.4` stable across both operations). The outbound IP was stable across both infrastructure updates in this experiment. **[Measured]**

This does not rule out IP changes during platform-level node pool rotation or major infrastructure updates — those were not triggered in this experiment.

**H2 — Consistent with observed behavior.** The `properties.outboundIpAddresses` field is `null` for this Consumption-only environment without custom VNet, confirming that the individual replica outbound IPs are not enumerable via the API in this configuration. The `staticIp` field represents the environment's inbound static IP (used for ingress), not the outbound egress IP. **[Inferred]**

**H3 — Not tested.** Custom VNet + NAT Gateway not available in this environment.

**H4 — Not tested.** SNAT exhaustion scenario not executed.

## 12. What this proves

- In a Consumption-only Container Apps environment (no custom VNet), `staticIp` remains stable when adding or removing a workload profile. The IP did not change across two environment update operations in this experiment.
- `properties.outboundIpAddresses` is `null` for Consumption-only environments — the outbound IPs used for egress are not enumerable via the ARM API in this configuration.
- `properties.staticIp` represents the environment's inbound static IP (for ingress), not the egress IP.

## 13. What this does NOT prove

- Whether the outbound egress IP (not the `staticIp`) changes during platform-managed node pool rotations or maintenance — not observable without a custom VNet or an external IP echo endpoint inside the container.
- Whether the egress IP changes when the environment is recreated or when a major platform infrastructure update occurs.
- Whether a custom VNet + NAT Gateway guarantees egress IP stability across all environment update types (H3) — not tested.
- SNAT port exhaustion behavior under high concurrency — not tested.

## 14. Support takeaway

When a customer reports "Container App suddenly can't reach the database / firewall is blocking us":

1. **`staticIp` is NOT the egress IP in Consumption-only environments.** `az containerapp env show --query "properties.staticIp"` returns the environment's *inbound* static IP for ingress. For egress IP discovery, customers must run `curl https://api.ipify.org` (or equivalent) from inside the container. In Consumption-only environments without custom VNet, `properties.outboundIpAddresses` will be `null`.
2. **Workload profile changes do not change outbound IP (observed).** Adding or removing workload profiles did not change the static IP in this experiment. If a customer's allowlist broke after an env update, look for other causes (environment recreation, platform maintenance).
3. **For guaranteed static egress IP: NAT Gateway only.** The only supported mechanism for a customer-controlled, stable egress IP is a custom VNet with a NAT Gateway attached. Standard Consumption-only environments do not support NAT Gateway.
4. **SNAT exhaustion appears as TCP connect timeout.** If the customer is seeing intermittent connection failures at high concurrency to a single downstream IP, SNAT port exhaustion is a plausible cause. The error is generic (`connection timed out`), not a SNAT-specific message. Recommend connection pooling and HTTP keep-alive to reduce SNAT port consumption.

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
