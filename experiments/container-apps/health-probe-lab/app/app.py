import json
import os
import random
import socket
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: str) -> int:
    return int(os.environ.get(name, default).strip())


def env_float(name: str, default: str) -> float:
    return float(os.environ.get(name, default).strip())


BOOT_TIME = time.time()
STARTUP_DELAY_SECONDS = env_float("STARTUP_DELAY_SECONDS", "0")
DEPENDENCY_TIMEOUT_MS = env_int("DEPENDENCY_TIMEOUT_MS", "2000")
APP_MODE = os.environ.get("APP_MODE", "main").strip().lower()
APP_NAME = os.environ.get("APP_NAME", "health-probe-lab")
REVISION = os.environ.get(
    "CONTAINER_APP_REVISION", os.environ.get("REVISION", "unknown")
)
DEPENDENCY_URL = os.environ.get("DEPENDENCY_URL", "").strip()
HOSTNAME = socket.gethostname()
PID = os.getpid()

app = Flask(__name__)

_lock = threading.Lock()
_request_count = 0
_dependency_checks_ok = 0
_dependency_checks_fail = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def startup_complete() -> bool:
    return (time.time() - BOOT_TIME) >= STARTUP_DELAY_SECONDS


def startup_state() -> dict:
    now = time.time()
    elapsed = now - BOOT_TIME
    remaining = max(0.0, STARTUP_DELAY_SECONDS - elapsed)
    return {
        "boot_time_unix": BOOT_TIME,
        "startup_delay_seconds": STARTUP_DELAY_SECONDS,
        "startup_elapsed_seconds": round(elapsed, 3),
        "startup_remaining_seconds": round(remaining, 3),
        "startup_complete": remaining <= 0,
    }


def log_event(event: str, **fields) -> None:
    payload = {
        "timestamp": utc_now(),
        "event": event,
        "app_name": APP_NAME,
        "app_mode": APP_MODE,
        "revision": REVISION,
        "hostname": HOSTNAME,
        "pid": PID,
    }
    payload.update(fields)
    print(json.dumps(payload, sort_keys=True), flush=True)


def next_request_count() -> int:
    global _request_count
    with _lock:
        _request_count += 1
        return _request_count


def record_dependency_result(success: bool) -> None:
    global _dependency_checks_ok, _dependency_checks_fail
    with _lock:
        if success:
            _dependency_checks_ok += 1
        else:
            _dependency_checks_fail += 1


def metrics_snapshot() -> dict:
    with _lock:
        return {
            "request_count": _request_count,
            "dependency_checks_ok": _dependency_checks_ok,
            "dependency_checks_fail": _dependency_checks_fail,
        }


def build_response(status_code: int, **payload):
    body = {
        "status_code": status_code,
        "timestamp": utc_now(),
        **payload,
    }
    response = jsonify(body)
    response.status_code = status_code
    return response


def maybe_log_startup_complete(context: str) -> None:
    state = startup_state()
    if state["startup_complete"]:
        log_event("STARTUP_COMPLETE", context=context, startup=state)


def check_dependency(source: str) -> tuple[bool, dict]:
    if not DEPENDENCY_URL:
        result = {
            "source": source,
            "dependency_url": DEPENDENCY_URL,
            "reason": "DEPENDENCY_URL not configured",
            "timeout_ms": DEPENDENCY_TIMEOUT_MS,
        }
        record_dependency_result(False)
        log_event("DEPENDENCY_CHECK_FAIL", **result)
        return False, result

    started = time.time()
    try:
        response = requests.get(DEPENDENCY_URL, timeout=DEPENDENCY_TIMEOUT_MS / 1000.0)
        duration_ms = round((time.time() - started) * 1000, 2)
        success = response.ok
        result = {
            "source": source,
            "dependency_url": DEPENDENCY_URL,
            "timeout_ms": DEPENDENCY_TIMEOUT_MS,
            "duration_ms": duration_ms,
            "status_code": response.status_code,
            "response_ok": response.ok,
        }
        record_dependency_result(success)
        log_event(
            "DEPENDENCY_CHECK_OK" if success else "DEPENDENCY_CHECK_FAIL", **result
        )
        return success, result
    except requests.RequestException as exc:
        duration_ms = round((time.time() - started) * 1000, 2)
        result = {
            "source": source,
            "dependency_url": DEPENDENCY_URL,
            "timeout_ms": DEPENDENCY_TIMEOUT_MS,
            "duration_ms": duration_ms,
            "error": str(exc),
        }
        record_dependency_result(False)
        log_event("DEPENDENCY_CHECK_FAIL", **result)
        return False, result


@app.before_request
def before_request_logging():
    request.environ["request_count"] = next_request_count()
    log_event(
        "REQUEST_START",
        method=request.method,
        path=request.path,
        query_string=request.query_string.decode("utf-8", errors="ignore"),
        remote_addr=request.headers.get("X-Forwarded-For", request.remote_addr),
        request_count=request.environ["request_count"],
    )


@app.after_request
def after_request_logging(response):
    log_event(
        "REQUEST_END",
        method=request.method,
        path=request.path,
        status_code=response.status_code,
        request_count=request.environ.get("request_count"),
    )
    return response


log_event("BOOT_START", startup=startup_state())


@app.route("/startup")
def startup_probe():
    state = startup_state()
    if state["startup_complete"]:
        log_event("STARTUP_COMPLETE", context="startup_probe", startup=state)
        return build_response(
            200, status="startup-complete", startup=state, metrics=metrics_snapshot()
        )
    return build_response(
        503, status="starting", startup=state, metrics=metrics_snapshot()
    )


@app.route("/healthz")
def healthz():
    state = startup_state()
    if not state["startup_complete"]:
        return build_response(
            503, status="starting", startup=state, metrics=metrics_snapshot()
        )
    maybe_log_startup_complete("healthz")
    return build_response(
        200, status="healthy", startup=state, metrics=metrics_snapshot()
    )


@app.route("/live")
def live():
    state = startup_state()
    if not state["startup_complete"]:
        return build_response(
            503, status="starting", startup=state, metrics=metrics_snapshot()
        )

    if env_bool("LIVENESS_CHECK_DEPENDENCY", "false"):
        ok, result = check_dependency("liveness")
        return build_response(
            200 if ok else 503,
            status="alive" if ok else "dependency-failed",
            dependency=result,
            startup=state,
            metrics=metrics_snapshot(),
        )

    maybe_log_startup_complete("live")
    return build_response(
        200,
        status="alive",
        dependency={"checked": False},
        startup=state,
        metrics=metrics_snapshot(),
    )


@app.route("/ready")
def ready():
    state = startup_state()
    if not state["startup_complete"]:
        return build_response(
            503, status="starting", startup=state, metrics=metrics_snapshot()
        )

    if env_bool("READINESS_CHECK_DEPENDENCY", "false"):
        ok, result = check_dependency("readiness")
        return build_response(
            200 if ok else 503,
            status="ready" if ok else "dependency-unready",
            dependency=result,
            startup=state,
            metrics=metrics_snapshot(),
        )

    maybe_log_startup_complete("ready")
    return build_response(
        200,
        status="ready",
        dependency={"checked": False},
        startup=state,
        metrics=metrics_snapshot(),
    )


@app.route("/dependency/health")
def dependency_health_proxy():
    ok, result = check_dependency("dependency-endpoint")
    return build_response(
        200 if ok else 503,
        status="dependency-ok" if ok else "dependency-failed",
        dependency=result,
        metrics=metrics_snapshot(),
    )


@app.route("/health")
def dependency_health():
    if APP_MODE != "dependency":
        return build_response(
            404,
            status="not-found",
            message="/health is only available when APP_MODE=dependency",
        )

    delay_ms = env_int("DEPENDENCY_DELAY_MS", "0")
    fail_rate = max(0.0, min(100.0, env_float("DEPENDENCY_FAIL_RATE", "0")))
    healthy = env_bool("DEPENDENCY_HEALTHY", "true")

    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

    should_fail = (not healthy) or (random.random() * 100 < fail_rate)
    status_code = 503 if should_fail else 200
    return build_response(
        status_code,
        status="unhealthy" if should_fail else "healthy",
        dependency_mode=True,
        dependency_settings={
            "healthy": healthy,
            "delay_ms": delay_ms,
            "fail_rate": fail_rate,
        },
        metrics=metrics_snapshot(),
    )


@app.route("/")
def index():
    return build_response(
        200,
        app_name=APP_NAME,
        app_mode=APP_MODE,
        revision=REVISION,
        replica=HOSTNAME,
        pid=PID,
        startup=startup_state(),
        metrics=metrics_snapshot(),
    )


@app.route("/delay")
def delay():
    seconds = max(0.0, env_float_from_request("seconds", "0"))
    time.sleep(seconds)
    return build_response(
        200, status="delayed", delay_seconds=seconds, metrics=metrics_snapshot()
    )


@app.route("/cpu")
def cpu():
    seconds = max(0.0, env_float_from_request("seconds", "0"))
    end_time = time.time() + seconds
    value = 0
    while time.time() < end_time:
        value += 1
    return build_response(
        200,
        status="cpu-complete",
        cpu_seconds=seconds,
        iterations=value,
        metrics=metrics_snapshot(),
    )


@app.route("/status")
def status():
    code = int(request.args.get("code", "200"))
    return build_response(
        code, status="custom-status", requested_status=code, metrics=metrics_snapshot()
    )


def env_float_from_request(name: str, default: str) -> float:
    return float(request.args.get(name, default))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
