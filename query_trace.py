#!/usr/bin/env python3
"""
Query traces from the observability collector.

Usage:
  # list the most recent traces (newest first)
  python query_trace.py --list

  # look up one request's full trace (prompt version, tool latency, status, ...)
  python query_trace.py --request-id <request_id>

Assumes the observability service is reachable, e.g. via:
  kubectl port-forward svc/observability 9000:9000
"""
import argparse
import json
import sys

import requests


def list_traces(base_url: str, limit: int):
    r = requests.get(f"{base_url}/traces", params={"limit": limit}, timeout=10)
    r.raise_for_status()
    traces = r.json().get("traces", [])
    if not traces:
        print("No traces found.")
        return
    print(f"{'request_id':<38} {'status':<8} {'prompt_version':<16} {'model_version':<14} timestamp")
    for t in traces:
        print(f"{t.get('request_id', ''):<38} {t.get('status', ''):<8} "
              f"{t.get('prompt_version', ''):<16} {t.get('model_version', '') or '-':<14} {t.get('timestamp', '')}")


def get_trace(base_url: str, request_id: str):
    r = requests.get(f"{base_url}/trace/{request_id}", timeout=10)
    if r.status_code == 404:
        print(f"No trace found for request_id={request_id}", file=sys.stderr)
        sys.exit(1)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:9000", help="observability base URL")
    p.add_argument("--request-id", default=None, help="look up one trace by request_id")
    p.add_argument("--list", action="store_true", help="list the most recent traces")
    p.add_argument("--limit", type=int, default=20, help="max traces to list")
    args = p.parse_args()

    if args.request_id:
        get_trace(args.url, args.request_id)
    elif args.list:
        list_traces(args.url, args.limit)
    else:
        p.error("specify --request-id <id> or --list")


if __name__ == "__main__":
    main()
