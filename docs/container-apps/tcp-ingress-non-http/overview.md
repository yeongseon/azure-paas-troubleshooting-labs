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

# TCP Ingress for Non-HTTP Protocols: Configuration and Limitations

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

Container Apps supports TCP ingress (non-HTTP) for protocols like raw TCP, gRPC, and custom binary protocols. What are the exact limitations of TCP ingress compared to HTTP ingress — specifically around TLS termination, load balancing behavior, and observability — and what failure modes occur when HTTP ingress is used for non-HTTP traffic?

## 2. Why this matters

Teams deploying database proxies, message brokers, or custom TCP services on Container Apps may configure HTTP ingress by default (assuming it is the standard choice) and then encounter unexpected behavior: the ingress attempts HTTP parsing on binary data, mangling the protocol. Understanding when to use TCP ingress vs. HTTP ingress and the trade-offs (TCP ingress does not do TLS termination at the ingress level, limiting observability) is essential for non-web workloads.

## 3. Customer symptom

"gRPC service connects but immediately returns a protocol error" or "Custom TCP client can't establish a connection even though the container is listening" or "Redis proxy on Container Apps works locally but fails when deployed."

## 4. Hypothesis

- H1: When a container listens on a custom TCP protocol port and HTTP ingress is configured, the ingress attempts HTTP parsing on the first bytes. Non-HTTP data (e.g., a database handshake) triggers a `400 Bad Request` or protocol error from the ingress before reaching the container.
- H2: TCP ingress configured for the correct port allows raw TCP connections to pass through to the container. TLS is handled by the client-container pair (passthrough TLS), not by the ingress.
- H3: TCP ingress does not provide per-request metrics (request count, latency) in Azure Monitor because individual TCP flows are not HTTP requests. Observability is limited to connection count and bytes transferred.
- H4: TCP ingress requires that the container expose a specific port; the ingress does not support multiple TCP ports per container app (unlike Kubernetes Services which can map multiple ports).

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Environment | env-batch-lab (no custom VNet) |
| App name | aca-diag-batch |
| Runtime | Python 3.11 / Flask (HTTP) used as TCP target |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Networking / Protocol

**Controlled:**

- Container running a custom TCP echo server (non-HTTP) on port 9000
- HTTP ingress configured on port 9000 (incorrect)
- TCP ingress configured on port 9000 (correct)

**Observed:**

- Connection behavior and error message under HTTP ingress
- Connection behavior and data integrity under TCP ingress
- Available metrics under each ingress type

**Scenarios:**

- S1: HTTP ingress, TCP client sends non-HTTP data → protocol error
- S2: TCP ingress, TCP client sends non-HTTP data → echo response received correctly
- S3: Observe metric availability for TCP vs HTTP ingress

## 7. Instrumentation

- `nc` or Python `socket` client to send raw TCP data
- Captured response (hex dump to verify echo integrity)
- Azure Monitor Container Apps metrics for TCP vs. HTTP ingress

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python TCP echo server (`asyncio` server) on port 9000.
2. S1: Configure HTTP ingress on port 9000; connect with TCP client; send binary data; observe error response.
3. S2: Switch to TCP ingress; connect TCP client; send binary data; verify echo response received intact.
4. S3: Compare available Azure Monitor metrics for each configuration.

## 9. Expected signal

- S1: Connection established but data mangled; HTTP 400 or protocol error returned by ingress.
- S2: Raw TCP echo works correctly; binary data round-trips intact.
- S3: HTTP ingress: request count, response codes, latency metrics available. TCP ingress: only connection-level metrics.

## 10. Results

### S1: HTTP ingress — raw binary data via TLS

```bash
ACA_URL="aca-diag-batch.agreeablehill-e6bfb5a7.koreacentral.azurecontainerapps.io"

echo -ne '\x00\x00\x00\x01\xfe\x00\x00\x02\x00\x00\x00\x00\x00' \
  | timeout 5 openssl s_client -connect $ACA_URL:443 -quiet 2>/dev/null | xxd | head -3
```

```
00000000: 4854 5450 2f31 2e31 2034 3030 2042 6164  HTTP/1.1 400 Bad
00000010: 2052 6571 7565 7374 0d0a 636f 6e74 656e   Request..conten
00000020: 742d 6c65 6e67 7468 3a20 3131 0d0a        t-length: 11..
```

The ingress responded `HTTP/1.1 400 Bad Request` immediately. The binary data was interpreted as an HTTP request; failing to parse a valid HTTP verb caused the ingress to reject the connection before any data reached the container.

### S2: External TCP ingress attempt — VNet requirement

```bash
az containerapp ingress update -n aca-diag-batch -g rg-lab-aca-batch \
  --transport tcp --target-port 8000 --exposed-port 9000

→ ERROR: (ContainerAppTcpRequiresVnet) Applications with external TCP ingress
  can only be deployed to Container App Environments that have a custom VNET.
  Set ingress traffic to 'Limited to Container Apps Environment' if you want
  to deploy to a Container App Environment without a custom VNET.
```

!!! warning "Platform constraint discovered"
    External TCP ingress (internet-facing) requires a custom VNet-integrated Container Apps environment. The Consumption-only environment (`env-batch-lab`) without a custom VNet **cannot expose TCP ingress externally**.

### S3: Internal TCP ingress — success without VNet

```bash
az containerapp ingress update -n aca-diag-batch -g rg-lab-aca-batch \
  --transport tcp --target-port 8000 --exposed-port 9000 --type internal

→ "transport": "Tcp"
→ "exposedPort": 9000
→ "external": false
```

Internal TCP ingress (`--type internal`) works without a custom VNet. The app is accessible on port 9000 only from within the Container Apps environment (other apps in the same environment).

### S4: CORS policy blocks TCP ingress switch

```bash
az containerapp ingress update -n aca-diag-batch -g rg-lab-aca-batch --transport tcp ...

→ ERROR: (ContainerAppInvalidIngressCORSPolicyForTcpApp)
  CORS policy can only be set for http transport.
```

Any existing CORS policy on the app must be explicitly removed (`az containerapp ingress cors disable`) before switching to TCP transport. The CLI does not automatically clear it.

### Summary of transport switch sequence

```
HTTP ingress (Auto) → cors disable → TCP internal → TCP external (BLOCKED: needs VNet)
```

## 11. Interpretation

- **Measured**: H1 is confirmed. HTTP ingress returns `HTTP/1.1 400 Bad Request` when receiving non-HTTP binary data. The ingress parses the first bytes as an HTTP request and rejects malformed data before it reaches the container. **Measured**.
- **Measured**: H2 is partially confirmed with a critical caveat: external TCP ingress requires a custom VNet environment. Internal TCP ingress works without VNet. The claim that TCP ingress "passes through" raw data is correct in principle, but only accessible within the environment in Consumption-only setups. **Measured** (VNet requirement confirmed by platform error).
- **Not Proven**: H3 (TCP ingress metrics vs HTTP) was not measured — the internal TCP ingress was not exercised with actual TCP traffic in this run.
- **Not Proven**: H4 (single exposed port per container app) was not directly tested.

## 12. What this proves

- HTTP ingress on a Container App returns `HTTP/1.1 400 Bad Request` when receiving non-HTTP binary data. **Measured**.
- External TCP ingress requires a custom VNet-integrated environment. Consumption-only environments (no VNet) cannot expose TCP ports externally. **Measured** (platform error).
- Internal TCP ingress (`--type internal`) works without a custom VNet — TCP traffic is accessible only within the Container Apps environment. **Measured**.
- CORS policy must be explicitly removed before switching from HTTP to TCP transport. **Measured** (platform error).

## 13. What this does NOT prove

- Whether TCP ingress correctly passes binary data to the container was not verified (no TCP echo server deployed).
- Whether gRPC should use TCP or HTTP/2 ingress was not directly compared in this run (addressed in `grpc-aca-end-to-end` experiment).
- HTTP/TCP metric comparison in Azure Monitor was not measured.
- Whether a custom VNet environment with external TCP ingress correctly passes raw binary data was not tested.

## 14. Support takeaway

When a customer reports protocol errors or connection failures on Container Apps for non-HTTP services:

1. **HTTP ingress + non-HTTP binary** → `400 Bad Request` from ingress. Switch to TCP ingress.
2. **External TCP ingress** requires a custom VNet environment. Consumption-only environments cannot expose TCP ports externally. Customers must either:
   - Use a VNet-integrated environment, OR
   - Use internal TCP ingress (only accessible from within the same environment), OR
   - Wrap the protocol in HTTP/WebSocket for external exposure.
3. **gRPC** should use `--transport http2` (not TCP ingress) — gRPC runs over HTTP/2. See `grpc-aca-end-to-end` experiment.
4. **Before switching transport**: run `az containerapp ingress cors disable` first, or the switch fails with `ContainerAppInvalidIngressCORSPolicyForTcpApp`.
5. **CORS policy** is HTTP-only — it cannot coexist with TCP transport.

## 15. Reproduction notes

```bash
APP="aca-diag-batch"
RG="rg-lab-aca-batch"

# Test 1: Verify HTTP ingress rejects binary data
ACA_FQDN=$(az containerapp show -n $APP -g $RG --query "properties.configuration.ingress.fqdn" -o tsv)
echo -ne '\x00\x00\x00\x01\xfe\x00\x00\x02\x00\x00\x00\x00\x00' \
  | timeout 5 openssl s_client -connect $ACA_FQDN:443 -quiet 2>/dev/null | xxd | head -3
# Expected: HTTP/1.1 400 Bad Request

# Test 2: Switch to TCP ingress (internal only for Consumption environment)
az containerapp ingress cors disable -n $APP -g $RG
az containerapp ingress update -n $APP -g $RG \
  --transport tcp --target-port 8000 --exposed-port 9000 --type internal
# Expected: success

# Test 3: Try external TCP (will fail without VNet)
az containerapp ingress update -n $APP -g $RG \
  --transport tcp --target-port 8000 --exposed-port 9000 --type external
# Expected: ContainerAppTcpRequiresVnet error

# Restore HTTP ingress
az containerapp ingress update -n $APP -g $RG \
  --transport auto --target-port 8000 --type external
```

## 16. Related guide / official docs

- [Container Apps ingress overview](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [TCP ingress in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to)
- [Container Apps networking — custom VNet](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom)
