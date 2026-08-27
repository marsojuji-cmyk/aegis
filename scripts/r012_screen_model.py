#!/usr/bin/env python3
"""Screen one model for R-012 native Hermes tool-call admission.

Default harness: ``hermes chat -q --max-turns`` (agent loop). Legacy: R012_HARNESS=oneshot.
Offline scoring uses session DB + final assistant text. savings_percent stays null.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
sys.path.insert(0, str(HERE))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from r012_harness import run_probe, score_probe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="R-012 model admission screen")
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="nous")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    import os

    os.environ.setdefault("R012_MODEL", args.model)
    os.environ.setdefault("R012_PROVIDER", args.provider)

    probe_body = run_probe()
    admission = score_probe(probe_body, mode="control")
    body = {
        "model": args.model,
        "provider": args.provider,
        "harness": probe_body.get("harness"),
        "max_turns": probe_body.get("max_turns"),
        "session_id": probe_body.get("session_id"),
        "exit_code": probe_body.get("exit_code"),
        "stdout": probe_body.get("stdout"),
        "cli_stdout_tail": (probe_body.get("cli_stdout") or "")[-500:],
        "usage": probe_body.get("usage"),
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
