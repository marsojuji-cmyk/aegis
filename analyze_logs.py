import json
from pathlib import Path
from collections import defaultdict

log_path = Path("~/.aegis/guard_log.jsonl").expanduser()
if not log_path.exists():
    print("No log found.")
    exit(1)

total_lines = 0
valid_records = 0
malformed_json = 0
missing_required_fields = 0
invalid_environment = 0
unknown_run_id = 0
duplicate_event_ids = 0
valid_requests = 0
flagged_requests = 0

REQUIRED_FIELDS = {
    "event_id", "request_id", "run_id", "environment", 
    "provider", "rule", "action", "would_block", 
    "shadow_mode", "timestamp_iso", "reason", "redaction_version"
}

VALID_ENVIRONMENTS = {"test", "development", "staging", "production"}

records = []
seen_events = set()

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
        if not REQUIRED_FIELDS.issubset(set(r.keys())):
            missing_required_fields += 1
            continue

        # Check dupes
        event_id = r.get("event_id")
        if event_id in seen_events:
            duplicate_event_ids += 1
            continue
        seen_events.add(event_id)

        # Check Environment
        env = r.get("environment")
        if env not in VALID_ENVIRONMENTS:
            invalid_environment += 1
            continue
            
        # Check Run ID
        run = r.get("run_id")
        if not run or run == "unknown" or run == "default-run" or len(str(run)) < 8:
            unknown_run_id += 1
            continue

        valid_records += 1
        records.append(r)

# Filter for legitimate usage denominator
real_records = [r for r in records if r.get("environment") in ["development", "production", "staging"]]

requests = defaultdict(list)
for r in real_records:
    requests[r.get("request_id")].append(r)

valid_requests = len(requests)
flagged_rules = defaultdict(int)

for req_id, events in requests.items():
    blocks = [e for e in events if e.get("would_block") is True]
    if blocks:
        flagged_requests += 1
        for b in blocks:
            flagged_rules[b.get("rule")] += 1

print(f"--- AEGIS LOG ACCOUNTING ---")
print(f"total_lines: {total_lines}")
print(f"valid_records: {valid_records}")
print(f"malformed_json: {malformed_json}")
print(f"missing_required_fields: {missing_required_fields}")
print(f"invalid_environment: {invalid_environment}")
print(f"unknown_run_id: {unknown_run_id}")
print(f"duplicate_event_ids: {duplicate_event_ids}")
print(f"\n--- REQUEST TELEMETRY ---")
print(f"valid_requests: {valid_requests}")
print(f"flagged_requests: {flagged_requests}")

if valid_requests > 0:
    block_rate = (flagged_requests / valid_requests) * 100
    print(f"legitimate_would_block_request_rate: {block_rate:.2f}%")
else:
    print("legitimate_would_block_request_rate: N/A (no legitimate requests)")

if flagged_requests > 0:
    print("\n--- FLAGGED RULES ---")
    for rule, count in flagged_rules.items():
        print(f"- {rule}: {count} rule hits")
