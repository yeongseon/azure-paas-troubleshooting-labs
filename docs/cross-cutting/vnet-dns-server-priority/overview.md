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

# VNet DNS Server Priority and Fallback

!!! warning "Status: Draft - Awaiting Execution"
    Cross-cutting experiment (App Service + Functions + Container Apps). Awaiting execution.

## 1. Question

When a VNet has multiple custom DNS servers configured, in what order are they queried? Is there a fallback to Azure's default DNS resolver (168.63.129.16) if all custom servers are unreachable? How does this differ across App Service, Functions (Flex), and Container Apps?

## 2. Why this matters

VNet custom DNS configuration is one of the most common sources of cross-service networking failures. When organizations use custom DNS servers (on-premises forwarders, CoreDNS, dnsmasq) and those servers become unreachable, the question of whether Azure falls back to its default DNS resolver is critical for understanding outage scope.

Support cases arise when:
- One of multiple custom DNS servers fails and resolution becomes intermittent (round-robin DNS queries)
- A customer expects fallback to Azure DNS but their resources in Azure cannot resolve `*.azure.com`
- DNS resolution behavior differs between App Service and Container Apps in the same VNet

## 3. Customer symptom

- "DNS resolution is intermittent — sometimes it works, sometimes it fails."
- "After our on-premises DNS server went down, our app can't resolve Azure Storage."
- "We have two DNS servers but traffic seems to alternate between them — some queries fail."
- "App Service can resolve the name but Container Apps in the same VNet cannot."

## 4. Hypothesis

**H1 — Multiple DNS servers are queried round-robin**: When multiple DNS servers are configured on the VNet, queries are distributed across them. A single failing server causes ~50% of DNS queries to fail (intermittent failure).

**H2 — No automatic fallback to Azure DNS (168.63.129.16)**: If all configured custom DNS servers are unreachable, Azure does NOT automatically fall back to the Azure DNS resolver. Resolution fails completely.

**H3 — Exception: Azure-internal names**: Even with custom DNS configured, some Azure-internal name resolutions (e.g., IMDS endpoint `169.254.169.254`, and platform-internal names) may bypass custom DNS and use the platform resolver.

**H4 — Container Apps has different DNS behavior**: Container Apps environments with custom DNS may apply the custom DNS at the environment level, while App Service VNet integration applies DNS at the instance level. The failure mode and recovery timing may differ.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Services | App Service (P1v3), Container Apps (Consumption), Functions (Consumption) |
| VNet | Custom VNet with 2 custom DNS servers |
| Region | Korea Central |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Networking + DNS

**Controlled:**

- Number of custom DNS servers (1, 2)
- Custom DNS server availability (both up, one down, both down)
- Query target: Azure Storage FQDN, custom domain, Azure AD endpoint
- Service being tested: App Service, Functions, Container Apps

**Observed:**

- DNS resolution success rate per service during each server availability state
- Resolution latency during round-robin vs. single server
- Whether IMDS (`169.254.169.254`) resolves when custom DNS is down
- Recovery time after DNS server recovery

## 7. Instrumentation

- Python diagnostic endpoint: `GET /dns-test?hostname=<fqdn>` using `socket.getaddrinfo`
- Runs on App Service, Functions (HTTP trigger), and Container Apps simultaneously
- Load generator: 100 DNS resolutions over 30s to measure failure rate
- Network Watcher: DNS resolution test (if available)

**DNS test across services:**

```python
import socket, time

def test_dns(hostname, attempts=10):
    results = []
    for _ in range(attempts):
        try:
            start = time.time()
            socket.getaddrinfo(hostname, None)
            results.append({"success": True, "latency_ms": (time.time()-start)*1000})
        except Exception as e:
            results.append({"success": False, "error": str(e)})
    return results
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
# VNet with 2 custom DNS servers (simulated with Azure VMs running dnsmasq)
az network vnet create --name vnet-dns-test --resource-group rg-dns-test \
  --dns-servers 10.0.0.4 10.0.0.5
```

### 8.2 Scenarios

**S1 — Both DNS servers available**: Baseline. Measure resolution success rate, latency distribution.

**S2 — One DNS server down**: Shut down DNS VM 1. Measure intermittent failure rate and latency spike.

**S3 — Both DNS servers down**: Shut down both DNS VMs. Measure complete failure. Verify whether IMDS resolves (as indicator of platform DNS bypass).

**S4 — Recovery**: Restart DNS VM 1. Measure time until resolution success rate returns to 100%.

**S5 — Cross-service comparison**: Run S1-S4 simultaneously on App Service, Container Apps, and Functions. Compare failure rates and recovery times.

## 9. Expected signal

- **S1**: 100% success rate, ~1–5ms resolution latency.
- **S2**: ~50% failure rate (round-robin to the dead server). Latency bimodal: fast for working server, timeout (~5s) for dead server.
- **S3**: 100% failure for public hostnames. IMDS may still resolve (platform bypass).
- **S4**: Recovery within 30–60s of DNS server restart.
- **S5**: App Service and Container Apps may have different failure rates due to different DNS caching at the platform level.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Setting up two DNS server VMs requires infrastructure. This is a blocked experiment until a suitable test subscription is available.
- Container Apps DNS behavior may have changed across platform versions.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Multiple DNS servers queried round-robin | **Strongly Suggested** (standard VNet DNS behavior) |
| No automatic fallback to Azure DNS | **Inferred** |
| IMDS resolves even without custom DNS | **Inferred** |

## 14. Related experiments

- [Custom DNS Resolution (App Service)](../../app-service/custom-dns-resolution/overview.md) — App Service DNS resolution behavior
- [Custom DNS Forwarding (Container Apps)](../../container-apps/custom-dns-forwarding/overview.md) — Container Apps DNS failure
- [PE DNS Negative Cache](../pe-dns-negative-cache/overview.md) — DNS negative caching

## 15. References

- [Azure VNet custom DNS documentation](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances)
- [Azure DNS resolver 168.63.129.16](https://learn.microsoft.com/en-us/azure/virtual-network/what-is-ip-address-168-63-129-16)

## 16. Support takeaway

For intermittent DNS failures in VNet-integrated services:

1. With multiple custom DNS servers, a single failing server causes ~50% of DNS queries to fail — the characteristic signature is intermittent, not consistent failure.
2. There is NO automatic fallback to Azure DNS (168.63.129.16) when all custom DNS servers fail. This is intentional — custom DNS is authoritative for the VNet.
3. Exception: some platform operations (IMDS access at `169.254.169.254`, platform-internal endpoints) may bypass custom DNS. This means managed identity token acquisition might work even when external DNS fails.
4. Add Azure DNS (168.63.129.16) as the last DNS server in the VNet configuration for fallback capability — this gives the VNet custom resolution for internal names with Azure DNS as the fallback for Azure-native names.
