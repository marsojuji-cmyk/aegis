"""Dispatch Hermes note_graph / project_context skills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aegis.hermes_index import DEFAULT_ROOT  # noqa: E402
from aegis.hermes_skills import dispatch, list_skills  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes org skills (note graph, project context)")
    parser.add_argument("skill", nargs="?", default="", help="note_graph | project_context")
    parser.add_argument("--action", default="")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--target", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list or not args.skill:
        print(json.dumps({"skills": list_skills()}, indent=2))
        return 0
    out = dispatch(
        args.skill,
        action=args.action,
        root=args.root,
        target=args.target,
        tag=args.tag,
        name=args.name,
    )
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
