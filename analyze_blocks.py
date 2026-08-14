import json
from pathlib import Path

log_path = Path("~/.aegis/guard_log.jsonl").expanduser()
with open(log_path, "r") as f:
    for line in f:
        if line.strip():
            r = json.loads(line)
            ts = r.get("timestamp_iso", "")
            if ts.startswith("2026-08-11T19:59") or r["timestamp"] < 1786500000:
                continue
            if r["action"] == "block":
                print(f"[{r['rule']}] {r['reason']}")
