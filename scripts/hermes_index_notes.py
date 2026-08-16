"""Build notes/graph/projects JSON under ~/.aegis/hermes_index/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aegis.hermes_index import DEFAULT_ROOT  # noqa: E402
from aegis.hermes_notes import build_notes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Index Markdown notes through AEGIS")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    args = parser.parse_args()
    out = build_notes(args.root)
    print(
        json.dumps(
            {
                "root": out.get("notes", {}).get("root"),
                "note_count": out.get("notes", {}).get("note_count"),
                "reads_allowed": out.get("notes", {}).get("reads_allowed"),
                "reads_denied": out.get("notes", {}).get("reads_denied"),
                "edge_count": len(out.get("graph", {}).get("edges") or []),
                "orphan_count": len(out.get("graph", {}).get("orphans") or []),
                "project_count": len(out.get("projects", {}).get("projects") or []),
                "write_decision": out.get("write_decision"),
                "write_executed": out.get("write_executed"),
            },
            indent=2,
        )
    )
    return 0 if out.get("write_executed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
