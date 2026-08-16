"""Query the local Hermes indexes. Read-only. No external search."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aegis.hermes_search import unified_search  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Hermes file/note/project indexes")
    parser.add_argument("query")
    parser.add_argument("--kind", default="", help="file|note|project")
    parser.add_argument("--tag", default="")
    parser.add_argument("--project", default="")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    out = unified_search(
        args.query, kind=args.kind, tag=args.tag, project=args.project, limit=args.limit
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
