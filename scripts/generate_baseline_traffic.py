#!/usr/bin/env python3
import os
import sys
import argparse
from aegis.router_pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()

    env = os.environ.get("AEGIS_ENV")
    run_id = os.environ.get("AEGIS_RUN_ID")

    if not env or not run_id:
        print("ERROR: AEGIS_ENV and AEGIS_RUN_ID must be set")
        sys.exit(1)

    print(f"Starting baseline traffic generator (count={args.count})")
    print(f"Environment: {env}")
    print(f"Run ID: {run_id}")

    seen_requests = set()

    for i in range(args.count):
        task_label = f"controlled development baseline traffic {i}"
        
        # We invoke the mock provider directly to avoid real network calls
        result = run_pipeline(
            task=task_label,
            model="mock",
            mode="explore",
            skip_preflight=True,
            dry_run=False
        )

        if not result.ok:
            print(f"ERROR: Pipeline failed on iteration {i}: {result.error}")
            sys.exit(1)
            
        if result.provider != "mock":
            print(f"ERROR: Non-mock provider used: {result.provider}")
            sys.exit(1)

        req_id = result.meta.get("request_id") if result.meta else None
        
        if not req_id:
            print(f"ERROR: Missing request_id on iteration {i}")
            sys.exit(1)

        if req_id in seen_requests:
            print(f"ERROR: Duplicate request_id detected: {req_id}")
            sys.exit(1)

        seen_requests.add(req_id)

    print(f"\n--- RUN SUMMARY ---")
    print(f"Generated {len(seen_requests)} requests successfully.")
    print(f"All requests used 'mock' provider and had unique request_ids.")

if __name__ == "__main__":
    main()
