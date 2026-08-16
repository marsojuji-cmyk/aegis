"""Build ~/.aegis/hermes_index/files.json for the Hermes workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aegis.hermes_index import DEFAULT_ROOT, build_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Index a Hermes workspace through AEGIS")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--dest", default="")
    args = parser.parse_args()
    dest = Path(args.dest) if args.dest else None
    payload = build_index(args.root, dest=dest)
    print(
        json.dumps(
            {
                "root": payload.get("root"),
                "file_count": payload.get("file_count"),
                "dir_count": payload.get("dir_count"),
                "reads_allowed": payload.get("reads_allowed"),
                "reads_denied": payload.get("reads_denied"),
                "write_decision": payload.get("write_decision"),
                "write_executed": payload.get("write_executed"),
                "dest": str(dest) if dest else str(Path.home() / ".aegis" / "hermes_index" / "files.json"),
            },
            indent=2,
        )
    )
    return 0 if payload.get("write_executed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
