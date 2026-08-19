#!/usr/bin/env python3
"""Screen one model for R-012 native Hermes tool-call admission.

Offline scoring uses session stats from ~/.hermes/state.db after a live probe.
Does not claim savings_percent. Exit 0 only when admitted=true.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/tmp/aegis-r012-measure")
MARKER = "R012-MARKER-7c3e91"
PROMPT = (
    f"Read the file {ROOT}/marker.txt. "
    "Reply with only the exact file contents and nothing else."
)
HERMES = Path.home() / ".local" / "bin" / "hermes"
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"


def main() -> int:
    parser = argparse.ArgumentParser(description="R-012 model admission screen")
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="nous")
    parser.add_argument("--context-length", type=int, default=128000)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "marker.txt").write_text(MARKER + "\n", encoding="utf-8")
    usage_path = ROOT / f"screen-{args.model.replace('/', '_')}.json"

    cmd = [
        str(HERMES),
        "-z",
        PROMPT,
        "--usage-file",
        str(usage_path),
        "-t",
        "file",
        "--ignore-rules",
        "--reasoning",
        "none",
        "-m",
        args.model,
        "--provider",
        args.provider,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
    stdout = (proc.stdout or "").strip()
    usage = {}
    if usage_path.is_file():
        try:
            usage = json.loads(usage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            usage = {"parse_error": True}

    sys.path.insert(0, str(HERE))
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from r012_admission_gate import admit_run, load_session_stats

    session_id = str(usage.get("session_id") or "")
    stats = load_session_stats(session_id)
    admission = admit_run(
        mode="control",
        stdout=stdout,
        usage=usage,
        context_length=args.context_length,
        metadata_advertises_tools=True,
        hermes_accepted=proc.returncode != 2,
        session_id=session_id,
    )
    body = {
        "model": args.model,
        "provider": args.provider,
        "exit_code": proc.returncode,
        "stdout_tail": stdout[-500:],
        "usage": usage,
        "session_stats": stats,
        "admission": admission,
        "savings_percent": None,
    }
    text = json.dumps(body, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if admission.get("admitted") else 2


if __name__ == "__main__":
    raise SystemExit(main())
