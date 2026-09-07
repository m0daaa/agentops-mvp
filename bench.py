#!/usr/bin/env python3
"""
Simple benchmark script for agent-service.

Usage:
  python bench.py --url http://localhost:8000/invoke --concurrency 10 --requests 100

This script uses `requests` and `concurrent.futures.ThreadPoolExecutor` to send
HTTP POST requests concurrently and prints latency percentiles and throughput.
"""
import argparse
import csv
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from datetime import datetime


def worker(session, url, payload, timeout=10.0):
    start = time.time()
    try:
        r = session.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        status = 'ok'
    except Exception as e:
        status = f'error:{e}'
    elapsed = (time.time() - start) * 1000.0
    return elapsed, status


def percentile(sorted_list, p):
    if not sorted_list:
        return None
    k = (len(sorted_list)-1) * (p/100)
    f = int(k)
    c = min(f+1, len(sorted_list)-1)
    if f == c:
        return sorted_list[int(k)]
    d0 = sorted_list[f] * (c-k)
    d1 = sorted_list[c] * (k-f)
    return d0 + d1


def run_bench(url, concurrency, total, target_format="agent"):
    """
    target_format: 'agent' or 'tool'
    """
    latencies = []
    errors = 0
    error_samples = []
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=concurrency, pool_maxsize=concurrency)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    start_all = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = []
        for i in range(total):
            if target_format == 'tool':
                # tool expects: {request_id, action, args: {input, prompt}}
                payload = {
                    "request_id": f"bench-{i}",
                    "action": "default",
                    "args": {"input": f"bench-{i}", "prompt": ""},
                }
            else:
                # agent expects: {input, request_id?}
                payload = {"input": f"bench-{i}", "request_id": f"bench-{i}"}
            futures.append(ex.submit(worker, session, url, payload))

        for future in as_completed(futures):
            elapsed, status = future.result()
            latencies.append(elapsed)
            if not status.startswith('ok'):
                errors += 1
                if len(error_samples) < 3:
                    error_samples.append(status)

    duration = time.time() - start_all
    lat_sorted = sorted(latencies)
    throughput = total / duration if duration > 0 else 0.0
    out = {
        "requests": total,
        "concurrency": concurrency,
        "errors": errors,
        "total_time_s": round(duration, 4),
        "throughput_rps": round(throughput, 4),
        "p50_ms": round(percentile(lat_sorted, 50) if lat_sorted else 0.0, 4),
        "p95_ms": round(percentile(lat_sorted, 95) if lat_sorted else 0.0, 4),
        "p99_ms": round(percentile(lat_sorted, 99) if lat_sorted else 0.0, 4),
        "mean_ms": round(statistics.mean(lat_sorted) if lat_sorted else 0.0, 4),
    }
    print(f"Requests: {total}, Concurrency: {concurrency}, Errors: {errors}")
    if error_samples:
        print("Sample errors:")
        for e in error_samples:
            print(f"  {e}")
    print(f"Total time: {duration:.2f}s, Throughput: {out['throughput_rps']:.2f} req/s")
    if lat_sorted:
        print(f"p50: {out['p50_ms']:.2f} ms")
        print(f"p95: {out['p95_ms']:.2f} ms")
        print(f"p99: {out['p99_ms']:.2f} ms")
        print(f"mean: {out['mean_ms']:.2f} ms")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000/invoke")
    p.add_argument("--concurrency", type=int, default=10,
                   help="Single concurrency value (deprecated if --concurrency-list used)")
    p.add_argument("--concurrency-list", type=str, default=None,
                   help="Comma-separated list of concurrency values to run, e.g. 1,5,10,25")
    p.add_argument("--requests", type=int, default=100)
    p.add_argument("--format", type=str, default="agent", choices=["agent", "tool"], help="Payload format: 'agent' (default) or 'tool'")
    p.add_argument("--repeat", type=int, default=1, help="Repeat each concurrency N times")
    p.add_argument("--csv", type=str, default=None, help="Output CSV file path to append results")
    args = p.parse_args()

    conc_list = []
    if args.concurrency_list:
        try:
            conc_list = [int(x) for x in args.concurrency_list.split(",") if x.strip()]
        except Exception:
            conc_list = [args.concurrency]
    else:
        conc_list = [args.concurrency]

    results = []
    for c in conc_list:
        for r in range(args.repeat):
            print(f"Running bench: concurrency={c}, repeat={r+1}/{args.repeat}, format={args.format}")
            res = run_bench(args.url, c, args.requests, target_format=args.format)
            res.update({"url": args.url, "timestamp": datetime.utcnow().isoformat(), "format": args.format})
            results.append(res)

    if args.csv:
        fieldnames = ["timestamp", "url", "format", "concurrency", "requests", "errors", "total_time_s", "throughput_rps", "p50_ms", "p95_ms", "p99_ms", "mean_ms"]
        write_header = not __import__("os").path.exists(args.csv)
        with open(args.csv, "a", newline="", encoding="utf-8") as cf:
            writer = csv.DictWriter(cf, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for r in results:
                writer.writerow({
                    "timestamp": r.get("timestamp"),
                    "url": r.get("url"),
                    "format": r.get("format"),
                    "concurrency": r.get("concurrency"),
                    "requests": r.get("requests"),
                    "errors": r.get("errors"),
                    "total_time_s": r.get("total_time_s"),
                    "throughput_rps": r.get("throughput_rps"),
                    "p50_ms": r.get("p50_ms"),
                    "p95_ms": r.get("p95_ms"),
                    "p99_ms": r.get("p99_ms"),
                    "mean_ms": r.get("mean_ms"),
                })
        print(f"Appended results to {args.csv}")



if __name__ == '__main__':
    main()
