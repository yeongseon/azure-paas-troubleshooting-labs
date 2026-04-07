import azure.functions as func
import logging
import os
import time

INIT_DELAY_SECONDS = int(os.environ.get("INIT_DELAY_SECONDS", "0"))

if INIT_DELAY_SECONDS > 0:
    logging.info("Simulating slow init: sleeping %d seconds", INIT_DELAY_SECONDS)
    time.sleep(INIT_DELAY_SECONDS)

_init_timestamp = time.time()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="ping")
def ping(req: func.HttpRequest) -> func.HttpResponse:
    uptime = time.time() - _init_timestamp
    return func.HttpResponse(
        f'{{"status":"ok","uptime_seconds":{uptime:.2f},"init_delay":{INIT_DELAY_SECONDS}}}',
        mimetype="application/json",
    )


@app.route(route="heavy-init")
def heavy_init(req: func.HttpRequest) -> func.HttpResponse:
    import json

    return func.HttpResponse(
        json.dumps(
            {
                "init_delay_configured": INIT_DELAY_SECONDS,
                "init_timestamp": _init_timestamp,
                "current_timestamp": time.time(),
                "uptime_seconds": time.time() - _init_timestamp,
            }
        ),
        mimetype="application/json",
    )
