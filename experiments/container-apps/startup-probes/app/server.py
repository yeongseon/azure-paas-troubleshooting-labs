import http.server
import os
import time
import json
import socketserver

STARTUP_DELAY_SECONDS = int(os.environ.get("STARTUP_DELAY_SECONDS", "10"))
PORT = int(os.environ.get("PORT", "8080"))

print(
    f"Simulating slow startup: waiting {STARTUP_DELAY_SECONDS}s before accepting traffic"
)
time.sleep(STARTUP_DELAY_SECONDS)
print("Startup complete, server ready")

_ready_timestamp = time.time()
_ready = True


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"status": "healthy", "ready": _ready})
        elif self.path == "/readyz":
            if _ready:
                self._respond(200, {"status": "ready"})
            else:
                self._respond(503, {"status": "not ready"})
        elif self.path == "/stats":
            self._respond(
                200,
                {
                    "startup_delay_configured": STARTUP_DELAY_SECONDS,
                    "ready_since": _ready_timestamp,
                    "uptime_seconds": time.time() - _ready_timestamp,
                },
            )
        else:
            self._respond(200, {"message": "ok"})

    def _respond(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {args[0]}")


with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Listening on port {PORT}")
    httpd.serve_forever()
