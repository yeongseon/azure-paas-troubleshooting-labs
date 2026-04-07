"""Measure Azure Functions cold-start latency.

Triggers cold starts by waiting for idle timeout, then measures response time.

Usage:
    python measure-cold-start.py --function-url https://<func-app>.azurewebsites.net/api/ping
    python measure-cold-start.py --function-url https://<func-app>.azurewebsites.net/api/ping \
        --rounds 5 --idle-wait 600
"""

import argparse
import json
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError


def measure_single_request(url: str, timeout: int = 30) -> dict:
    start = time.monotonic()
    try:
        req = Request(url)
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            status = resp.status
    except URLError as e:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "latency_ms": (time.monotonic() - start) * 1000,
            "status": 0,
            "error": str(e),
        }

    latency_ms = (time.monotonic() - start) * 1000
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "latency_ms": latency_ms,
        "status": status,
        "uptime_seconds": body.get("uptime_seconds"),
        "init_delay": body.get("init_delay"),
    }


def warm_up(url: str):
    print(f"Warming up: {url}")
    for _ in range(3):
        measure_single_request(url)
        time.sleep(1)


def measure_warm_baseline(url: str, count: int = 5) -> list:
    print(f"Measuring warm baseline ({count} requests)...")
    results = []
    for i in range(count):
        result = measure_single_request(url)
        results.append(result)
        print(f"  Warm #{i + 1}: {result['latency_ms']:.1f} ms")
        time.sleep(2)
    return results


def measure_cold_start(url: str, idle_wait: int) -> dict:
    print(f"Waiting {idle_wait}s for idle timeout (cold start trigger)...")
    time.sleep(idle_wait)

    print("Sending cold-start request...")
    result = measure_single_request(url)
    print(f"  Cold start: {result['latency_ms']:.1f} ms")

    if result.get("uptime_seconds") is not None and result["uptime_seconds"] < 5:
        result["likely_cold_start"] = True
    else:
        result["likely_cold_start"] = False

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Measure Azure Functions cold-start latency"
    )
    parser.add_argument(
        "--function-url", required=True, help="Function HTTP trigger URL"
    )
    parser.add_argument(
        "--rounds", type=int, default=3, help="Number of cold-start rounds (default: 3)"
    )
    parser.add_argument(
        "--idle-wait",
        type=int,
        default=600,
        help="Seconds to wait for idle timeout (default: 600)",
    )
    args = parser.parse_args()

    print(f"=== Cold Start Measurement ===")
    print(f"URL:       {args.function_url}")
    print(f"Rounds:    {args.rounds}")
    print(f"Idle wait: {args.idle_wait}s")
    print()

    warm_up(args.function_url)
    warm_results = measure_warm_baseline(args.function_url)

    cold_results = []
    for r in range(args.rounds):
        print(f"\n--- Round {r + 1}/{args.rounds} ---")
        result = measure_cold_start(args.function_url, args.idle_wait)
        cold_results.append(result)

    # Report
    warm_latencies = [r["latency_ms"] for r in warm_results if r.get("status") == 200]
    cold_latencies = [r["latency_ms"] for r in cold_results if r.get("status") == 200]

    print("\n=== Results ===")
    if warm_latencies:
        print(f"Warm avg:  {sum(warm_latencies) / len(warm_latencies):.1f} ms")
        print(f"Warm p50:  {sorted(warm_latencies)[len(warm_latencies) // 2]:.1f} ms")
    if cold_latencies:
        print(f"Cold avg:  {sum(cold_latencies) / len(cold_latencies):.1f} ms")
        print(f"Cold p50:  {sorted(cold_latencies)[len(cold_latencies) // 2]:.1f} ms")
        print(f"Cold max:  {max(cold_latencies):.1f} ms")
    if warm_latencies and cold_latencies:
        ratio = (sum(cold_latencies) / len(cold_latencies)) / (
            sum(warm_latencies) / len(warm_latencies)
        )
        print(f"Cold/Warm: {ratio:.1f}x")

    output = {
        "warm_results": warm_results,
        "cold_results": cold_results,
    }
    output_file = "cold-start-results.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nRaw data saved to {output_file}")


if __name__ == "__main__":
    main()
