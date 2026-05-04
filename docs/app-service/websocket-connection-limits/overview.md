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

# WebSocket Connection Limits and Idle Disconnection

!!! warning "Status: Draft - Awaiting Execution"
    Experiment designed. Awaiting execution.

## 1. Question

How many concurrent WebSocket connections does App Service support per instance and per plan tier? At what idle duration does App Service terminate a WebSocket connection, and can periodic ping frames prevent disconnection?

## 2. Why this matters

WebSocket-based applications (real-time dashboards, collaborative tools, chat, live data feeds) are increasingly deployed on App Service. Customers frequently encounter:
- WebSocket connections dropping after an exact duration (commonly 3 minutes 50 seconds)
- Client libraries that don't implement WebSocket ping/pong and experience unexpected disconnects
- Applications that work locally but fail in App Service due to WebSocket-specific limitations
- Confusion between WebSocket idle timeout (App Service ARR) and HTTP request timeout (different mechanism)

## 3. Customer symptom

- "Our WebSocket connection drops after exactly 4 minutes of no activity."
- "We're implementing a real-time dashboard but connections keep disconnecting."
- "Works fine locally but in App Service the connection breaks intermittently."
- "How many concurrent WebSocket connections can one App Service instance handle?"

## 4. Hypothesis

**H1 — Idle timeout causes disconnection**: ARR (Application Request Routing) on App Service enforces an idle timeout on all connections including WebSocket. After a period of no bytes sent or received (typically 230–240 seconds, same as HTTP), the connection is terminated.

**H2 — Ping frames prevent disconnection**: Sending WebSocket Ping frames (or application-level heartbeat messages) at intervals shorter than the idle timeout prevents disconnection by resetting the idle timer.

**H3 — Connection limit per instance**: Each App Service instance has a finite number of concurrent WebSocket connections it can maintain. The limit varies by SKU.

**H4 — ARR affinity required for multi-instance**: With multiple instances and WebSocket, ARR affinity (sticky sessions) is required. Without it, the WebSocket upgrade request may be routed to one instance while subsequent requests go to another, breaking the persistent connection.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | App Service |
| SKU / Plan | B1 Linux, P1v3 Linux |
| Region | Korea Central |
| Runtime | Python 3.11 (websockets library) |
| OS | Linux |
| Date tested | Not yet executed |

## 6. Variables

**Experiment type**: Network + Connection

**Controlled:**

- WebSocket idle duration (0s, 60s, 120s, 180s, 240s, 300s — no bytes sent)
- Ping frame frequency (none, 30s, 60s, 120s)
- Number of concurrent connections (10, 100, 500, 1000)
- ARR affinity: enabled vs. disabled

**Observed:**

- Time-to-disconnect for idle WebSocket connections
- Whether ping frames extend connection lifetime
- Maximum concurrent connections before new connections are rejected
- Error code/message on ARR-forced disconnect

## 7. Instrumentation

- WebSocket server: Python `websockets` library, echo server
- Client load generator: `wscat` or custom Python script, multiple concurrent connections
- Custom metric: connection duration histogram per client
- App Service logs: ARR timeout events

**Connection duration measurement:**

```python
import asyncio, websockets, time

async def measure_idle_disconnect():
    async with websockets.connect(WS_URL) as ws:
        start = time.time()
        try:
            await asyncio.wait_for(ws.recv(), timeout=600)
        except (websockets.ConnectionClosed, asyncio.TimeoutError) as e:
            print(f"Disconnected after {time.time()-start:.1f}s: {e}")
```

## 8. Procedure

### 8.1 Infrastructure Setup

```bash
az appservice plan create --name plan-ws --resource-group rg-websocket \
  --sku B1 --is-linux --location koreacentral
az webapp create --name app-websocket --resource-group rg-websocket \
  --plan plan-ws --runtime "PYTHON:3.11"

# Enable WebSocket support
az webapp config set --name app-websocket --resource-group rg-websocket \
  --web-sockets-enabled true
```

### 8.2 Scenarios

**S1 — Idle disconnection timing**: Open WebSocket connection, send no bytes. Record when connection closes.

**S2 — Ping prevention**: Open connection, send WebSocket Ping every 30s. Verify connection stays open beyond the idle timeout.

**S3 — Application-level heartbeat**: Send a small JSON `{"type": "ping"}` message every 60s. Verify connection stays open.

**S4 — Concurrent connection limit**: Open 100, 500, 1000 concurrent connections. Record when new connections start failing.

**S5 — ARR affinity with 2 instances**: Scale to 2 instances, disable ARR affinity. Open WebSocket. Check which instance handles the connection vs. which handles subsequent HTTP requests.

## 9. Expected signal

- **S1**: Connection closes at ~230–240s of idle (same as HTTP ARR timeout).
- **S2**: Ping frames extend connection lifetime beyond 240s.
- **S3**: Application-level messages also extend the idle timer.
- **S4**: Connection limit varies by SKU; B1 may support ~350 concurrent connections before degradation.
- **S5**: Without ARR affinity, WebSocket upgrade and HTTP request may go to different instances — WebSocket requires sticky session routing.

## 10. Results

!!! info "Results pending execution"
    No data collected yet.

## 11. Interpretation

*Awaiting results.*

## 12. Limits

- Windows App Service may have different WebSocket behavior than Linux.
- Custom container deployments may bypass the ARR WebSocket limit.

## 13. Confidence calibration

| Claim | Level |
|-------|-------|
| Idle timeout ~230s applies to WebSocket | **Strongly Suggested** (same ARR infrastructure) |
| Ping frames prevent idle disconnection | **Inferred** |
| ARR affinity required for multi-instance WebSocket | **Strongly Suggested** |

## 14. Related experiments

- [WebSocket Idle Disconnect](../zip-vs-container/overview.md) — in-depth WebSocket idle timeout
- [Slow Requests](../slow-requests/overview.md) — ARR timeout behavior for HTTP requests
- [ARR Affinity Behavior](../zip-vs-container/overview.md) — sticky session routing

## 15. References

- [WebSocket support in App Service](https://learn.microsoft.com/en-us/azure/app-service/faq-availability-performance-application-issues#how-do-i-use-websockets-in-app-service)
- [ARR Affinity documentation](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-connection-strings)

## 16. Support takeaway

For WebSocket disconnection issues:

1. First, verify WebSocket is enabled: `az webapp config show --query webSocketsEnabled`. It is disabled by default on many plans.
2. The ARR idle timeout (~230s) applies to WebSocket connections exactly as it does to HTTP. Recommend client-side WebSocket ping at 60–90s intervals.
3. For multi-instance plans, ARR affinity (sticky session) must be enabled for WebSocket. Without it, load-balanced connections may be routed to different instances, breaking the persistent connection.
4. Connection limits: direct customers to check `Connections` metric in Azure Monitor during peak load to identify if the limit is being reached.
