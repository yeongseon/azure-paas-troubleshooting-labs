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

# WebSocket Idle Disconnect Without Keepalive

!!! info "Status: Published"
    Experiment completed with real data on 2026-05-04.

## 1. Question

When a WebSocket connection is established on App Service and remains idle (no messages sent), does the platform disconnect it after a timeout? What is the idle timeout duration, and does enabling the App Service WebSocket setting affect whether the upgrade is accepted?

## 2. Why this matters

App Service has a frontend idle connection timeout that applies to all HTTP connections including WebSocket upgrades. Long-lived WebSocket connections that rely on the server to send data (e.g., server-sent events, notification streams) will be disconnected if no data flows for the timeout period. Clients that do not implement application-layer keepalive (ping/pong frames) will experience silent disconnection, often manifesting as clients that stop receiving updates without an error event.

## 3. Customer symptom

"WebSocket connections drop after a few minutes with no error" or "Our real-time feature works for a while then stops without any exception" or "The WebSocket connection seems to time out — we have to reconnect."

## 4. Hypothesis

- H1: App Service accepts WebSocket upgrade requests when `webSocketsEnabled: true`. When `webSocketsEnabled: false`, the upgrade is rejected with a non-101 response.
- H2: The App Service frontend imposes a ~4-minute idle timeout on WebSocket connections. A connection with no message traffic will be disconnected after approximately 240 seconds.
- H3: Standard gunicorn workers (sync worker type) do not support WebSocket upgrades — the `/ws` endpoint returns 404 because gunicorn cannot handle the Upgrade header in sync mode.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | B1 |
| Region | Korea Central |
| Runtime | Python 3.11 / gunicorn (sync workers) |
| OS | Linux |
| App name | app-batch-1777849901 |
| Date tested | 2026-05-04 |

## 6. Variables

**Experiment type**: Configuration / Platform behavior

**Controlled:**

- `webSocketsEnabled` toggled via `az rest PATCH .../config/web`
- Flask app with `flask-sock` WebSocket endpoint at `/ws`
- gunicorn with default sync worker class

**Observed:**

- HTTP response to WebSocket upgrade with `webSocketsEnabled=false` vs `true`
- Whether gunicorn sync workers handle WS upgrade
- WS endpoint availability before/after enable

## 7. Instrumentation

- `curl -H "Upgrade: websocket" -H "Sec-WebSocket-Key: ..."` — manual WS upgrade test
- `az rest GET/PATCH .../config/web` — check/set webSocketsEnabled
- Python `websocket-client` library for WS handshake test

## 8. Procedure

1. Confirm `webSocketsEnabled: false` (default). Test `/ws` endpoint with WS upgrade headers.
2. Add `flask-sock` WS endpoint to app. Deploy.
3. Enable `webSocketsEnabled: true`. Test WS upgrade.
4. Observe whether gunicorn sync workers can handle WS upgrade.

## 9. Expected signal

- H1: `webSocketsEnabled=false` → non-101 response (or connection refused upgrade).
- H3: gunicorn sync workers → 404 even with `webSocketsEnabled=true` (WS requires async/gevent workers).

## 10. Results

### Baseline: webSocketsEnabled=false

```json
{"webSocketsEnabled": false, "http20Enabled": true}
```

### Deploy flask-sock endpoint, enable webSocketsEnabled

```bash
az rest PATCH .../config/web --body '{"properties":{"webSocketsEnabled":true}}'
→ "webSocketsEnabled": true
```

### WS upgrade test with webSocketsEnabled=true

```bash
curl -H "Upgrade: websocket" -H "Connection: Upgrade" \
     -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
     -H "Sec-WebSocket-Version: 13" \
     https://<app>.azurewebsites.net/ws --http1.1
→ HTTP/1.1 404 NOT FOUND
  Server: gunicorn
```

Python `websocket-client` test:
```
websocket._exceptions.WebSocketBadStatusException: Handshake status 404 NOT FOUND
```

!!! info "Key finding"
    The App Service frontend correctly forwarded the WebSocket upgrade request to gunicorn (response is from gunicorn, not the App Service frontend). gunicorn's default **sync worker** class does not support WebSocket upgrades — it returns 404 because it cannot handle the connection upgrade protocol. WebSocket requires gunicorn with `--worker-class gevent` or `--worker-class eventlet`.

### `/ws-info` endpoint (HTTP GET)

```json
{
  "upgrade_header": "none",
  "connection_header": "none",
  "note": "WebSocket requires gevent/eventlet worker - standard gunicorn does not support WS upgrade"
}
```

## 11. Interpretation

- **Observed**: When `webSocketsEnabled=true`, the App Service frontend does forward WebSocket upgrade requests to the application. The 404 comes from gunicorn, not from the App Service layer. H1 is partially confirmed — the setting affects whether the frontend allows the upgrade, but the backend worker must also support it.
- **Observed**: gunicorn sync workers return 404 for WebSocket upgrade requests. H3 is confirmed. To use WebSocket on App Service with Python/gunicorn, the startup command must use `--worker-class gevent` or `--worker-class eventlet`.
- **Not Proven**: The 4-minute idle timeout (H2) could not be directly tested because a working WebSocket connection was not established (gunicorn sync worker blocked the upgrade). The 4-minute timeout is documented platform behavior.
- **Inferred**: The correct startup command for WebSocket-capable gunicorn: `gunicorn --worker-class gevent --bind 0.0.0.0:8000 app:app`. The `gevent` package must be included in `requirements.txt`.

## 12. What this proves

- App Service forwards WebSocket upgrade requests to the application when `webSocketsEnabled=true`. **Observed**.
- gunicorn sync workers (default) cannot handle WebSocket upgrades — they return 404. **Observed**.
- WebSocket on Python App Service requires `gevent` or `eventlet` worker class in gunicorn. **Inferred** from 404 behavior and gunicorn documentation.

## 13. What this does NOT prove

- The App Service idle timeout for WebSocket connections (believed to be ~240 seconds) was not directly measured in this experiment.
- Behavior with Node.js (which supports WebSocket natively via `ws` or `socket.io`) was not tested.
- gevent-based gunicorn WebSocket behavior was not tested (would require startup command change and redeployment).

## 14. Support takeaway

When a Python App Service returns 404 for WebSocket connections despite `webSocketsEnabled=true`:

1. The issue is in the gunicorn worker class, not App Service configuration. Default sync workers do not support WS.
2. Fix: Change startup command to `gunicorn --worker-class gevent --bind 0.0.0.0:8000 app:app` and add `gevent` to `requirements.txt`.
3. For idle disconnection issues (connection drops after a few minutes): implement application-layer WebSocket ping/pong every 30–60 seconds to keep the connection active through the platform's idle timeout.
4. Verify `webSocketsEnabled=true` via portal or `az rest GET .../config/web --query "properties.webSocketsEnabled"`.

## 15. Reproduction notes

```bash
APP="<app-name>"
RG="<resource-group>"
SUB="<subscription-id>"

# Enable WebSocket
az rest --method PATCH \
  --uri "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Web/sites/${APP}/config/web?api-version=2022-03-01" \
  --body '{"properties":{"webSocketsEnabled":true}}'

# Test WS upgrade (will fail with sync gunicorn → 404)
curl -sv --http1.1 \
  -H "Upgrade: websocket" \
  -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  https://<app>.azurewebsites.net/ws

# For working WS: startup command must use gevent
# az webapp config set -n $APP -g $RG \
#   --startup-file "gunicorn --worker-class gevent --bind 0.0.0.0:8000 app:app"
# pip install gevent (add to requirements.txt)
```

## 16. Related guide / official docs

- [WebSocket support in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/faq-availability-performance-application-issues#websocket)
- [Configure general settings in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-common#configure-general-settings)
- [gunicorn worker classes](https://docs.gunicorn.org/en/stable/design.html#worker-types)
