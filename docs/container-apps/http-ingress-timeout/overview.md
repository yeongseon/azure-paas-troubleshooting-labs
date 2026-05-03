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

# HTTP Ingress Timeout: Long-Running Request Termination

!!! info "Status: Planned"

## 1. Question

Container Apps ingress has a configurable idle timeout and an implicit request timeout. What is the maximum duration for a single HTTP request, and what HTTP status code does the client receive when the request exceeds the timeout — and does the container process receive a signal before the connection is dropped?

## 2. Why this matters

Applications that perform long-running synchronous operations (data export, batch processing, file conversion) may require HTTP requests that take minutes to complete. Container Apps ingress has an idle timeout that terminates connections that are idle (no data sent) for more than the configured period. If the application does not stream any response bytes during a long operation, the ingress drops the connection even though the application is actively processing the request. Understanding this behavior is essential for designing appropriate patterns (streaming, async with polling, or webhooks) for long operations.

## 3. Customer symptom

"Long-running API calls fail after exactly 240 seconds with a connection error" or "Export endpoint works for small datasets but times out for large ones" or "The request completes on the server but the client never receives the response."

## 4. Hypothesis

- H1: Container Apps ingress has an idle connection timeout (default: 240 seconds) that terminates connections where no data is sent by the server for that period. A long-running request that does not send response headers or body bytes until completion is terminated by the ingress after 240 seconds.
- H2: The container process is NOT notified before the connection is terminated — the application continues processing after the ingress has closed the connection. The completed result is silently discarded.
- H3: Streaming the response (sending HTTP headers immediately, then streaming body bytes periodically) keeps the connection alive past the 240-second idle timeout, allowing arbitrarily long responses.
- H4: The `ingress.timeout` property in the container app configuration controls the idle timeout (in seconds, maximum 3600).

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

**Experiment type**: Networking / Platform behavior

**Controlled:**

- Container app with a `/long-request?seconds=<n>` endpoint (sleeps for n seconds, then returns)
- Container app with a `/streaming?seconds=<n>` endpoint (sends a byte every 10 seconds)
- Ingress timeout configured at 240 seconds (default) and 3600 seconds

**Observed:**

- Client-side error code and timing for requests exceeding the timeout
- Application log entries after the connection is dropped (does the process continue?)
- Streaming behavior preventing timeout

**Scenarios:**

- S1: 300-second request, no streaming → timeout at 240s
- S2: 300-second request, streaming (1 byte/10s) → completes successfully
- S3: Configure `ingress.timeout=3600` → 300-second non-streaming request completes

## 7. Instrumentation

- `curl --max-time 400 -v https://<aca-url>/long-request?seconds=300` to observe timeout behavior
- Container application logs to verify process continues after connection drop
- Client-side error: socket reset, 504, or empty response

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Flask app with `/long-request?seconds=300` (sleeps 300s, then returns JSON) and `/streaming?seconds=300` (sends progress bytes every 10s using `yield`).
2. S1: Call `/long-request?seconds=300`; observe timeout at ~240 seconds; check server log for completion message after timeout.
3. S2: Call `/streaming?seconds=300`; verify client receives data stream for 300 seconds; verify completion.
4. S3: `az containerapp ingress update --timeout 3600`; call `/long-request?seconds=300`; verify it completes.

## 9. Expected signal

- S1: Client receives connection error or 504 at ~240 seconds; application log shows "request completed" at t=300s (proving process continued after connection drop).
- S2: Client receives streamed bytes for 300 seconds; final JSON response received at t=300s; no timeout.
- S3: Request completes at t=300s; client receives full response.

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

- Configure ingress timeout: `az containerapp ingress update --name <app> --resource-group <rg> --timeout <seconds>` (max 3600).
- Streaming in Flask: use `Response(generate(), content_type='text/event-stream')` where `generate()` is a generator that yields bytes.
- For operations > 1 hour, the recommended pattern is async: return a job ID immediately, process in the background, poll for status.

## 16. Related guide / official docs

- [Container Apps ingress configuration](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Set ingress timeout](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to)
