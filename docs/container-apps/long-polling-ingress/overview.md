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

# Long-Polling Connections Dropped by Ingress Idle Timeout

!!! info "Status: Planned"

## 1. Question

Long-polling is a pattern where the client holds an HTTP connection open, waiting for the server to push a response when new data is available. When the wait period exceeds the Container Apps ingress idle timeout, the connection is dropped. What status code or error does the client receive, and how does the application need to be designed to handle this gracefully?

## 2. Why this matters

Long-polling is used by real-time applications (notifications, dashboard updates, chat) as a fallback when WebSockets are not available. Unlike streaming responses (which send bytes periodically), a pure long-poll holds the connection silently until the server has data. The idle timeout at the ingress layer is indistinguishable from the server finally having data — both result in the connection ending. If the client doesn't implement proper reconnect logic, it silently loses the connection and stops receiving updates.

## 3. Customer symptom

"Notifications stop arriving after a few minutes" or "Our polling endpoint works locally but stops delivering updates on Azure" or "Clients need to refresh the page to see new updates — the long-poll keeps timing out."

## 4. Hypothesis

- H1: Container Apps ingress terminates long-polling connections that have been idle (no response bytes sent) for longer than the configured idle timeout (default 240 seconds). The client receives a connection close event (TCP FIN or RST).
- H2: A well-designed long-poll server sends an empty response (HTTP 204 or a "no-data" response body) before the idle timeout, allowing the client to immediately reconnect and poll again. The timeout becomes the max wait interval, not a failure condition.
- H3: Server-Sent Events (SSE) is a better pattern than long-polling for Container Apps because SSE is a persistent HTTP stream — as long as the server sends a keep-alive `:` comment periodically, the connection remains open past the idle timeout.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption |
| Region | Korea Central |
| Runtime | Python 3.11 (Flask) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Networking / Application pattern

**Controlled:**

- Long-poll endpoint that waits up to 300 seconds for data
- SSE endpoint that sends keep-alive comments every 30 seconds
- Ingress idle timeout at default (240 seconds)

**Observed:**

- Client behavior when long-poll connection is dropped by ingress
- Data receipt when long-poll is within timeout vs. beyond timeout
- SSE keep-alive effectiveness

**Scenarios:**

- S1: Long-poll with 300s wait, default timeout → dropped at 240s
- S2: Long-poll with 200s wait, default timeout → completes successfully (within timeout)
- S3: Long-poll server sends empty response at 200s, client reconnects immediately → graceful handling
- S4: SSE with 30s keep-alive comment → connection survives indefinitely

## 7. Instrumentation

- Client-side timer and error event handler
- `curl -v --max-time 400 https://<aca>/long-poll?wait=300` to capture connection close behavior
- Server-side log to verify if client received the intended response

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Flask app with three endpoints: `/long-poll?wait=N` (waits N seconds, returns data), `/long-poll-graceful?wait=N` (returns empty at min(N, 200) seconds), `/sse` (SSE with keep-alive comments).
2. S1: `curl --max-time 400 /long-poll?wait=300`; observe connection drop at ~240s.
3. S2: `curl --max-time 300 /long-poll?wait=200`; observe successful response at 200s.
4. S3: `curl /long-poll-graceful?wait=300`; observe two responses: empty at 200s, then client immediately reconnects.
5. S4: `curl -N /sse`; hold for 10+ minutes; verify keep-alive comments prevent idle timeout.

## 9. Expected signal

- S1: Connection terminated at ~240s; `curl` reports "Empty reply from server" or connection reset.
- S2: Response received at ~200s; full JSON body delivered.
- S3: First response (empty) at 200s; client reconnects; eventual data response arrives.
- S4: SSE stream remains open; keep-alive comments arrive every 30s; no idle timeout.

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

- SSE keep-alive: send `: keep-alive\n\n` (a comment line) from the server every 30-60 seconds to reset the idle timeout.
- Long-polling client design: always implement reconnect logic; treat connection close as "server has no data yet, reconnect."
- WebSockets with application-level ping/pong are the most robust real-time connection pattern for Container Apps.

## 16. Related guide / official docs

- [Container Apps ingress timeout](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
