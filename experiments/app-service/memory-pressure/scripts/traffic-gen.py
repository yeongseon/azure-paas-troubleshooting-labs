"""Generate load against memory-pressure lab apps.

Usage:
    python traffic-gen.py --base-url https://memlabapp-1.azurewebsites.net
    python traffic-gen.py --base-url https://memlabapp-1.azurewebsites.net \
        --duration 300 --concurrency 10 --interval 0.5
"""

import argparse
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError


def send_request(url: str, timeout: int = 10) -> dict:
    """Send a single GET request and return timing info."""
    start = time.monotonic()
    try:
        req = Request(url)
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            resp.read()
    except URLError as e:
        elapsed = time.monotonic() - start
        return {"status": 0, "error": str(e), "elapsed_ms": elapsed * 1000}
    except Exception as e:
        elapsed = time.monotonic() - start
        return {"status": 0, "error": str(e), "elapsed_ms": elapsed * 1000}

    elapsed = time.monotonic() - start
    return {"status": status, "error": None, "elapsed_ms": elapsed * 1000}


def run_load(base_url: str, duration: int, concurrency: int, interval: float):
    """Run load generation for the specified duration."""
    health_url = f"{base_url.rstrip('/')}/health"
    stats_url = f"{base_url.rstrip('/')}/stats"

    print(f"[{datetime.utcnow().isoformat()}] Starting load generation")
    print(f"  Target:      {base_url}")
    print(f"  Duration:    {duration}s")
    print(f"  Concurrency: {concurrency}")
    print(f"  Interval:    {interval}s")
    print()

    total = 0
    errors = 0
    latencies = []
    end_time = time.monotonic() + duration

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        while time.monotonic() < end_time:
            futures = [
                pool.submit(send_request, health_url) for _ in range(concurrency)
            ]

            for f in as_completed(futures):
                result = f.result()
                total += 1
                latencies.append(result["elapsed_ms"])
                if result["error"]:
                    errors += 1
                    print(f"  ERR: {result['error']}")

            time.sleep(interval)

    # Summary
    latencies.sort()
    print()
    print(f"[{datetime.utcnow().isoformat()}] Load generation complete")
    print(f"  Total requests: {total}")
    print(f"  Errors:         {errors}")
    if latencies:
        print(f"  p50 latency:    {latencies[len(latencies) // 2]:.1f} ms")
        print(f"  p95 latency:    {latencies[int(len(latencies) * 0.95)]:.1f} ms")
        print(f"  p99 latency:    {latencies[int(len(latencies) * 0.99)]:.1f} ms")

    # Fetch stats
    print()
    print("App stats:")
    result = send_request(stats_url)
    if result["error"]:
        print(f"  Could not fetch stats: {result['error']}")
    else:
        from urllib.request import urlopen as uo
        import json

        with uo(stats_url, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"  Allocated MB: {data.get('alloc_mb')}")
            print(f"  Startup time: {data.get('startup')}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate traffic for memory-pressure lab"
    )
    parser.add_argument("--base-url", required=True, help="Base URL of the app")
    parser.add_argument(
        "--duration", type=int, default=120, help="Duration in seconds (default: 120)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=5, help="Concurrent requests (default: 5)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Interval between batches in seconds (default: 1.0)",
    )
    args = parser.parse_args()

    run_load(args.base_url, args.duration, args.concurrency, args.interval)


if __name__ == "__main__":
    main()
