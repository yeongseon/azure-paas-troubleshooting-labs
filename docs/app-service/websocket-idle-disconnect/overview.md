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

# WebSocket Idle Disconnect Without Keepalive

!!! info "Status: Planned"

## 1. Question

App Service has an idle connection timeout at the frontend layer. What is the exact idle timeout for WebSocket connections, and at what point does the platform terminate an idle WebSocket — and does the client receive a clean close frame or an abrupt TCP reset?

## 2. Why this matters

Long-lived WebSocket connections are used for real-time applications (chat, live dashboards, collaborative tools). When the App Service frontend terminates an idle WebSocket, the client library may not detect the disconnect immediately (especially in browser environments where the close event can be delayed). This leads to clients believing they are connected while messages are being silently dropped, causing data consistency issues that appear as bugs in the application logic rather than platform networking behavior.

## 3. Customer symptom

"WebSocket connections drop every few minutes even with no errors in the application" or "The client thinks it's connected but stops receiving messages" or "We see regular reconnection events in our client logs at exact intervals, even during quiet periods."

## 4. Hypothesis

- H1: App Service has a frontend idle connection timeout (believed to be 240 seconds for standard SKUs). An idle WebSocket connection (no frames sent in either direction) is terminated by the platform after this period.
- H2: The termination is a TCP RST (not a clean WebSocket close frame with opcode 0x8). The client's WebSocket `close` event fires, but the `code` is `1006` (abnormal closure) rather than `1000` (normal closure), indicating an unclean disconnect.
- H3: Sending a WebSocket ping frame (or any frame, including an application-level heartbeat) from either the client or server resets the idle timer. An application-level keepalive every 60 seconds prevents the idle disconnect.
- H4: The `WEBSITE_IDLE_TIMEOUT_IN_MINUTES` app setting controls the site idle timeout (which triggers worker recycle) but does NOT control the frontend connection idle timeout.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 |
| Region | Korea Central |
| Runtime | Node.js 20 (ws library) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Platform behavior

**Controlled:**

- WebSocket server (Node.js `ws`) deployed on App Service
- Client connecting from a VM in the same region
- tcpdump on client side to capture TCP-level disconnect behavior

**Observed:**

- Time to disconnect from last frame sent
- Disconnect type (TCP RST vs clean close frame)
- WebSocket close code received by client
- Keepalive frame interval required to prevent disconnect

**Scenarios:**

- S1: Idle WebSocket — measure time to disconnect
- S2: Ping frame every 60 seconds — verify no disconnect
- S3: Application-level heartbeat (custom message) every 60 seconds — verify no disconnect
- S4: Check disconnect behavior on B1 SKU vs P1v3

## 7. Instrumentation

- `tcpdump -i any -w /tmp/ws-capture.pcap port 443` on client VM
- Wireshark analysis of captured traffic (FIN vs RST, WebSocket close frame presence)
- Node.js `ws` library `close` event handler logging: `code`, `reason`, `wasClean`
- App Service connection metrics in Azure Monitor

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy a WebSocket echo server on App Service.
2. S1: Connect from a client VM; send no frames after connection; capture time until `close` event fires; check `code` and `wasClean`.
3. S2: Connect and send a WebSocket `ping` frame every 60 seconds; verify connection remains alive for 10+ minutes.
4. S3: Replace ping with an application JSON message `{"type":"heartbeat"}` every 60 seconds; verify same result.
5. S4: Repeat S1 on B1 SKU to check if timeout differs across plan tiers.
6. Analyze tcpdump to confirm RST vs FIN.

## 9. Expected signal

- S1: Connection terminates at ~240 seconds of idle; client receives `close` event with `code=1006`, `wasClean=false`; tcpdump shows TCP RST.
- S2–S3: Connection remains alive indefinitely with keepalive.
- S4: Timeout is the same across SKUs (platform-level behavior, not SKU-dependent).

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

- WebSocket must be enabled explicitly on Windows App Service: **Configuration > General settings > Web sockets = On**. Linux App Service has it enabled by default.
- ARR Affinity must be enabled when scaling out to ensure WebSocket clients reconnect to the same instance (WebSocket state is instance-local).
- The frontend timeout is a platform infrastructure setting and cannot be configured by the customer via any app setting.

## 16. Related guide / official docs

- [WebSockets support in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#websockets)
- [Azure App Service networking features](https://learn.microsoft.com/en-us/azure/app-service/networking-features)
