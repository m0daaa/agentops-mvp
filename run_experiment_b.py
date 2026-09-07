#!/usr/bin/env python3
"""
Automate a controlled Before/After comparison for Experiment B (Tool Scaling
Isolation): same workload, only the HPA replica count differs.

Phase 1 (before): force tool-service to exactly 1 replica (patch the HPA's
min/max to 1), run the benchmark, record throughput/p95.

Phase 2 (after): restore the HPA to its normal min/max, run an *unmeasured*
warm-up burst long enough for the HPA to actually notice sustained CPU
pressure and scale out (and for the new pod to become Ready), THEN run the
exact same benchmark (same concurrency/requests/repeat) while replicas stay
elevated, and record throughput/p95.

This is designed to avoid two mistakes visible in earlier ad-hoc runs:
  - comparing runs with different concurrency / TOOL_BUSY_MS ("apples to
    oranges") -- both phases here use the exact same workload parameters.
  - measuring a window too short for the HPA to react. The HPA's metrics
    refresh + scheduling + pod startup can easily take 60-120s, so a ~24s
    benchmark (as seen in earlier runs) never gives a second replica a
    chance to receive any traffic at all.

Usage (with `kubectl port-forward svc/tool-service 8001:8001` already running):
  python run_experiment_b.py --repeat 3

Requires: pip install requests
Requires: `kubectl` on PATH, pointed at the cluster; `bench.py` in the same
directory (this script imports it directly and reuses run_bench()).
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime

import bench  # reuse the existing benchmark driver (run_bench)


def kubectl(args_list, namespace=None, check=True):
    ns_args = ["-n", namespace] if namespace else []
    cmd = ["kubectl"] + args_list + ns_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"kubectl command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def patch_hpa(hpa_name, min_replicas, max_replicas, namespace=None):
    patch = f'{{"spec":{{"minReplicas":{min_replicas},"maxReplicas":{max_replicas}}}}}'
    kubectl(["patch", "hpa", hpa_name, "--type", "merge", "-p", patch], namespace)


def set_busy_ms(deployment, busy_ms, namespace=None):
    kubectl(["set", "env", f"deployment/{deployment}", f"TOOL_BUSY_MS={busy_ms}"], namespace)
    kubectl(["rollout", "status", f"deployment/{deployment}", "--timeout=120s"], namespace)


def get_ready_replicas(deployment, namespace=None):
    out = kubectl(["get", "deployment", deployment, "-o", "jsonpath={.status.readyReplicas}"],
                  namespace, check=False)
    try:
        return int(out)
    except ValueError:
        return 0


def wait_for_replicas(deployment, target, namespace=None, timeout=180, poll_interval=5):
    deadline = time.time() + timeout
    last = 0
    while time.time() < deadline:
        last = get_ready_replicas(deployment, namespace)
        if last >= target:
            return last
        time.sleep(poll_interval)
    return last


def warmup(url, concurrency, duration_s):
    """Generate continuous load for duration_s wall-clock seconds, discarding
    results -- just to give the HPA a sustained CPU signal and time for a new
    replica to become Ready before the measured phase begins."""
    print(f"Warm-up: sending load for {duration_s}s to let HPA scale out ...")
    deadline = time.time() + duration_s
    sent = 0
    while time.time() < deadline:
        batch = concurrency * 5
        bench.run_bench(url, concurrency, batch, target_format="tool")
        sent += batch
    print(f"Warm-up done ({sent} requests sent).")


def write_csv(path, rows):
    fieldnames = ["timestamp", "url", "format", "concurrency", "requests", "errors",
                  "total_time_s", "throughput_rps", "p50_ms", "p95_ms", "p99_ms", "mean_ms"]
    write_header = not os.path.exists(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


def run_measured(url, concurrency, requests_total, repeat, csv_path):
    rows = []
    for i in range(repeat):
        print(f"  measured run {i + 1}/{repeat} ...")
        res = bench.run_bench(url, concurrency, requests_total, target_format="tool")
        res.update({"url": url, "timestamp": datetime.utcnow().isoformat(), "format": "tool"})
        rows.append(res)
    write_csv(csv_path, rows)
    return rows


def summarize(label, rows):
    if not rows:
        print(f"{label}: no data")
        return
    thr = [r["throughput_rps"] for r in rows]
    p95 = [r["p95_ms"] for r in rows]
    print(f"{label}: n={len(rows)}  throughput mean={sum(thr) / len(thr):.1f} req/s  "
          f"p95 mean={sum(p95) / len(p95):.1f} ms")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8001/run")
    p.add_argument("--deployment", default="tool-service")
    p.add_argument("--hpa", default="tool-service-hpa")
    p.add_argument("--namespace", default=None)
    p.add_argument("--busy-ms", type=int, default=500)
    p.add_argument("--concurrency", type=int, default=100)
    p.add_argument("--requests", type=int, default=20000,
                    help="requests per measured run (same for before/after)")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--warmup-seconds", type=int, default=90)
    p.add_argument("--csv-before", default="artifacts/bench/tool_before_hpa_clean.csv")
    p.add_argument("--csv-after", default="artifacts/bench/tool_after_hpa_clean.csv")
    p.add_argument("--restore-max-replicas", type=int, default=5)
    args = p.parse_args()

    print("== Phase 1: BEFORE (forcing exactly 1 replica) ==")
    patch_hpa(args.hpa, 1, 1, args.namespace)
    set_busy_ms(args.deployment, args.busy_ms, args.namespace)
    ready = wait_for_replicas(args.deployment, 1, args.namespace)
    print(f"tool-service ready replicas: {ready}")
    before_rows = run_measured(args.url, args.concurrency, args.requests, args.repeat, args.csv_before)
    summarize("BEFORE (1 replica)", before_rows)

    print("\n== Phase 2: AFTER (restoring HPA, warming up, then measuring) ==")
    patch_hpa(args.hpa, 1, args.restore_max_replicas, args.namespace)
    warmup(args.url, args.concurrency, args.warmup_seconds)
    ready = get_ready_replicas(args.deployment, args.namespace)
    print(f"tool-service ready replicas after warm-up: {ready}")
    if ready <= 1:
        print("WARNING: HPA has not scaled out yet. Consider increasing --warmup-seconds, "
              "or check `kubectl get hpa` / `kubectl top pods` for why CPU isn't triggering it.")
    after_rows = run_measured(args.url, args.concurrency, args.requests, args.repeat, args.csv_after)
    summarize(f"AFTER ({ready} replica(s))", after_rows)

    print("\n== Summary ==")
    summarize("BEFORE (1 replica)", before_rows)
    summarize(f"AFTER ({ready} replica(s))", after_rows)
    print(f"\nRaw data: {args.csv_before}, {args.csv_after}")


if __name__ == "__main__":
    main()
