"""
Cross-model memory — ephemeral KV cache any provider run can read/write.

Durable provenance records live in memory_records.jsonl via memory_admit.
Stored under ~/.aegis/memory.jsonl.

Production-hardened:
  - threading lock + atomic rewrite
  - key/value length caps
  - max store size with recency/hits prune
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aegis.paths import ensure_home, memory_path

_LOCK = threading.RLock()
MAX_KEY_LEN = 160
MAX_VALUE_LEN = 2000
MAX_ENTRIES = 2000


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_all() -> List[Dict[str, Any]]:
    path = memory_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and row.get("key"):
                        rows.append(row)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _atomic_write(rows: List[Dict[str, Any]]) -> None:
    ensure_home()
    path = memory_path()
    tmp = path.with_suffix(".jsonl.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except OSError:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        # fallback non-atomic
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _prune(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(rows) <= MAX_ENTRIES:
        return rows
    # keep highest hits, then newest
    ranked = sorted(
        rows,
        key=lambda r: (int(r.get("hits") or 0), str(r.get("ts") or "")),
        reverse=True,
    )
    return ranked[:MAX_ENTRIES]


def remember(
    key: str,
    value: str,
    *,
    project: str = "aegis",
    source_model: str = "",
    source_provider: str = "",
    tags: Optional[List[str]] = None,
    weight: float = 1.0,
) -> Dict[str, Any]:
    """Upsert an ephemeral memory fact (last write wins per key+project)."""
    key = (key or "").strip()[:MAX_KEY_LEN]
    if not key:
        raise ValueError("memory key required")
    value = (value or "")[:MAX_VALUE_LEN]
    project = (project or "aegis").strip()[:64] or "aegis"
    try:
        w = float(weight)
    except (TypeError, ValueError):
        w = 1.0
    w = max(0.0, min(w, 100.0))

    with _LOCK:
        rows = _read_all()
        entry = {
            "id": f"mem_{uuid.uuid4().hex[:10]}",
            "key": key,
            "value": value,
            "project": project,
            "source_model": str(source_model or "")[:64],
            "source_provider": str(source_provider or "")[:64],
            "tags": [str(t)[:32] for t in (tags or [])][:12],
            "weight": w,
            "ts": _now(),
            "hits": 0,
        }
        replaced = False
        for i, row in enumerate(rows):
            if row.get("key") == key and row.get("project") == project:
                entry["id"] = row.get("id") or entry["id"]
                entry["hits"] = int(row.get("hits") or 0)
                rows[i] = entry
                replaced = True
                break
        if not replaced:
            rows.append(entry)
        rows = _prune(rows)
        _atomic_write(rows)
        return entry


def recall(
    query: str = "",
    *,
    project: Optional[str] = None,
    limit: int = 12,
    key_prefix: str = "",
    bump_hits: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retrieve memories. Ranking: exact key > substring > token overlap + weight.
    """
    limit = max(1, min(int(limit or 12), 50))
    q = (query or "").strip().lower()[:200]
    key_prefix = (key_prefix or "")[:MAX_KEY_LEN]

    with _LOCK:
        rows = _read_all()
        if project:
            rows = [
                r
                for r in rows
                if r.get("project") == project
                or r.get("project") in ("aegis", "global")
            ]
        if key_prefix:
            rows = [
                r for r in rows if str(r.get("key") or "").startswith(key_prefix)
            ]

        scored: List[tuple] = []
        for r in rows:
            key = str(r.get("key") or "")
            val = str(r.get("value") or "")
            try:
                score = float(r.get("weight") or 1.0)
            except (TypeError, ValueError):
                score = 1.0
            if q:
                kl, vl = key.lower(), val.lower()
                if kl == q or key == query:
                    score += 50
                elif q in kl:
                    score += 20
                elif q in vl:
                    score += 10
                else:
                    toks = [t for t in q.split() if len(t) > 2][:12]
                    score += sum(3 for t in toks if t in kl or t in vl)
                    if score <= float(r.get("weight") or 1.0):
                        continue
            scored.append((score, str(r.get("ts") or ""), r))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out: List[Dict[str, Any]] = []
        for score, _ts, r in scored[:limit]:
            item = dict(r)
            item["score"] = round(score, 2)
            out.append(item)

        if bump_hits and out:
            ids = {x.get("id") for x in out if x.get("id")}
            all_rows = _read_all()
            changed = False
            for i, row in enumerate(all_rows):
                if row.get("id") in ids:
                    all_rows[i] = dict(row)
                    all_rows[i]["hits"] = int(row.get("hits") or 0) + 1
                    changed = True
            if changed:
                _atomic_write(all_rows)
        return out


def memory_context_block(
    task: str = "",
    *,
    project: str = "aegis",
    limit: int = 8,
    include_durable: bool = True,
    include_ephemeral: bool = True,
) -> str:
    """Compact text block for pack/system injection (cross-model mesh)."""
    lines: List[str] = []
    if include_durable:
        try:
            from aegis.memory_admit import search_durable

            durable = search_durable(task, limit=max(1, limit // 2))
            if durable:
                lines.append("[AEGIS MEMORY — durable provenance]")
                for h in durable:
                    mid = str(h.get("id") or "")[:40]
                    content = str(h.get("content") or "")[:200]
                    est = str(h.get("evidence_status") or "")
                    lines.append(f"- {mid} ({est}): {content}")
        except Exception:  # noqa: BLE001
            pass
    if include_ephemeral:
        try:
            hits = recall(task, project=project, limit=limit, bump_hits=True)
        except Exception:  # noqa: BLE001
            hits = []
        if hits:
            lines.append("[AEGIS MEMORY — ephemeral cache]")
            for h in hits:
                k = str(h.get("key") or "")[:80]
                v = str(h.get("value") or "")[:200]
                lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def memory_stats() -> Dict[str, Any]:
    with _LOCK:
        rows = _read_all()
    projects: Dict[str, int] = {}
    for r in rows:
        p = str(r.get("project") or "aegis")
        projects[p] = projects.get(p, 0) + 1
    out = {
        "tier": "ephemeral",
        "entries": len(rows),
        "projects": projects,
        "path": str(memory_path()),
        "max_entries": MAX_ENTRIES,
    }
    try:
        from aegis.memory_admit import record_stats

        out["durable"] = record_stats()
    except Exception:  # noqa: BLE001
        pass
    return out


def auto_capture_from_run(
    *,
    task: str,
    provider: str,
    model: str,
    project: str = "aegis",
    pack_id: Optional[str] = None,
    shrunk: str = "",
    ok: bool = True,
) -> Optional[Dict[str, Any]]:
    """Capture a lightweight fact after a successful router run."""
    if not ok or not task or not str(task).strip():
        return None
    try:
        key = f"run:{(task.strip().lower()[:80])}"
        value = f"last_ok provider={provider} model={model}"
        if pack_id:
            value += f" pack={pack_id}"
        if shrunk:
            value += f" | note={str(shrunk)[:160]}"
        return remember(
            key,
            value,
            project=project or "aegis",
            source_model=str(model or ""),
            source_provider=str(provider or ""),
            tags=["auto", "run"],
            weight=1.0,
        )
    except Exception:  # noqa: BLE001
        return None
