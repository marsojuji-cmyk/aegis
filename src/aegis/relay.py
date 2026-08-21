"""Observability relay — read guard, continuity, ledger, and outcome logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from aegis.guard import GUARD_LOG_PATH
from aegis.paths import continuity_events_path, ensure_home, ledger_path, outcomes_path

SOURCES = ("guard", "continuity", "ledger", "outcomes", "all")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_jsonl(path: Path, *, limit: int = 50) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return list(reversed(rows[-max(1, limit) :]))


def _source_path(source: str) -> Optional[Path]:
    if source == "guard":
        return GUARD_LOG_PATH
    if source == "continuity":
        return continuity_events_path()
    if source == "ledger":
        return ledger_path()
    if source == "outcomes":
        return outcomes_path()
    return None


def append_continuity_event(event: Mapping[str, Any]) -> None:
    """Append a continuity-side observability row."""
    ensure_home()
    row = dict(event)
    row.setdefault("ts", _now())
    with continuity_events_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def tail(source: str = "all", *, limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    src = (source or "all").strip().lower()
    if src not in SOURCES:
        raise ValueError(f"unknown source: {source}")
    if src == "all":
        out: List[Dict[str, Any]] = []
        for name in ("guard", "continuity", "ledger", "outcomes"):
            for row in tail(name, limit=limit):
                tagged = dict(row)
                tagged["_source"] = name
                out.append(tagged)
        out.sort(key=lambda r: str(r.get("timestamp_iso") or r.get("ts") or r.get("timestamp") or ""))
        return out[-limit:]
    path = _source_path(src)
    if path is None:
        return []
    rows = _read_jsonl(path, limit=limit)
    for row in rows:
        row["_source"] = src
    return rows


def query(
    *,
    source: str = "all",
    kind: str = "",
    request_id: str = "",
    since: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    rows = tail(source, limit=500)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if kind and str(row.get("kind") or row.get("rule") or "") != kind:
            continue
        if request_id:
            rid = str(row.get("request_id") or row.get("trace_id") or "")
            if request_id not in rid and rid != request_id:
                continue
        if since:
            ts = str(row.get("ts") or row.get("timestamp_iso") or row.get("timestamp") or "")
            if ts < since:
                continue
        out.append(row)
        if len(out) >= max(1, min(limit, 500)):
            break
    return out


def correlate(request_id: str) -> Dict[str, Any]:
    rid = (request_id or "").strip()
    if not rid:
        raise ValueError("request_id required")
    result: Dict[str, Any] = {"request_id": rid, "guard": [], "continuity": [], "ledger": [], "outcomes": []}
    for src in ("guard", "continuity", "ledger", "outcomes"):
        for row in query(source=src, request_id=rid, limit=100):
            result[src].append(row)
    result["count"] = sum(len(result[k]) for k in ("guard", "continuity", "ledger", "outcomes"))
    return result


def export_redacted(path: Path, *, source: str = "all", limit: int = 200) -> int:
    """Write redacted relay export; returns row count."""
    rows = tail(source, limit=limit)
    safe: List[Dict[str, Any]] = []
    for row in rows:
        item = {k: v for k, v in row.items() if k not in {"raw_prompt", "provider_payload"}}
        for key in ("input_excerpt", "output_excerpt", "content"):
            if key in item and isinstance(item[key], str) and len(item[key]) > 500:
                item[key] = item[key][:500] + "…"
        safe.append(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(safe)
