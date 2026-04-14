import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, Response, jsonify, request, stream_with_context

app = Flask(__name__)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def log_event(payload):
    print(json.dumps(payload), flush=True)


@app.get("/")
def index():
    return jsonify(
        {
            "status": "ok",
            "service_name": os.getenv("SERVICE_NAME", "unknown"),
            "revision": os.getenv(
                "CONTAINER_APP_REVISION", os.getenv("WEBSITE_INSTANCE_ID", "unknown")
            ),
            "timestamp_utc": utc_now(),
        }
    )


@app.get("/delay")
def delay():
    request_id = request.headers.get("x-request-id", str(uuid4()))
    duration = int(request.args.get("duration", "60"))

    log_event(
        {
            "event": "delay_start",
            "request_id": request_id,
            "duration_seconds": duration,
            "timestamp_utc": utc_now(),
            "service_name": os.getenv("SERVICE_NAME", "unknown"),
        }
    )

    time.sleep(duration)

    log_event(
        {
            "event": "delay_complete",
            "request_id": request_id,
            "duration_seconds": duration,
            "timestamp_utc": utc_now(),
        }
    )

    return jsonify(
        {
            "request_id": request_id,
            "mode": "delay",
            "duration_seconds": duration,
            "completed_utc": utc_now(),
        }
    )


@app.get("/stream")
def stream():
    request_id = request.headers.get("x-request-id", str(uuid4()))
    duration = int(request.args.get("duration", "300"))
    interval = int(request.args.get("interval", "30"))

    @stream_with_context
    def generate():
        start = time.monotonic()
        elapsed = 0

        log_event(
            {
                "event": "stream_start",
                "request_id": request_id,
                "duration_seconds": duration,
                "interval_seconds": interval,
                "timestamp_utc": utc_now(),
            }
        )

        yield f"start request_id={request_id} ts={utc_now()}\n"

        while elapsed + interval < duration:
            time.sleep(interval)
            elapsed = round(time.monotonic() - start)
            log_event(
                {
                    "event": "stream_chunk",
                    "request_id": request_id,
                    "elapsed_seconds": elapsed,
                    "timestamp_utc": utc_now(),
                }
            )
            yield f"chunk elapsed={elapsed} ts={utc_now()}\n"

        remaining = max(duration - round(time.monotonic() - start), 0)
        if remaining:
            time.sleep(remaining)

        log_event(
            {
                "event": "stream_complete",
                "request_id": request_id,
                "duration_seconds": duration,
                "timestamp_utc": utc_now(),
            }
        )
        yield f"complete request_id={request_id} ts={utc_now()}\n"

    return Response(generate(), mimetype="text/plain")


@app.get("/sse")
def sse():
    request_id = request.headers.get("x-request-id", str(uuid4()))
    duration = int(request.args.get("duration", "300"))
    interval = int(request.args.get("interval", "30"))

    @stream_with_context
    def generate():
        start = time.monotonic()
        elapsed = 0

        log_event(
            {
                "event": "sse_start",
                "request_id": request_id,
                "duration_seconds": duration,
                "interval_seconds": interval,
                "timestamp_utc": utc_now(),
            }
        )

        yield f'event: started\ndata: {{"request_id": "{request_id}", "timestamp_utc": "{utc_now()}"}}\n\n'

        while elapsed + interval < duration:
            time.sleep(interval)
            elapsed = round(time.monotonic() - start)
            log_event(
                {
                    "event": "sse_chunk",
                    "request_id": request_id,
                    "elapsed_seconds": elapsed,
                    "timestamp_utc": utc_now(),
                }
            )
            yield f'event: progress\ndata: {{"elapsed_seconds": {elapsed}, "timestamp_utc": "{utc_now()}"}}\n\n'

        remaining = max(duration - round(time.monotonic() - start), 0)
        if remaining:
            time.sleep(remaining)

        log_event(
            {
                "event": "sse_complete",
                "request_id": request_id,
                "duration_seconds": duration,
                "timestamp_utc": utc_now(),
            }
        )
        yield f'event: complete\ndata: {{"request_id": "{request_id}", "timestamp_utc": "{utc_now()}"}}\n\n'

    return Response(
        generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
