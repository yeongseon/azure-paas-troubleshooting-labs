import os
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

# Allocate memory on startup
ALLOC_MB = int(os.environ.get("ALLOC_MB", 100))
_memory_block = bytearray(ALLOC_MB * 1024 * 1024)
_startup_time = datetime.utcnow().isoformat()


@app.route("/health")
def health():
    return jsonify(status="healthy")


@app.route("/stats")
def stats():
    return jsonify(alloc_mb=ALLOC_MB, startup=_startup_time)
