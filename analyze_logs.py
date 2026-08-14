import json
from pathlib import Path
from collections import defaultdict
import datetime

log_path = Path("~/.aegis/guard_log.jsonl").expanduser()
if not log_path.exists():
    print("No log found.")
    exit(1)

records = []
with open(log_path, "r") as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))

real_records = []
for r in records:
    ts = r.get("timestamp_iso", "")
    if ts.startswith("2026-08-11T19:59") or r["timestamp"] < 1786500000:
        continue
    real_records.append(r)

print(f"Total records in file: {len(records)}")
print(f"Test burst records filtered: {len(records) - len(real_records)}")
print(f"Real records to analyze: {len(real_records)}\n")

if not real_records:
    print("No real records found!")
    exit(0)

# We want to group by unique calls.
# A single tool call generates a budget, loop, mission, and optionally signal decision.
# Since we don't have a correlation ID, we can group by timestamp (assuming they occur very close to each other).
# Or we can just look at how many times budget was checked, which is 1 per call.
calls = [r for r in real_records if r["rule"] == "budget"]

print(f"Estimated Unique Tool Calls: {len(calls)}")

rules = defaultdict(int)
actions = defaultdict(int)
shadow_blocks = defaultdict(int)
scores = []

for r in real_records:
    rules[r["rule"]] += 1
    actions[r["action"]] += 1
    if r["action"] == "block" or (r["action"] == "allow" and "velocity" in r.get("reason", "").lower() and "exceeded" in r.get("reason", "").lower()):
        # Note: shadow mode logs as "block" if it would have blocked.
        shadow_blocks[r["rule"]] += 1
        
    if r["score"] is not None:
        scores.append(r["score"])

print("\n--- RULE BREAKDOWN ---")
for rule, count in rules.items():
    print(f"- {rule}: {count} evaluations")

print("\n--- ACTIONS ---")
for action, count in actions.items():
    print(f"- {action}: {count}")

print("\n--- SHADOW BLOCKS (False Positives if flipped now) ---")
for rule, count in shadow_blocks.items():
    print(f"- {rule}: {count} would-be blocks")

if len(calls) > 0 and sum(shadow_blocks.values()) > 0:
    fp_rate = sum(shadow_blocks.values()) / len(calls) * 100
    print(f"\nEstimated False Positive Rate: {fp_rate:.2f}%")
else:
    print("\nEstimated False Positive Rate: 0.00%")

if scores:
    print(f"\nAverage Signal Score: {sum(scores)/len(scores):.2f}")
    print(f"Min Signal Score: {min(scores):.2f}")
    print(f"Max Signal Score: {max(scores):.2f}")

