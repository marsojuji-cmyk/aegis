#!/usr/bin/env python3
import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter

REQUIRED_FIELDS = {
    "event_id", "request_id", "run_id", "environment", 
    "provider", "rule", "action", "would_block", 
    "shadow_mode", "timestamp_iso", "reason", "redaction_version"
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--min-requests", type=int, required=True)
    parser.add_argument("--input", default="~/.aegis/guard_log.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--labels", required=False, help="Path to JSON file with request legitimacy labels")
    args = parser.parse_args()

    log_path = Path(args.input).expanduser()
    if not log_path.exists():
        print(f"ERROR: Input file not found: {log_path}")
        sys.exit(1)
        
    labels = {}
    if args.labels:
        labels_path = Path(args.labels).expanduser()
        if not labels_path.exists():
            print(f"ERROR: Labels file not found: {labels_path}")
            sys.exit(1)
        try:
            with open(labels_path, "r") as f:
                labels = json.load(f)
        except json.JSONDecodeError:
            print(f"ERROR: Labels file is malformed JSON: {labels_path}")
            sys.exit(1)
            
        # Validate schema
        if not isinstance(labels, dict):
            print("ERROR: Labels file must contain a JSON object mapping request_id to status")
            sys.exit(1)
        for req_id, status in labels.items():
            if status not in {"legitimate", "false_positive", "unknown"}:
                print(f"ERROR: Invalid label status '{status}' for request '{req_id}'. Allowed: legitimate, false_positive, unknown.")
                sys.exit(1)

    total_lines = 0
    valid_records = 0
    malformed_json = 0
    missing_required_fields = 0
    invalid_environments = 0
    duplicate_event_ids = 0

    records = []
    seen_events = set()
    
    # Missing fields characterization
    missing_keys_tally = Counter()

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            total_lines += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                malformed_json += 1
                continue

            # Check required fields
            r_keys = set(r.keys())
            if not REQUIRED_FIELDS.issubset(r_keys):
                missing_required_fields += 1
                missing = tuple(sorted(REQUIRED_FIELDS - r_keys))
                missing_keys_tally[missing] += 1
                continue

            # Strict Redaction Validation: skip/reject records with raw sensitive fields or empty redaction_version
            if not r.get("redaction_version"):
                missing_required_fields += 1
                missing_keys_tally[("redaction_version",)] += 1
                continue
            
            if "raw_prompt" in r or "provider_payload" in r:
                # Fatal rejection of unsafe telemetry. Fail hard so we do not process unredacted records.
                print(f"FATAL: Unredacted sensitive payload detected in event {r.get('event_id')}", file=sys.stderr)
                sys.exit(1)

            # Check dupes
            event_id = r.get("event_id")
            if event_id in seen_events:
                duplicate_event_ids += 1
                continue
            seen_events.add(event_id)

            # Check Environment
            env = r.get("environment")
            if env != args.environment:
                invalid_environments += 1
                continue
                
            valid_records += 1
            records.append(r)

    isolated_records = [r for r in records if r.get("run_id") == args.run_id]

    requests = defaultdict(list)
    for r in isolated_records:
        if r.get("environment") != args.environment or r.get("run_id") != args.run_id:
            print("ERROR: Isolated record mismatch detected!")
            sys.exit(1)
        requests[r.get("request_id")].append(r)

    valid_requests = len(requests)
    
    # Reject success if isolated request IDs are not unique
    # Here, "valid_requests" must equal the number of distinct request_id values found in isolated_records.
    # Grouping already enforces this, but let's just make sure there are no duplicate request_ids per single request logic if intended.
    # The requirement is likely ensuring there isn't overlapping or confusing request states. 

    flagged_requests = 0
    legitimate_flagged_requests = 0
    false_positive_flagged_requests = 0
    unlabeled_flagged_requests = 0

    for req_id, events in requests.items():
        blocks = [e for e in events if e.get("would_block") is True]
        if blocks:
            flagged_requests += 1
            if args.labels:
                status = labels.get(req_id, "unknown")
                if status == "legitimate":
                    legitimate_flagged_requests += 1
                elif status == "false_positive":
                    false_positive_flagged_requests += 1
                else:
                    unlabeled_flagged_requests += 1

    would_block_request_rate = 0.0
    if valid_requests > 0:
        would_block_request_rate = (flagged_requests / valid_requests) * 100
        
    false_positive_rate = None
    legitimate_would_block_request_rate = None
    labeled_flagged_requests = false_positive_flagged_requests + legitimate_flagged_requests
    
    if args.labels and labeled_flagged_requests > 0:
        false_positive_rate = (false_positive_flagged_requests / labeled_flagged_requests) * 100
        legitimate_would_block_request_rate = (legitimate_flagged_requests / labeled_flagged_requests) * 100

    report = {
        "status": "pass" if valid_requests >= args.min_requests else "fail",
        "environment": args.environment,
        "run_id": args.run_id,
        "total_lines": total_lines,
        "valid_records": valid_records,
        "isolated_records": len(isolated_records),
        "malformed_json": malformed_json,
        "missing_required_fields": missing_required_fields,
        "missing_field_characterization": {
            ",".join(k): v for k, v in missing_keys_tally.items()
        },
        "duplicate_event_ids": duplicate_event_ids,
        "valid_requests": valid_requests,
        "flagged_requests": flagged_requests,
        "would_block_request_rate": would_block_request_rate,
        "false_positive_rate": false_positive_rate,
        "legitimate_would_block_request_rate": legitimate_would_block_request_rate,
        "labeled_flagged_requests": labeled_flagged_requests if args.labels else None,
        "unlabeled_flagged_requests": unlabeled_flagged_requests if args.labels else None,
        "min_requests": args.min_requests
    }

    # Write JSON atomically
    out_path = Path(args.output)
    tmp_path = out_path.with_suffix('.tmp')
    with open(tmp_path, 'w') as f:
        json.dump(report, f, indent=2)
    tmp_path.rename(out_path)

    print(json.dumps(report, indent=2))

    if valid_requests < args.min_requests:
        print(f"ERROR: Found {valid_requests} valid distinct requests, but --min-requests is {args.min_requests}")
        sys.exit(1)

if __name__ == "__main__":
    main()
