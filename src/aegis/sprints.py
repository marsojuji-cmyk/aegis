"""Sprint ledger — track Aegis work without a second source of truth.

Operational SoT: ~/.aegis/sprints.jsonl
Human index: repo 05_SPRINT_BOARD.md (written by `aegis sprint board --write`)
Does not replace 01_CANONICAL_REGISTER.md. Parked items stay parked.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aegis.paths import ensure_home, sprints_path

STATUSES = ("planned", "active", "done", "blocked", "parked")
TASK_STATUSES = ("todo", "doing", "done")
REPO_BOARD = "05_SPRINT_BOARD.md"

# Seeded once. Existing IDs are not overwritten (status/evidence survive).
CATALOG: List[Dict[str, Any]] = [
    {
        "id": "SP-001",
        "title": "Sprint reporting system",
        "goal": "CLI + jsonl ledger + repo board. Track sprints without replacing registers.",
        "status": "planned",
        "kind": "execute",
        "links": {"decisions": ["D-025"], "risks": ["R-013"], "questions": []},
        "tasks": [
            {"id": "T-1", "title": "sprint module + path", "status": "todo", "evidence": ""},
            {"id": "T-2", "title": "CLI seed/list/start/complete/report/board", "status": "todo", "evidence": ""},
            {"id": "T-3", "title": "tests + register index", "status": "todo", "evidence": ""},
        ],
    },
    {
        "id": "SP-002",
        "title": "Align product version strings to 1.1.1",
        "goal": "README, setup.py, and CLI --version match pyproject / __version__. Plugin identity stays 1.0.0.",
        "status": "planned",
        "kind": "execute",
        "links": {"decisions": [], "risks": [], "questions": []},
        "tasks": [
            {"id": "T-1", "title": "setup.py + argparse --version", "status": "todo", "evidence": ""},
            {"id": "T-2", "title": "README + FIRST_RELEASE note", "status": "todo", "evidence": ""},
        ],
    },
    {
        "id": "SP-003",
        "title": "Thin aegis hermes search|resolve CLI",
        "goal": "FIRST_RELEASE in-scope retrieval on the product CLI. Read-only. No new index/API.",
        "status": "planned",
        "kind": "execute",
        "links": {"decisions": ["D-024", "D-023"], "risks": [], "questions": []},
        "tasks": [
            {"id": "T-1", "title": "hermes search wraps unified_search", "status": "todo", "evidence": ""},
            {"id": "T-2", "title": "hermes resolve wraps resolve_context", "status": "todo", "evidence": ""},
        ],
    },
    {
        "id": "SP-010",
        "title": "R-014 admitted token pair",
        "goal": "One admitted gated/ungated pair. savings_percent stays null until D-015 admits both sides.",
        "status": "parked",
        "kind": "parked",
        "blocked_by": ["D-015", "D-016", "D-019", "Q-012", "R-014"],
        "links": {"decisions": ["D-015", "D-016", "D-019"], "risks": ["R-014"], "questions": ["Q-012"]},
        "tasks": [],
    },
    {
        "id": "SP-011",
        "title": "Q-011 require-review hard block",
        "goal": "When (if ever) high-risk require-review becomes a hard block.",
        "status": "blocked",
        "kind": "blocked",
        "blocked_by": ["D-011", "Q-011"],
        "links": {"decisions": ["D-011"], "risks": [], "questions": ["Q-011"]},
        "tasks": [],
    },
    {
        "id": "SP-012",
        "title": "Q-013 semantic packet encoder",
        "goal": "Encoder only after field contract is explicitly accepted. Not D-025.",
        "status": "parked",
        "kind": "parked",
        "blocked_by": ["Q-013"],
        "links": {"decisions": [], "risks": [], "questions": ["Q-013"]},
        "tasks": [],
    },
    {
        "id": "SP-013",
        "title": "Continuity capsule artifacts pack_id",
        "goal": "Capsules store pack id in artifacts. Parked by FIRST_RELEASE / WP-3.",
        "status": "parked",
        "kind": "parked",
        "blocked_by": ["FIRST_RELEASE", "WP-3"],
        "links": {"decisions": [], "risks": [], "questions": []},
        "tasks": [],
    },
    {
        "id": "SP-014",
        "title": "R-015 memory domain scope",
        "goal": "Hermes memory.write is not domain-scoped. Needs explicit design authorization.",
        "status": "blocked",
        "kind": "blocked",
        "blocked_by": ["R-015", "D-020"],
        "links": {"decisions": ["D-020"], "risks": ["R-015"], "questions": []},
        "tasks": [],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _blank(sprint: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "id": "",
        "title": "",
        "goal": "",
        "status": "planned",
        "kind": "execute",
        "blocked_by": [],
        "links": {"decisions": [], "risks": [], "questions": []},
        "tasks": [],
        "started_ts": None,
        "completed_ts": None,
        "verified": "",
        "evidence": "",
        "created_ts": _now(),
        "updated_ts": _now(),
    }
    row.update(sprint)
    row["blocked_by"] = list(row.get("blocked_by") or [])
    links = row.get("links") or {}
    row["links"] = {
        "decisions": list(links.get("decisions") or []),
        "risks": list(links.get("risks") or []),
        "questions": list(links.get("questions") or []),
    }
    tasks = []
    for task in row.get("tasks") or []:
        tasks.append(
            {
                "id": str(task.get("id") or ""),
                "title": str(task.get("title") or ""),
                "status": task.get("status") if task.get("status") in TASK_STATUSES else "todo",
                "evidence": str(task.get("evidence") or ""),
            }
        )
    row["tasks"] = tasks
    if row["status"] not in STATUSES:
        row["status"] = "planned"
    return row


def _read() -> List[Dict[str, Any]]:
    path = sprints_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict) and raw.get("id"):
                rows.append(_blank(raw))
    return rows


def _write_all(rows: List[Dict[str, Any]]) -> None:
    ensure_home()
    with sprints_path().open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _by_id(sid: str) -> Optional[Dict[str, Any]]:
    needle = (sid or "").strip()
    for row in _read():
        if row["id"] == needle:
            return row
    return None


def _upsert(row: Dict[str, Any]) -> Dict[str, Any]:
    row = _blank(row)
    row["updated_ts"] = _now()
    rows = _read()
    found = False
    for idx, existing in enumerate(rows):
        if existing["id"] == row["id"]:
            rows[idx] = row
            found = True
            break
    if not found:
        rows.append(row)
    _write_all(rows)
    return row


def _next_id(rows: Optional[List[Dict[str, Any]]] = None) -> str:
    n = 0
    for row in rows if rows is not None else _read():
        match = re.fullmatch(r"SP-(\d+)", str(row.get("id") or ""))
        if match:
            n = max(n, int(match.group(1)))
    return f"SP-{n + 1:03d}"


def seed_board(*, force: bool = False) -> Dict[str, Any]:
    """Insert catalog rows. Existing IDs keep their live status unless force."""
    rows = _read()
    have = {row["id"] for row in rows}
    created: List[str] = []
    refreshed: List[str] = []
    for item in CATALOG:
        row = _blank(item)
        if row["id"] in have and not force:
            continue
        if row["id"] in have and force:
            live = next(r for r in rows if r["id"] == row["id"])
            row["started_ts"] = live.get("started_ts")
            row["completed_ts"] = live.get("completed_ts")
            row["verified"] = live.get("verified") or ""
            row["evidence"] = live.get("evidence") or ""
            row["status"] = live.get("status") or row["status"]
            row["created_ts"] = live.get("created_ts") or row["created_ts"]
            _upsert(row)
            refreshed.append(row["id"])
            continue
        _upsert(row)
        created.append(row["id"])
    return {"ok": True, "created": created, "refreshed": refreshed, "total": len(_read())}


def add_sprint(
    title: str,
    *,
    goal: str = "",
    status: str = "planned",
    kind: str = "execute",
    blocked_by: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    row = _blank(
        {
            "id": _next_id(),
            "title": title.strip(),
            "goal": goal.strip(),
            "status": status,
            "kind": kind,
            "blocked_by": blocked_by or [],
        }
    )
    return _upsert(row)


def list_sprints(status: str = "") -> List[Dict[str, Any]]:
    rows = _read()
    if status:
        rows = [row for row in rows if row.get("status") == status]
    order = {name: idx for idx, name in enumerate(("active", "planned", "blocked", "parked", "done"))}
    rows.sort(key=lambda row: (order.get(str(row.get("status")), 9), str(row.get("id"))))
    return rows


def get_sprint(sid: str) -> Optional[Dict[str, Any]]:
    return _by_id(sid)


def start_sprint(sid: str) -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    if row["status"] in {"blocked", "parked"}:
        return {"ok": False, "error": f"{row['id']} is {row['status']}", "sprint": row}
    if row["status"] == "done":
        return {"ok": False, "error": f"{row['id']} already done", "sprint": row}
    row["status"] = "active"
    row["started_ts"] = row.get("started_ts") or _now()
    return {"ok": True, "sprint": _upsert(row)}


def complete_sprint(sid: str, *, verified: str, evidence: str = "") -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    if row["status"] in {"blocked", "parked"}:
        return {"ok": False, "error": f"{row['id']} is {row['status']}; will not complete", "sprint": row}
    note = (verified or "").strip()
    if not note:
        return {"ok": False, "error": "verified is required"}
    for task in row["tasks"]:
        task["status"] = "done"
    row["status"] = "done"
    row["verified"] = note
    row["evidence"] = (evidence or "").strip()
    row["completed_ts"] = _now()
    if not row.get("started_ts"):
        row["started_ts"] = row["completed_ts"]
    return {"ok": True, "sprint": _upsert(row)}


def block_sprint(sid: str, *, reason: str, blocked_by: Optional[List[str]] = None) -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    if row["status"] == "done":
        return {"ok": False, "error": f"{row['id']} already done", "sprint": row}
    row["status"] = "blocked"
    row["kind"] = "blocked"
    if reason:
        row["evidence"] = reason.strip()
    if blocked_by:
        extra = [item.strip() for item in blocked_by if item and item.strip()]
        row["blocked_by"] = list(dict.fromkeys(list(row.get("blocked_by") or []) + extra))
    return {"ok": True, "sprint": _upsert(row)}


def unpark_sprint(sid: str, *, reason: str = "") -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    if row["status"] == "done":
        return {"ok": False, "error": f"{row['id']} already done", "sprint": row}
    row["status"] = "planned"
    row["kind"] = "execute"
    if reason:
        row["evidence"] = reason.strip()
    return {"ok": True, "sprint": _upsert(row)}


def park_sprint(sid: str, *, reason: str = "") -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    if row["status"] == "done":
        return {"ok": False, "error": f"{row['id']} already done", "sprint": row}
    row["status"] = "parked"
    row["kind"] = "parked"
    if reason:
        row["evidence"] = reason.strip()
    return {"ok": True, "sprint": _upsert(row)}


def add_task(sid: str, title: str) -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    n = 0
    for task in row["tasks"]:
        match = re.fullmatch(r"T-(\d+)", str(task.get("id") or ""))
        if match:
            n = max(n, int(match.group(1)))
    task = {"id": f"T-{n + 1}", "title": title.strip(), "status": "todo", "evidence": ""}
    row["tasks"].append(task)
    return {"ok": True, "task": task, "sprint": _upsert(row)}


def complete_task(sid: str, task_id: str, *, evidence: str = "") -> Dict[str, Any]:
    row = _by_id(sid)
    if row is None:
        return {"ok": False, "error": f"unknown sprint {sid}"}
    for task in row["tasks"]:
        if task["id"] == task_id:
            task["status"] = "done"
            if evidence:
                task["evidence"] = evidence.strip()
            return {"ok": True, "task": task, "sprint": _upsert(row)}
    return {"ok": False, "error": f"unknown task {task_id}"}


def _register_snapshot(repo: Path) -> Dict[str, Any]:
    path = repo / "01_CANONICAL_REGISTER.md"
    snap: Dict[str, Any] = {"path": str(path), "decisions": [], "risks": [], "questions": []}
    if not path.is_file():
        return snap
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Decisions"):
            section = "decisions"
            continue
        if line.startswith("## Risks"):
            section = "risks"
            continue
        if line.startswith("## Questions"):
            section = "questions"
            continue
        if line.startswith("## "):
            section = ""
            continue
        if not section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in {"ID", "---"} or cells[0].startswith("---"):
            continue
        snap[section].append({"id": cells[0], "status": cells[1], "summary": cells[2]})
    return snap


def report(*, repo: Optional[Path] = None) -> Dict[str, Any]:
    from aegis import __version__

    rows = list_sprints()
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[str(row.get("status"))] = counts.get(str(row.get("status")), 0) + 1
    root = repo or Path.cwd()
    return {
        "version": __version__,
        "generated_ts": _now(),
        "counts": counts,
        "active": [row for row in rows if row["status"] == "active"],
        "planned": [row for row in rows if row["status"] == "planned"],
        "blocked": [row for row in rows if row["status"] == "blocked"],
        "parked": [row for row in rows if row["status"] == "parked"],
        "done": [row for row in rows if row["status"] == "done"],
        "sprints": rows,
        "register": _register_snapshot(root),
    }


def render_board(rows: Optional[List[Dict[str, Any]]] = None) -> str:
    from aegis import __version__

    items = rows if rows is not None else list_sprints()
    lines = [
        "# Sprint Board",
        "",
        f"Product `{__version__}`. Operational SoT: `~/.aegis/sprints.jsonl`.",
        "This file is the human index. Registers remain authoritative for D/R/Q.",
        "",
        "| ID | Status | Title | Blocked by | Links |",
        "|---|---|---|---|---|",
    ]
    for row in items:
        links = row.get("links") or {}
        link_ids = (
            list(links.get("decisions") or [])
            + list(links.get("risks") or [])
            + list(links.get("questions") or [])
        )
        blocked = ", ".join(row.get("blocked_by") or []) or "—"
        lines.append(
            f"| {row['id']} | {row['status']} | {row['title']} | {blocked} | "
            f"{', '.join(link_ids) or '—'} |"
        )
    lines.extend(["", "## Detail", ""])
    for row in items:
        lines.append(f"### {row['id']} — {row['title']}")
        lines.append("")
        lines.append(f"- status: `{row['status']}`")
        if row.get("goal"):
            lines.append(f"- goal: {row['goal']}")
        if row.get("blocked_by"):
            lines.append(f"- blocked_by: {', '.join(row['blocked_by'])}")
        if row.get("verified"):
            lines.append(f"- verified: {row['verified']}")
        if row.get("evidence"):
            lines.append(f"- evidence: {row['evidence']}")
        for task in row.get("tasks") or []:
            lines.append(f"- {task['id']} [{task['status']}]: {task['title']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_board(path: Optional[Path] = None) -> Path:
    dest = Path(path) if path else Path.cwd() / REPO_BOARD
    dest.write_text(render_board(), encoding="utf-8")
    return dest


def format_report_text(payload: Dict[str, Any]) -> str:
    counts = payload.get("counts") or {}
    lines = [
        f"Aegis sprint report  v{payload.get('version')}",
        f"  generated: {payload.get('generated_ts')}",
        "  counts: "
        + " ".join(f"{name}={counts.get(name, 0)}" for name in STATUSES),
        "",
    ]
    for label in ("active", "planned", "blocked", "parked", "done"):
        rows = payload.get(label) or []
        if not rows:
            continue
        lines.append(f"{label}:")
        for row in rows:
            extra = ""
            if row.get("blocked_by"):
                extra = f"  blocked_by={','.join(row['blocked_by'])}"
            lines.append(f"  {row['id']}  {row['title']}{extra}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
