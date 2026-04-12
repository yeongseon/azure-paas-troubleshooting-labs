import json
import logging
import os
import time
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
logger = logging.getLogger("coldstart")

START_TS = time.time()
DEPENDENCY_PROFILE = os.getenv("DEPENDENCY_PROFILE", "minimal")
INIT_PROFILE = os.getenv("INIT_PROFILE", "fast")
PLAN_TYPE = os.getenv("PLAN_TYPE", "consumption")
INIT_DELAY_SECONDS = 2.0 if INIT_PROFILE == "slow" else 0.0


def trace_marker(name: str, **extra: object) -> None:
    payload = {
        "dependency_profile": DEPENDENCY_PROFILE,
        "init_profile": INIT_PROFILE,
        "plan_type": PLAN_TYPE,
        "python_version": "3.11",
        **extra,
    }
    logger.warning("%s %s", name, json.dumps(payload, sort_keys=True))


trace_marker("coldstart.test.begin", phase="app-bootstrap")
trace_marker("coldstart.imports.begin", phase="framework-init")

if DEPENDENCY_PROFILE in ("moderate", "heavy"):
    import requests  # noqa: F401
    import pandas as pd  # noqa: F401

if DEPENDENCY_PROFILE == "heavy":
    import matplotlib  # noqa: F401
    import numpy as np  # noqa: F401
    import scipy  # noqa: F401
    import sklearn  # noqa: F401

trace_marker("coldstart.imports.end", phase="framework-init")
trace_marker("coldstart.appinit.begin", phase="app-init")


class ExpensiveSingleton:
    def __init__(self) -> None:
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.lookup = {f"k{i}": i for i in range(5000)}
        self.vector = [i * 3 for i in range(4000)]


singleton = ExpensiveSingleton()

if INIT_DELAY_SECONDS:
    time.sleep(INIT_DELAY_SECONDS)

trace_marker(
    "coldstart.appinit.end",
    phase="app-init",
    init_delay_seconds=INIT_DELAY_SECONDS,
)


@app.route(route="coldstart", methods=["GET"])
def coldstart(req: func.HttpRequest) -> func.HttpResponse:
    trace_marker("coldstart.handler.begin", phase="handler")
    now = datetime.now(timezone.utc)
    body = {
        "timestamp_utc": now.isoformat(),
        "uptime_seconds": round(time.time() - START_TS, 3),
        "init_delay": INIT_DELAY_SECONDS,
        "dependency_profile": DEPENDENCY_PROFILE,
        "init_profile": INIT_PROFILE,
        "plan_type": PLAN_TYPE,
        "singleton_created_at": singleton.created_at,
    }
    trace_marker("coldstart.handler.end", phase="handler")
    return func.HttpResponse(
        json.dumps(body),
        mimetype="application/json",
        status_code=200,
    )
