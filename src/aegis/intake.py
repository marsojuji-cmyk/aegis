import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from aegis.paths import ensure_home, ledger_path, reports_dir


def ingest_text(
    raw_text: str, sender: str = "local", channel: str = "cli"
) -> Dict[str, Any]:
  ensure_home()
  r_dir = reports_dir()
  r_dir.mkdir(parents=True, exist_ok=True)

  pattern = (
      r"^!(?P<cmd>BUG|TASK|STATUS|REPORT)\s*(?:\\[(?P<mod>[\\w-]+)\\])?\s*(?P<payload>.*)$"
  )
  match = re.match(pattern, raw_text.strip(), re.IGNORECASE | re.DOTALL)

  cmd_type = match.group("cmd").upper() if match else "TASK"
  module = match.group("mod") if (match and match.group("mod")) else "general"
  payload = match.group("payload").strip() if match else raw_text.strip()

  ts_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
  h = hashlib.sha256(f"{ts_now}:{payload}".encode()).hexdigest()[:6].upper()
  issue_id = f"ISS-{int(time.time())}-{h}"

  record = {
      "id": issue_id,
      "ts": ts_now,
      "channel": channel,
      "sender": sender,
      "type": cmd_type,
      "module": module,
      "summary": payload.splitlines()[0][:100] if payload else "",
      "body": payload,
      "status": "QUEUED",
      "priority": (
          "P1"
          if cmd_type == "BUG"
          else ("P2" if cmd_type == "TASK" else "P3")
      ),
  }

  out_file = r_dir / f"{issue_id}.json"
  out_file.write_text(json.dumps(record, indent=2))

  l_path = ledger_path()
  with open(l_path, "a") as f:
    f.write(
        json.dumps({
            "event": "ISSUE_INGEST",
            "id": issue_id,
            "module": module,
            "priority": record["priority"],
            "ts": ts_now,
        })
        + "\n"
    )

  return record


def list_reports(limit: int = 10) -> list:
  ensure_home()
  r_dir = reports_dir()
  if not r_dir.exists():
    return []
  files = sorted(
      r_dir.glob("ISS-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
  )
  return [json.loads(p.read_text()) for p in files[:limit]]
