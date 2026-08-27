"""Durable memory admission — provenance-bearing records (MUL schema)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from aegis.paths import continuity_events_path, ensure_home, memory_records_path

_LOCK = threading.RLock()

MEMORY_TYPES = frozenset({"episodic", "semantic", "procedural", "preference"})
EVIDENCE_STATUSES = frozenset({"observed", "verified", "inferred", "proposed", "unknown"})
PRIVACY_CLASSES = frozenset({"public", "internal", "private", "sensitive", "restricted"})
SOURCE_TYPES = frozenset({
    "direct_observation", "user_statement", "document", "tool_result", "model_inference",
})
EMOTION_KEYS = (
    "valence", "arousal", "curiosity", "trust", "uncertainty",
    "salience", "agency", "attachment", "fatigue", "cognitive_load",
)
MAX_CONTENT_LEN = 4000
MAX_ENTRIES = 5000


def schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "memory_record.schema.json"


def neutral_emotion(**overrides: float) -> Dict[str, float]:
    base = {
        "valence": 0.0,
        "arousal": 0.0,
        "curiosity": 0.0,
        "trust": 0.5,
        "uncertainty": 0.5,
        "salience": 0.0,
        "agency": 0.5,
        "attachment": 0.0,
        "fatigue": 0.0,
        "cognitive_load": 0.0,
    }
    for k, v in overrides.items():
        if k in base:
            base[k] = float(v)
    return base


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _in_range(val: Any, lo: float, hi: float) -> bool:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return lo <= f <= hi


def validate_record(record: Mapping[str, Any]) -> Tuple[bool, List[str]]:
    """Lightweight validator (no jsonschema dependency)."""
    errors: List[str] = []
    required = (
        "id", "memory_type", "content", "provenance", "confidence",
        "evidence_status", "emotion", "privacy_class", "observed_at",
        "recorded_at", "deletion_path", "conflicts_with",
    )
    for key in required:
        if key not in record:
            errors.append(f"missing required field: {key}")

    if record.get("memory_type") not in MEMORY_TYPES:
        errors.append("memory_type invalid")
    content = str(record.get("content") or "")
    if not content.strip():
        errors.append("content empty")
    elif len(content) > MAX_CONTENT_LEN:
        errors.append(f"content exceeds {MAX_CONTENT_LEN} chars")

    prov = record.get("provenance")
    if not isinstance(prov, dict):
        errors.append("provenance must be object")
    else:
        for pk in ("source_type", "source_id", "captured_by"):
            if not str(prov.get(pk) or "").strip():
                errors.append(f"provenance.{pk} required")
        if prov.get("source_type") not in SOURCE_TYPES:
            errors.append("provenance.source_type invalid")

    if not _in_range(record.get("confidence"), 0.0, 1.0):
        errors.append("confidence must be 0..1")

    est = record.get("evidence_status")
    if est not in EVIDENCE_STATUSES:
        errors.append("evidence_status invalid")
    if record.get("memory_type") == "preference" and est in {"inferred", "unknown", "proposed"}:
        errors.append("preference requires observed or verified evidence_status")

    emotion = record.get("emotion")
    if not isinstance(emotion, dict):
        errors.append("emotion must be object")
    else:
        for ek in EMOTION_KEYS:
            if ek not in emotion:
                errors.append(f"emotion.{ek} required")
        if "valence" in emotion and not _in_range(emotion["valence"], -1.0, 1.0):
            errors.append("emotion.valence out of range")
        for ek in EMOTION_KEYS:
            if ek == "valence":
                continue
            if ek in emotion and not _in_range(emotion[ek], 0.0, 1.0):
                errors.append(f"emotion.{ek} out of range")

    if record.get("privacy_class") not in PRIVACY_CLASSES:
        errors.append("privacy_class invalid")
    if not str(record.get("deletion_path") or "").strip():
        errors.append("deletion_path required")

    conflicts = record.get("conflicts_with")
    if not isinstance(conflicts, list):
        errors.append("conflicts_with must be array")
    elif any(not str(x).strip() for x in conflicts):
        errors.append("conflicts_with entries must be non-empty strings")

    return len(errors) == 0, errors


def _read_all() -> List[Dict[str, Any]]:
    path = memory_records_path()
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
                    if isinstance(row, dict) and row.get("id"):
                        rows.append(row)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _atomic_write(rows: List[Dict[str, Any]]) -> None:
    ensure_home()
    path = memory_records_path()
    tmp = path.with_suffix(".jsonl.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except OSError:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_event(event: Dict[str, Any]) -> None:
    ensure_home()
    with continuity_events_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _prune(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(rows) <= MAX_ENTRIES:
        return rows
    ranked = sorted(rows, key=lambda r: str(r.get("recorded_at") or ""), reverse=True)
    return ranked[:MAX_ENTRIES]


def admit(record: Mapping[str, Any], *, replace: bool = False) -> Dict[str, Any]:
    """Validate and append a durable memory record. Fails closed on invalid input."""
    row = dict(record)
    if not str(row.get("id") or "").strip():
        row["id"] = f"mem_{uuid.uuid4().hex[:12]}"
    if not str(row.get("recorded_at") or "").strip():
        row["recorded_at"] = _now()
    if not str(row.get("observed_at") or "").strip():
        row["observed_at"] = row["recorded_at"]
    if "conflicts_with" not in row:
        row["conflicts_with"] = []
    if not isinstance(row.get("emotion"), dict):
        row["emotion"] = neutral_emotion()

    ok, errors = validate_record(row)
    if not ok:
        raise ValueError("; ".join(errors))

    with _LOCK:
        rows = _read_all()
        existing_ids = {str(r.get("id")) for r in rows}
        if str(row["id"]) in existing_ids and not replace:
            raise ValueError(f"record id already exists: {row['id']}")
        if replace:
            rows = [r for r in rows if str(r.get("id")) != str(row["id"])]
        rows.append(row)
        rows = _prune(rows)
        _atomic_write(rows)

    _append_event({
        "kind": "memory_admit",
        "id": row["id"],
        "memory_type": row["memory_type"],
        "privacy_class": row["privacy_class"],
        "evidence_status": row["evidence_status"],
        "ts": _now(),
    })
    return row


def propose(
    content: str,
    *,
    memory_type: str = "semantic",
    source_id: str = "",
    captured_by: str = "aegis",
    project_hint: str = "",
) -> Dict[str, Any]:
    """Create a proposed record (M-011 capture). Does not auto-promote to verified."""
    sid = source_id or f"run:{project_hint or 'aegis'}"
    record = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "memory_type": memory_type,
        "content": content[:MAX_CONTENT_LEN],
        "provenance": {
            "source_type": "tool_result",
            "source_id": sid[:200],
            "captured_by": captured_by[:64],
        },
        "confidence": 0.3,
        "evidence_status": "proposed",
        "emotion": neutral_emotion(salience=0.2),
        "privacy_class": "internal",
        "observed_at": _now(),
        "recorded_at": _now(),
        "deletion_path": "aegis memory delete --id <id>",
        "conflicts_with": [],
    }
    return admit(record)


def list_records(
    *,
    memory_type: Optional[str] = None,
    privacy_class: Optional[str] = None,
    evidence_status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 200))
    with _LOCK:
        rows = _read_all()
    if memory_type:
        rows = [r for r in rows if r.get("memory_type") == memory_type]
    if privacy_class:
        rows = [r for r in rows if r.get("privacy_class") == privacy_class]
    if evidence_status:
        rows = [r for r in rows if r.get("evidence_status") == evidence_status]
    rows.sort(key=lambda r: str(r.get("recorded_at") or ""), reverse=True)
    return rows[:limit]


def add_conflict(record_id: str, contradicts_id: str, *, reason: str = "") -> Dict[str, Any]:
    """Link two records without mutating either's content."""
    rid = str(record_id or "").strip()
    cid = str(contradicts_id or "").strip()
    if not rid or not cid:
        raise ValueError("record_id and contradicts_id required")
    with _LOCK:
        rows = _read_all()
        target = None
        other = None
        for r in rows:
            if str(r.get("id")) == rid:
                target = r
            if str(r.get("id")) == cid:
                other = r
        if target is None:
            raise ValueError(f"record not found: {rid}")
        if other is None:
            raise ValueError(f"record not found: {cid}")
        conflicts = list(target.get("conflicts_with") or [])
        if cid not in conflicts:
            conflicts.append(cid)
        target = dict(target)
        target["conflicts_with"] = conflicts
        if reason:
            target["conflict_reason"] = str(reason)[:500]
        updated = []
        for r in rows:
            updated.append(target if str(r.get("id")) == rid else r)
        _atomic_write(updated)
    _append_event({
        "kind": "memory_conflict",
        "id": rid,
        "contradicts": cid,
        "reason": str(reason)[:200],
        "ts": _now(),
    })
    return target


def delete_record(record_id: str, *, deletion_path: str = "") -> Dict[str, Any]:
    rid = str(record_id or "").strip()
    if not rid:
        raise ValueError("record_id required")
    with _LOCK:
        rows = _read_all()
        kept = [r for r in rows if str(r.get("id")) != rid]
        if len(kept) == len(rows):
            raise ValueError(f"record not found: {rid}")
        _atomic_write(kept)
    _append_event({
        "kind": "memory_delete",
        "id": rid,
        "deletion_path": deletion_path or "cli",
        "ts": _now(),
    })
    return {"deleted": rid, "remaining": len(kept)}


def search_durable(query: str = "", *, limit: int = 8) -> List[Dict[str, Any]]:
    """Lexical search over admitted records for inject (M-012)."""
    q = (query or "").strip().lower()
    rows = list_records(limit=200)
    if not q:
        return rows[:limit]
    scored: List[tuple] = []
    for r in rows:
        if r.get("evidence_status") == "proposed":
            continue
        text = (str(r.get("content") or "") + " " + str(r.get("id") or "")).lower()
        if q in text:
            scored.append((1, str(r.get("recorded_at") or ""), r))
        else:
            toks = [t for t in q.split() if len(t) > 2]
            hit = sum(1 for t in toks if t in text)
            if hit:
                scored.append((hit, str(r.get("recorded_at") or ""), r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _s, _t, r in scored[: max(1, min(limit, 50))]]


def record_stats() -> Dict[str, Any]:
    with _LOCK:
        rows = _read_all()
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    proposed = 0
    for r in rows:
        mt = str(r.get("memory_type") or "unknown")
        by_type[mt] = by_type.get(mt, 0) + 1
        es = str(r.get("evidence_status") or "unknown")
        by_status[es] = by_status.get(es, 0) + 1
        if es == "proposed":
            proposed += 1
    return {
        "entries": len(rows),
        "proposed": proposed,
        "by_type": by_type,
        "by_status": by_status,
        "path": str(memory_records_path()),
        "schema": str(schema_path()),
        "max_entries": MAX_ENTRIES,
    }
