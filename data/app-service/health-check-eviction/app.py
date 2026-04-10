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
