---
hide:
  - toc
validation:
  az_cli:
    last_tested: 2026-04-10
    cli_version: "2.73.0"
    core_tools_version: null
    result: pass
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Health Check Eviction on Partial Dependency Failure

!!! info "Status: Published"
    Experiment completed with real data collected on 2026-04-10 from Azure App Service P1v3 (koreacentral).
    Four test scenarios executed across 2 instances over ~40 minutes. All hypotheses partially confirmed — with a critical nuance discovered.

## 1. Question

When an App Service health check endpoint returns unhealthy because a single downstream dependency (e.g., database) is unreachable, does the platform evict the instance even though the application itself is running and could serve requests that don't require that dependency?

## 2. Why this matters

Customers implement health check endpoints that validate all dependencies. When one dependency fails, the health check returns unhealthy, and the platform removes the instance from the load balancer rotation. This can cascade — if the unhealthy dependency affects all instances equally, every instance gets evicted, causing a full outage for a partial dependency failure.

### Background: How Health Check Eviction Works

Azure App Service Health Check probes each instance every **1 minute** at a configured path. When an instance returns a non-200 status code for a threshold of consecutive checks, the platform marks the instance as **unhealthy** and removes it from load balancer rotation.

```text
┌─────────────────────────────────────────────────────┐
│  App Service Load Balancer                          │
│  ┌───────────────┐    ┌───────────────┐             │
│  │  Instance A    │    │  Instance B    │            │
│  │  /healthz→503  │    │  /healthz→200  │            │
│  │  (UNHEALTHY)   │    │  (HEALTHY)     │            │
│  └───────┬───────┘    └───────┬───────┘             │
│          │                    │                      │
│   ✗ Evicted after      ✓ Receives 100%              │
│     ~10 minutes          of traffic                  │
└─────────────────────────────────────────────────────┘
```

**Critical design constraint**: If ALL instances are unhealthy, the platform does NOT evict any instance. This prevents cascading eviction from turning a partial failure into a total outage.

## 3. Customer symptom

- "Our app went completely down, but only the database was unreachable for 2 minutes."
- "Health check keeps failing and instances keep getting removed and re-added."
- "We see instance cycling in the health check blade even though the app is fine."
- "After we fixed the dependency, it still took 10 minutes for the instance to come back."

## 4. Hypothesis

1. **H1 — Partial eviction**: When a single instance fails health checks while others are healthy, the platform evicts only the unhealthy instance after ~10 consecutive failures (~10 minutes).
2. **H2 — Total failure protection**: When ALL instances fail health checks simultaneously, the platform does NOT evict any instance — all instances continue receiving traffic.
3. **H3 — Cascading amplification**: If one instance is evicted and the last remaining instance also becomes unhealthy, the platform keeps the last instance in rotation (never reduces to zero).
4. **H4 — Recovery**: After restart, evicted instances re-enter rotation within 1-2 minutes.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 (2 instances) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Deployment method | ZIP Deploy |
| ARR Affinity | Disabled |
| Health Check Path | `/healthz` |
| Health Check Interval | 1 minute (platform default) |
| Date tested | 2026-04-10 |

Instances:

| Instance | Short ID | Hostname | Availability Zone |
|----------|----------|----------|-------------------|
| A | `4b6100b2a00e` | `c7cfde03186d` | koreacentral-az3 |
| B | `ed56515e4ed9` | `defc2b4c67d1` | koreacentral-az2 |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Health check path (`/healthz`) and response logic (200 if dependency healthy, 503 if not)
- Dependency failure simulation (in-memory per-instance flag)
- Instance count (2, fixed P1v3 plan)
- Which instance(s) have failed dependency

**Observed:**

- Traffic distribution across instances (30 requests per measurement window)
- Instance state via `az webapp list-instances` (READY, STOPPED, UNKNOWN)
- Time from first health check failure to eviction
- Behavior when all instances are unhealthy
- Behavior when last healthy instance fails (cascading scenario)
- Recovery time after `az webapp restart`

## 7. Instrumentation

- **Test application**: Custom Flask app with simulated dependency and health check logging
- **Traffic measurement**: 30 sequential HTTP requests to `/status` per check, counting instance distribution
- **Instance state**: `az webapp list-instances --query "[].{name:name, state:state}"` — reports READY, STOPPED, or UNKNOWN
- **Monitoring interval**: Every 2 minutes for up to 16 minutes per test
- **Failure control**: POST to `/fail-dependency` targets a specific instance; if wrong instance is hit, immediately POST `/recover-dependency` and retry

## 8. Procedure

### 8.1 Application Code

#### app.py

```python
"""
Health Check Eviction Test App for Azure App Service.

This app simulates a health check endpoint that depends on an external dependency.
The dependency can be toggled to simulate failure, triggering health check eviction.
"""

import os
import socket
import time
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)

# Simulated dependency state - shared across requests on this instance
dependency_state = {
    "healthy": True,
    "failed_since": None,
    "failure_count": 0,
    "recovery_time": None,
}

# Health check call log - track each health check probe
health_check_log = []
MAX_LOG_SIZE = 500

# Request log - track all requests
request_log = []
MAX_REQUEST_LOG = 500

# Lock for thread safety
state_lock = threading.Lock()


def _get_instance_id():
    return os.environ.get(
        "WEBSITE_INSTANCE_ID",
        os.environ.get("COMPUTERNAME", socket.gethostname()),
    )


def _log_health_check(status_code, reason):
    with state_lock:
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "instance_id": _get_instance_id()[:16],
            "hostname": socket.gethostname(),
            "status_code": status_code,
            "reason": reason,
            "dependency_healthy": dependency_state["healthy"],
        }
        health_check_log.append(entry)
        if len(health_check_log) > MAX_LOG_SIZE:
            health_check_log.pop(0)


def _log_request(endpoint, status_code):
    with state_lock:
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "instance_id": _get_instance_id()[:16],
            "hostname": socket.gethostname(),
            "endpoint": endpoint,
            "status_code": status_code,
            "pid": os.getpid(),
        }
        request_log.append(entry)
        if len(request_log) > MAX_REQUEST_LOG:
            request_log.pop(0)


@app.route("/")
def index():
    """Root endpoint - always responds (not tied to dependency)."""
    _log_request("/", 200)
    return jsonify({
        "status": "ok",
        "instance_id": _get_instance_id(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dependency_healthy": dependency_state["healthy"],
    })


@app.route("/healthz")
def health_check():
    """Health check endpoint that depends on simulated external service.

    Returns 200 if dependency is healthy, 503 if dependency is down.
    This is the endpoint configured in App Service Health Check.
    """
    if dependency_state["healthy"]:
        _log_health_check(200, "dependency_healthy")
        return jsonify({
            "status": "healthy",
            "instance_id": _get_instance_id()[:16],
            "hostname": socket.gethostname(),
            "dependency": "connected",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }), 200
    else:
        _log_health_check(503, "dependency_unavailable")
        return jsonify({
            "status": "unhealthy",
            "instance_id": _get_instance_id()[:16],
            "hostname": socket.gethostname(),
            "dependency": "unreachable",
            "failed_since": dependency_state["failed_since"],
            "failure_count": dependency_state["failure_count"],
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }), 503


@app.route("/api/data")
def api_data():
    """Normal API endpoint that doesn't need the dependency."""
    _log_request("/api/data", 200)
    return jsonify({
        "data": "This endpoint works regardless of dependency status",
        "instance_id": _get_instance_id()[:16],
        "hostname": socket.gethostname(),
        "dependency_healthy": dependency_state["healthy"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/fail-dependency", methods=["POST"])
def fail_dependency():
    """Simulate dependency failure."""
    with state_lock:
        dependency_state["healthy"] = False
        dependency_state["failed_since"] = datetime.now(timezone.utc).isoformat()
        dependency_state["failure_count"] = 0
    return jsonify({
        "action": "dependency_failed",
        "instance_id": _get_instance_id()[:16],
        "hostname": socket.gethostname(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/recover-dependency", methods=["POST"])
def recover_dependency():
    """Simulate dependency recovery."""
    with state_lock:
        dependency_state["healthy"] = True
        dependency_state["recovery_time"] = datetime.now(timezone.utc).isoformat()
    return jsonify({
        "action": "dependency_recovered",
        "instance_id": _get_instance_id()[:16],
        "hostname": socket.gethostname(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/status")
def status():
    """Get current instance status and health check log."""
    return jsonify({
        "instance_id": _get_instance_id(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "dependency_state": dependency_state,
        "health_check_log_count": len(health_check_log),
        "health_check_log_last_10": health_check_log[-10:],
        "request_log_count": len(request_log),
        "request_log_last_10": request_log[-10:],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/logs/healthcheck")
def healthcheck_logs():
    """Get full health check log."""
    return jsonify({
        "instance_id": _get_instance_id()[:16],
        "hostname": socket.gethostname(),
        "total_entries": len(health_check_log),
        "entries": health_check_log,
    })


@app.route("/logs/requests")
def request_logs():
    """Get full request log."""
    return jsonify({
        "instance_id": _get_instance_id()[:16],
        "hostname": socket.gethostname(),
        "total_entries": len(request_log),
        "entries": request_log,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```

#### requirements.txt

```text
flask==3.1.1
gunicorn==23.0.0
```

#### Design Notes

- **In-memory dependency simulation**: Uses a thread-safe dictionary (`dependency_state`) with `threading.Lock` to simulate an external dependency that can be toggled healthy/unhealthy per-instance. This avoids needing a real database while allowing per-instance control.
- **Per-instance state isolation**: Each App Service instance runs its own container with its own process - `dependency_state` is process-local. This means POST `/fail-dependency` on Instance A does not affect Instance B, which is exactly what we need to test partial failure scenarios.
- **Health check logging**: Every `/healthz` probe is logged with timestamp, instance ID, hostname, and result. This creates an audit trail to correlate with platform health check decisions (eviction timing).
- **Truncated instance ID**: `_get_instance_id()[:16]` is used because Azure's `WEBSITE_INSTANCE_ID` is a 64-character hex string; the first 16 chars are sufficient for visual differentiation in logs.
- **Request logging**: All endpoints log requests to an in-memory list (capped at 500 entries) for post-test forensic analysis without needing Application Insights.
- **gunicorn single-worker**: The startup command uses `gunicorn --bind=0.0.0.0 --timeout 600 app:app` with the default 1 worker because thread safety of the shared `dependency_state` dict is simpler with a single process.

#### Endpoint Map

| Endpoint | Method | Purpose | Hypothesis Link | Response |
|----------|--------|---------|-----------------|----------|
| `/` | GET | Root - always returns 200 regardless of dependency state | Baseline - confirms app is running | `{"status": "ok", "instance_id": "...", "dependency_healthy": true/false}` |
| `/healthz` | GET | Health check endpoint configured in App Service | Tests H1-H3 - platform probes this every 1 minute; returns 503 when dependency is failed | `200 + {"status": "healthy"}` or `503 + {"status": "unhealthy"}` |
| `/api/data` | GET | Normal API endpoint that works without dependency | Shows that the app can serve requests even when health check fails - illustrates the cascading eviction problem | `{"data": "This endpoint works regardless..."}` |
| `/fail-dependency` | POST | Toggles dependency to unhealthy state | Triggers health check failure on the targeted instance | `{"action": "dependency_failed", "instance_id": "..."}` |
| `/recover-dependency` | POST | Restores dependency to healthy state | Ends the failure simulation for recovery testing (H4) | `{"action": "dependency_recovered", "instance_id": "..."}` |
| `/status` | GET | Returns full instance state including health check log | Forensic analysis - shows dependency state, last 10 health checks and requests | Full JSON with `dependency_state`, logs |
| `/logs/healthcheck` | GET | Returns complete health check probe log | Correlates platform probe timing with eviction decisions | `{"entries": [...]}` |
| `/logs/requests` | GET | Returns complete request log | Tracks traffic distribution across instances | `{"entries": [...]}` |

### 8.2 Deploy test infrastructure

```bash
# Create resource group and P1v3 plan (2 instances for eviction testing)
az group create --name rg-healthcheck-lab --location koreacentral
az appservice plan create --name plan-healthcheck \
    --resource-group rg-healthcheck-lab --sku P1v3 --is-linux \
    --number-of-workers 2

# Create Python 3.11 web app with health check
az webapp create --name app-healthcheck-lab \
    --resource-group rg-healthcheck-lab \
    --plan plan-healthcheck --runtime "PYTHON:3.11"

# Configure health check and disable ARR affinity
az webapp config set --name app-healthcheck-lab \
    --resource-group rg-healthcheck-lab \
    --generic-configurations '{"healthCheckPath": "/healthz"}'
az webapp update --name app-healthcheck-lab \
    --resource-group rg-healthcheck-lab \
    --client-affinity-enabled false

# Set startup command and deploy
az webapp config set --name app-healthcheck-lab \
    --resource-group rg-healthcheck-lab \
    --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"
az webapp deploy --name app-healthcheck-lab \
    --resource-group rg-healthcheck-lab \
    --src-path healthcheck-app.zip --type zip
```

### 8.3 Verify baseline — both instances healthy

1. Send 20 requests to `/status`, verify both instances appear with `healthy=True`
2. Run `az webapp list-instances` — both should show `READY`

### 8.4 Test 1 — All instances unhealthy simultaneously

1. POST `/fail-dependency` repeatedly until both instances report unhealthy
2. Monitor traffic distribution every 2 minutes for 12+ minutes
3. Verify no eviction occurs (both instances continue receiving traffic)
4. POST `/recover-dependency` to restore both instances

### 8.5 Test 2 — Partial failure (one instance unhealthy)

1. POST `/fail-dependency` selectively to Instance A only
2. Verify Instance A returns 503 on `/healthz`, Instance B returns 200
3. Monitor traffic distribution every 2 minutes
4. Observe eviction event (Instance A stops receiving traffic)
5. Verify via `az webapp list-instances` — Instance A state changes

### 8.6 Test 3 — Cascading failure

1. Start from partial failure state (Instance A evicted)
2. POST `/fail-dependency` to Instance B (the only remaining instance)
3. Monitor whether Instance B gets evicted or stays in rotation
4. Check instance states via `az webapp list-instances`

### 8.7 Recovery test

1. Execute `az webapp restart` from cascading failure state
2. Measure time until both instances appear in traffic distribution
3. Verify via `az webapp list-instances` — both return to READY

### 8.8 Clean up

```bash
az group delete --name rg-healthcheck-lab --yes --no-wait
```

## 9. Expected signal

- Health check returns 503 after `/fail-dependency` on target instance
- Instance removed from rotation after ~10 consecutive failures (~10 minutes)
- When ALL instances fail simultaneously, no eviction occurs
- When the last healthy instance fails, it remains in rotation
- After `az webapp restart`, recovery within 1-2 minutes

## 10. Results

### 10.1 Test 1: All Instances Unhealthy Simultaneously

Both instances' `/healthz` endpoints returned 503 continuously for **12+ minutes**.

| Time | Instance A | Instance B | Traffic Split | Eviction |
|------|-----------|-----------|---------------|----------|
| T+0min | 503 | 503 | ~50/50 | No |
| T+2min | 503 | 503 | ~50/50 | No |
| T+4min | 503 | 503 | ~50/50 | No |
| T+6min | 503 | 503 | ~50/50 | No |
| T+8min | 503 | 503 | ~50/50 | No |
| T+10min | 503 | 503 | ~50/50 | No |
| T+12min | 503 | 503 | ~50/50 | **No** |

!!! tip "How to read this"
    After 12 minutes of continuous health check failures on BOTH instances, neither was evicted. The platform continued routing traffic to both instances equally. This confirms the protection mechanism: when all instances are unhealthy, App Service preserves the existing state to prevent total outage.

### 10.2 Test 2: Partial Failure (One Instance Unhealthy)

Instance A `/healthz` → 503. Instance B `/healthz` → 200.

| Time | Instance A Traffic | Instance B Traffic | Instance A State |
|------|-------------------|-------------------|-----------------|
| T+0min | 50% (15/30) | 50% (15/30) | READY |
| T+2min | 40% (12/30) | 60% (18/30) | UNHEALTHY |
| T+4min | 43% (13/30) | 57% (17/30) | UNHEALTHY |
| T+6min | 60% (18/30) | 40% (12/30) | UNHEALTHY |
| T+8min | 47% (14/30) | 53% (16/30) | UNHEALTHY |
| **T+10min** | **0% (0/30)** | **100% (30/30)** | **UNKNOWN** |

```text
Traffic to Instance A (UNHEALTHY):
T+0min  ████████████████████████████████████████████████  50%
T+2min  ████████████████████████████████                  40%
T+4min  ██████████████████████████████████                43%
T+6min  ████████████████████████████████████████████████  60%
T+8min  █████████████████████████████████████             47%
T+10min                                                    0%  ← EVICTED
```

!!! tip "How to read this"
    For the first 8 minutes, traffic was distributed roughly equally to both instances — the platform did NOT gradually reduce traffic to the unhealthy instance. Then at ~10 minutes, eviction was **instant and complete**: Instance A went from receiving ~47% of traffic to exactly 0%. This is a binary on/off switch, not a gradual drain.

**Post-eviction verification** (50 additional requests): 50/50 (100%) went to Instance B.

**Instance state via Azure API:**

| Instance | State |
|----------|-------|
| A (`4b6100b2a00e`) | **UNKNOWN** |
| B (`ed56515e4ed9`) | **READY** |

**ARRAffinity bypass attempt**: Attempted to route to Instance A using `ARRAffinity` cookie with Instance A's full ID — **failed**. Traffic was routed to Instance B regardless. Evicted instances are completely removed from the load balancer; no client-side routing can reach them.

### 10.3 Test 3: Cascading Failure

Starting state: Instance A already evicted (UNKNOWN), Instance B serving 100% of traffic.

**Step 1: Fail Instance B's dependency** (POST `/fail-dependency`).

| Time After B Failure | Instance B Traffic | Instance B State | Notes |
|---------------------|-------------------|-----------------|-------|
| T+0min | 100% (30/30) | READY → UNHEALTHY | B is last instance |
| T+2min | 100% (30/30) | UNHEALTHY | Still serving |
| T+4min | 100% (30/30) | UNHEALTHY | Still serving |
| T+6min | 100% (30/30) | **STOPPED** | Still serving despite STOPPED state |

!!! tip "How to read this"
    Instance B's health check was returning 503 for 6+ minutes, yet it continued receiving 100% of traffic. The instance state transitioned from READY → STOPPED, but the platform kept routing to it because it was the **last instance** in rotation. App Service will never reduce to zero instances — even if the only remaining instance is unhealthy.

**Instance states during cascading failure:**

| Instance | State | In Rotation | Notes |
|----------|-------|-------------|-------|
| A (`4b6100b2a00e`) | UNKNOWN | No | Evicted in Test 2 |
| B (`ed56515e4ed9`) | STOPPED | **Yes** | Last instance protection |

### 10.4 Recovery After Restart

`az webapp restart` issued at `2026-04-10T10:06:24Z` with both instances in degraded state.

| Time After Restart | Instance A Traffic | Instance B Traffic | A State | B State |
|-------------------|-------------------|-------------------|---------|---------|
| T+0s | — | — | UNKNOWN | STOPPED |
| T+15s | 60% | 40% | STOPPED | STOPPED |
| T+90s | 53% | 47% | STOPPED | READY |
| T+150s | 50% | 50% | **READY** | **READY** |

!!! tip "How to read this"
    Recovery was nearly instant — within 15 seconds of `az webapp restart`, both instances were serving traffic again. The instance state API lagged behind: Instance A transitioned through `UNKNOWN → STOPPED → READY` over ~150 seconds, even though it was already receiving and responding to requests.

### 10.5 Summary: Eviction Behavior Matrix

| Scenario | Eviction Occurs? | Time to Evict | Traffic During Eviction | Instance State |
|----------|-----------------|---------------|------------------------|----------------|
| All instances unhealthy | **No** | N/A | 50/50 (unchanged) | Both remain in rotation |
| One instance unhealthy | **Yes** | ~10 minutes | Instant 0% → 100% shift | UNKNOWN |
| Last instance becomes unhealthy | **No** | N/A | 100% to last instance | STOPPED (but still serving) |
| Recovery via `az webapp restart` | N/A | ~15 seconds | Both serve immediately | READY after ~150s |

## 11. Interpretation

**H1 — Partial eviction: CONFIRMED.** When Instance A failed health checks while Instance B remained healthy, Instance A was removed from load balancer rotation after exactly 10 minutes (~10 consecutive failed health probes at 1-minute intervals). The eviction was binary — traffic shifted from ~50% to 0% instantly, with no gradual drain period.

**H2 — Total failure protection: CONFIRMED.** When both instances failed health checks simultaneously, neither was evicted even after 12+ minutes of continuous failures. The platform maintained the existing traffic distribution.

**H3 — Cascading amplification: CONFIRMED with nuance.** When the last healthy instance also became unhealthy, it was NOT evicted — it remained in rotation with 100% of traffic. The platform's protection mechanism prevents reducing to zero healthy instances. However, the instance state changed to STOPPED, which could mislead monitoring dashboards.

**H4 — Recovery: CONFIRMED.** `az webapp restart` restored both instances to active rotation within 15 seconds, though the Azure API's instance state lagged behind by ~150 seconds.

### Key Discovery: Binary Eviction, Not Gradual Drain

The most significant finding is that health check eviction is an **all-or-nothing switch**:

- Before eviction: the unhealthy instance receives a normal share of traffic (~50%)
- After eviction: the unhealthy instance receives exactly 0% of traffic
- There is no "draining" period where traffic is gradually shifted

This means that for the first ~10 minutes after a health check starts failing, users hitting the unhealthy instance will experience degraded service. The platform does not reduce traffic to unhealthy instances — it either routes normally or stops routing entirely.

### Key Discovery: State API Lag

The `az webapp list-instances` state does not reflect real-time routing decisions:

| Actual Behavior | Reported State |
|----------------|----------------|
| Instance evicted from LB | UNKNOWN |
| Instance receiving traffic but unhealthy | STOPPED |
| Instance just restored, serving traffic | STOPPED (for ~90-150s) |
| Instance fully operational | READY |

Monitoring systems that rely on instance state will report misleading status during transitions.

## 12. What this proves

!!! success "Evidence level: Direct observation"

1. Health check eviction occurs after **~10 consecutive failed probes** (~10 minutes at 1-minute intervals)
2. Eviction is **binary**: traffic shifts from ~50% to 0% instantly — no gradual drain
3. When **all instances are unhealthy**, the platform does NOT evict any instance — protects against total outage
4. When the **last remaining instance** becomes unhealthy, it stays in rotation (never reduces to zero)
5. **ARRAffinity cookies cannot route to evicted instances** — they are fully removed from the load balancer
6. `az webapp restart` recovers evicted instances to active routing within **~15 seconds**
7. Instance state API (`az webapp list-instances`) **lags behind** actual routing decisions by 90-150 seconds

## 13. What this does NOT prove

- **Custom health check threshold**: We tested only the default threshold. The `WEBSITE_HEALTHCHECK_MAXUNHEALTHYCOUNT` setting may alter the eviction timing.
- **Health check with custom interval**: We used the default 1-minute interval. Custom intervals may affect the eviction timeline proportionally.
- **Instance replacement**: We did not verify whether App Service replaces evicted instances with new ones, or simply removes them from rotation. P1v3 does not auto-scale — this may behave differently on Consumption or Elastic Premium plans.
- **Long-term eviction behavior**: We observed eviction for ~10 minutes. It's unclear whether the platform eventually terminates (kills) a long-evicted instance or just keeps it running indefinitely.
- **Health check with authentication**: If the health check path requires authentication, the behavior may differ.
- **Scale-in during eviction**: We did not test whether the platform counts evicted instances toward the instance count or treats them as "missing."

## 14. Support takeaway

!!! abstract "For support engineers"

    **When a customer reports "app went down but only one dependency failed":**

    1. Check if health check validates ALL dependencies — this is the most common cause of cascading eviction
    2. Ask how many instances were running — partial eviction only happens when at least one instance is healthy
    3. Check timing — health check eviction takes ~10 minutes, so a 2-minute database blip should NOT cause eviction

    **Key guidance:**

    - Health check endpoints should validate **only critical dependencies** that are required for ALL request paths
    - If a dependency affects only some API endpoints, consider a **shallow health check** that returns 200 if the app process is alive, regardless of downstream health
    - Design health checks with **circuit breaker awareness**: if a dependency is known to be down but expected to recover, the health check should not immediately return unhealthy
    - After fixing the root cause, `az webapp restart` is the fastest way to restore evicted instances (~15 seconds vs waiting for health check to pass ~10 consecutive times)
    - Do NOT rely on `az webapp list-instances` state for real-time routing status — it lags by 90-150 seconds

    **Anti-pattern: "kitchen sink" health check**

    ```python
    # ❌ BAD: Validates everything — any single failure triggers eviction
    @app.route("/healthz")
    def health():
        check_database()      # ← DB blip evicts the instance
        check_redis()         # ← Redis maintenance evicts the instance
        check_storage()       # ← Storage throttling evicts the instance
        return "OK", 200

    # ✅ GOOD: Validates only that the app can serve requests
    @app.route("/healthz")
    def health():
        return "OK", 200

    # ✅ BETTER: Separate liveness from readiness
    @app.route("/healthz")
    def health():
        check_app_process_alive()  # Lightweight check
        return "OK", 200

    @app.route("/ready")         # NOT configured as health check path
    def ready():
        check_database()
        check_redis()
        return "OK", 200
    ```

## 15. Reproduction notes

- Health check interval is 1 minute by default; eviction happens after ~10 consecutive failures
- The `/healthz` path must return HTTP 200 to be considered healthy; any other status code (including 3xx redirects) counts as failure
- Test with 2+ instances to observe differential eviction behavior
- ARR Affinity should be disabled to observe load balancer distribution clearly
- P1v3 plan was used for this experiment; Consumption and Premium plans may have different eviction thresholds
- The in-memory dependency simulation means each instance has independent failure state — this accurately models scenarios where a downstream dependency is unavailable from some instances but not others (e.g., regional DNS issues, network partitions)
- `az webapp restart` performs a soft restart (process restart, not container recreation) — this is sufficient to re-register the instance with the health check system
- The test application source code is available in the `data/app-service/health-check-eviction/` directory

## 16. Related guide / official docs

- [Health check - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check)
- [Configure health check - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check?tabs=dotnet)
- [App Service diagnostics overview](https://learn.microsoft.com/en-us/azure/app-service/overview-diagnostics)
- [azure-app-service-practical-guide](https://github.com/yeongseon/azure-app-service-practical-guide)
