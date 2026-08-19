"""Repair Hermes session rows poisoned by dict tool results.

When aegis-gate returned deny payloads as dicts, Hermes persisted them as
``\\x00json:{...}``. On replay, ``_decode_content`` yields a dict, but chat
APIs require tool ``content`` to be a string → HTTP 400
``messages.N.content: Invalid input``.

Rewrites affected tool rows to plain JSON strings (no ``\\x00json:`` prefix).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERMES_STATE = Path.home() / ".hermes" / "state.db"
PREFIX = "\x00json:"


def repair_db(path: Path = HERMES_STATE, *, dry_run: bool = False) -> int:
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "state.db not found", "path": str(path)}))
        return 2

    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT id, session_id, role, content FROM messages WHERE role = 'tool'"
    ).fetchall()

    fixed = 0
    for row_id, session_id, role, content in rows:
        if not isinstance(content, str) or not content.startswith(PREFIX):
            continue
        try:
            parsed = json.loads(content[len(PREFIX) :])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        new_content = json.dumps(parsed)
        if new_content == content:
            continue
        fixed += 1
        if not dry_run:
            conn.execute(
                "UPDATE messages SET content = ? WHERE id = ?",
                (new_content, row_id),
            )
        print(f"{'would fix' if dry_run else 'fixed'} id={row_id} session={session_id}")

    if not dry_run and fixed:
        conn.commit()
    conn.close()
    print(json.dumps({"ok": True, "fixed": fixed, "dry_run": dry_run, "path": str(path)}))
    return 0


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    path = HERMES_STATE
    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            path = Path(arg.split("=", 1)[1])
    return repair_db(path, dry_run=dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
