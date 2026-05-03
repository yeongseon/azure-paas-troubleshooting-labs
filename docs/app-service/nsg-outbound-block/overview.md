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

# NSG Outbound Block: Silent Connectivity Failure to External Services

!!! info "Status: Planned"

## 1. Question

When App Service is integrated with a VNet, and an NSG on the integration subnet has an outbound deny rule, outbound connections to blocked destinations fail silently (TCP timeout rather than immediate reset). How long does the timeout take, what error does the application see, and how does the diagnostic path differ from a DNS resolution failure?

## 2. Why this matters

NSG outbound deny rules cause TCP connections to time out rather than receive an immediate RST. From the application's perspective, the call hangs for the full connection timeout (typically 20-75 seconds) before failing. This causes cascading timeouts in production: a blocked external API call ties up a thread for 30+ seconds, which depletes the thread pool and causes all subsequent requests to queue up. Engineers often cannot distinguish NSG blocking from DNS failure or slow service responses without checking NSG flow logs.

## 3. Customer symptom

"External API calls hang for 30 seconds and then fail — but not always, and not for every destination" or "After adding VNet Integration, everything slowed down" or "We added a new NSG rule for compliance and the app started timing out on some calls."

## 4. Hypothesis

- H1: An NSG deny rule (without explicit Allow) causes outbound TCP connections to time out rather than receive an immediate TCP RST. The connection attempt hangs for the OS TCP SYN timeout (typically 20 seconds in Azure) before the application sees a `connect timed out` error.
- H2: An NSG deny rule that returns an ICMP Unreachable (if configured) would produce an immediate connection refused error. In practice, Azure NSG deny rules silently drop packets (no ICMP response), producing the timeout behavior.
- H3: DNS resolution failure (wrong name, missing DNS entry) produces an immediate error (NXDOMAIN or timeout at the DNS query level, typically 2-5 seconds) that is distinguishable from NSG-blocked TCP by the error type and timing.
- H4: NSG flow logs (when enabled on the NSG) record the blocked flow with `DenyAllOutbound` or the specific deny rule name, allowing precise identification of which rule is blocking which destination.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 with VNet Integration |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Diagnostics

**Controlled:**

- App Service with VNet Integration to a /24 subnet
- NSG on the integration subnet with selective outbound deny rules
- External target: `https://httpbin.org/delay/1` (known good endpoint)

**Observed:**

- Time from connection attempt to error
- Error message and type
- NSG flow log entries

**Scenarios:**

- S1: No NSG (or allow all) → immediate connection, ~1s response
- S2: NSG deny rule for port 443 to all internet destinations → timeout behavior
- S3: NSG deny rule only for specific destination IP → other destinations unaffected
- S4: DNS failure (wrong hostname) → immediate NXDOMAIN vs. NSG block timeout

## 7. Instrumentation

- Application timing log for outbound call duration
- NSG flow logs (enable on the NSG in **Monitoring > NSG flow logs**)
- Network Watcher **IP Flow Verify** tool to check if NSG would block
- `curl --connect-timeout 5 https://httpbin.org` via Kudu SSH to measure timeout

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python app with `/call-external?url=<target>` endpoint that times the outbound call.
2. S1: No NSG restriction; call `httpbin.org`; verify ~1s response time.
3. S2: Add NSG deny rule for TCP 443 outbound; repeat call; measure timeout (expect 20+ seconds then error).
4. S3: Scope deny rule to `httpbin.org` IP only; verify other HTTPS destinations still work.
5. S4: Call a nonexistent hostname; measure time to error; compare with NSG block timing.
6. Check NSG flow logs for the S2 blocked connection entry.

## 9. Expected signal

- S1: Response in ~1 second.
- S2: Call hangs for 20-30 seconds; error is `connect timed out` or `Connection timeout`; NSG flow log shows blocked flow.
- S3: Blocked destination times out; other destinations respond normally.
- S4: DNS failure returns immediately (within 5 seconds) with `Name or service not known`; distinguishable from NSG block by timing and error type.

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

- Enable NSG flow logs via **Network Watcher > NSG flow logs** — this is not enabled by default.
- NSG deny rules without `Action=Allow` silently drop packets in Azure; they do not send TCP RST or ICMP Unreachable.
- For App Service without VNet Integration, outbound traffic does not pass through NSGs. VNet Integration is required for NSG outbound rules to take effect.
- The `AzureMonitor` service tag must be allowed outbound for Application Insights telemetry to flow correctly.

## 16. Related guide / official docs

- [App Service networking features: VNet Integration](https://learn.microsoft.com/en-us/azure/app-service/networking-features#regional-virtual-network-integration)
- [NSG flow logs](https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-nsg-flow-logging-overview)
- [Network Watcher IP Flow Verify](https://learn.microsoft.com/en-us/azure/network-watcher/ip-flow-verify-overview)
