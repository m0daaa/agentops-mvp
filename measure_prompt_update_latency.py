#!/usr/bin/env python3
"""
Measure the end-to-end latency of a Prompt update: from `kubectl apply` (new
ConfigMap content) to agent-service actually serving the new prompt, detected
via the content-derived `prompt_version` hash returned by /invoke.

This quantifies Action Plan gap #4 ("Prompt Update Cycle 的量化") and depends
on agent-service/main.py returning `prompt_version` in its /invoke response
(compute_prompt_version(), added together with this script).

Usage (agent-service reachable via `kubectl port-forward svc/agent-service 8000:8000`):
  python measure_prompt_update_latency.py --repeat 5 --csv artifacts/bench/prompt_update_latency.csv

Requires: pip install requests
Requires: `kubectl` on PATH, pointed at the cluster running agent-service.
"""
import argparse
import csv
import hashlib
import os
import subprocess
import tempfile
import time
import uuid
from datetime import datetime

import requests

BASE_PROMPT = (
    "Default prompt for AgentOps MVP.\n\n"
    "Task: Return the input uppercased and a short note that the prompt version was read.\n"
)


def compute_version(text: str) -> str:
    if not text:
        return "unknown"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def get_current_version(url: str, timeout: float = 10.0) -> str:
    payload = {"input": "probe", "request_id": f"probe-{uuid.uuid4()}"}
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    version = body.get("prompt_version")
    if version is None:
        raise RuntimeError(
            "agent-service response has no 'prompt_version' field. "
            "Make sure agent-service/main.py was patched to return it."
        )
    return version


def apply_new_prompt(configmap: str, key: str, text: str, namespace: str | None) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8", newline="\n") as f:
        f.write(text)
        tmp_path = f.name
    try:
        ns_args = ["-n", namespace] if namespace else []
        create = subprocess.run(
            ["kubectl", "create", "configmap", configmap,
             f"--from-file={key}={tmp_path}", "-o", "yaml", "--dry-run=client"] + ns_args,
            capture_output=True, text=True, check=True,
        )
        subprocess.run(
            ["kubectl", "apply", "-f", "-"] + ns_args,
            input=create.stdout, capture_output=True, text=True, check=True,
        )
    finally:
        os.unlink(tmp_path)


def run_trial(url, configmap, key, namespace, poll_interval, timeout):
    baseline = get_current_version(url)

    marker = uuid.uuid4().hex[:8]
    new_text = BASE_PROMPT + f"# bench-marker: {marker}\n"
    expected_version = compute_version(new_text)

    apply_new_prompt(configmap, key, new_text, namespace)
    t0 = time.time()

    deadline = t0 + timeout
    attempts = 0
    observed = baseline
    while time.time() < deadline:
        attempts += 1
        observed = get_current_version(url)
        if observed == expected_version:
            break
        time.sleep(poll_interval)
    t1 = time.time()

    matched = observed == expected_version
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "configmap": configmap,
        "key": key,
        "baseline_version": baseline,
        "expected_version": expected_version,
        "observed_version": observed,
        "matched": matched,
        "latency_s": round(t1 - t0, 4),
        "poll_attempts": attempts,
        "poll_interval_s": poll_interval,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000/invoke")
    p.add_argument("--configmap", default="agent-prompts")
    p.add_argument("--key", default="default.txt")
    p.add_argument("--namespace", default=None)
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--poll-interval", type=float, default=0.1)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--csv", default=None)
    args = p.parse_args()

    results = []
    for i in range(args.repeat):
        print(f"Trial {i + 1}/{args.repeat} ...")
        res = run_trial(args.url, args.configmap, args.key, args.namespace,
                         args.poll_interval, args.timeout)
        results.append(res)
        status = "OK" if res["matched"] else "TIMEOUT/MISMATCH"
        print(f"  -> latency={res['latency_s']:.3f}s  attempts={res['poll_attempts']}  [{status}]")

    latencies = [r["latency_s"] for r in results if r["matched"]]
    if latencies:
        print("\nSummary (matched trials only):")
        print(f"  n={len(latencies)}  mean={sum(latencies) / len(latencies):.3f}s  "
              f"min={min(latencies):.3f}s  max={max(latencies):.3f}s")
    failed = len(results) - len(latencies)
    if failed:
        print(f"  {failed} trial(s) did not observe the expected version within timeout.")

    if args.csv:
        fieldnames = ["timestamp", "configmap", "key", "baseline_version", "expected_version",
                      "observed_version", "matched", "latency_s", "poll_attempts", "poll_interval_s"]
        write_header = not os.path.exists(args.csv)
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "a", newline="", encoding="utf-8") as cf:
            writer = csv.DictWriter(cf, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for r in results:
                writer.writerow(r)
        print(f"Appended results to {args.csv}")


if __name__ == "__main__":
    main()
