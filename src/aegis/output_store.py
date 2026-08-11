"""
Output reduce path — shrink final outputs, store content-addressed, reuse.

Closes thought→ship: land stores shrunk body; future identical finals hit cache.
Integrates with ledger (output_store / output_reuse kinds).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aegis.paths import ensure_home, outputs_dir
from aegis.tokens import estimate_tokens

# Filler that bloats "final" agent replies (whole-line or line-prefix)
_FILLER_LINE = re.compile(
    r"^\s*("
    r"sure\b.*|"
    r"happy to\b.*|"
    r"of course\b.*|"
    r"here('s| is)\b.*|"
    r"let me\b.*|"
    r"i('ll| will)\b.*|"
    r"as an ai\b.*|"
    r"hope (this|that)\b.*"
    r")$",
    re.I,
)


def shrink_output(text: str, profile: str = "brief") -> str:
    """Profile-aware shrink — reduce storage + future token re-injection cost."""
    if not text:
        return ""
    prof = (profile or "brief").lower()
    raw = text.replace("\r\n", "\n")

    if prof == "json":
        return _shrink_json(raw)
    if prof == "diff":
        return _shrink_diff(raw)
    return _shrink_brief(raw)


def _shrink_json(text: str) -> str:
    # Extract first JSON object/array if wrapped in prose/fences
    body = text.strip()
    lines = body.splitlines()
    inner: List[str] = []
    in_fence = False
    for ln in lines:
        st = ln.strip()
        if st.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            inner.append(ln)
    if inner:
        body = "\n".join(inner).strip()
    # Try progressively smaller suffixes from first { or [
    start_obj = body.find("{")
    start_arr = body.find("[")
    starts = [s for s in (start_obj, start_arr) if s >= 0]
    if starts:
        i = min(starts)
        chunk = body[i:]
        # trim trailing prose after balanced JSON via raw_decode
        try:
            data, _ = json.JSONDecoder().raw_decode(chunk)
            return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        try:
            data = json.loads(chunk)
            return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return _collapse_ws(body)


def _shrink_diff(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    in_diff = False
    for ln in lines:
        s = ln.rstrip()
        if s.startswith(("diff ", "--- ", "+++ ", "@@", "index ")):
            in_diff = True
            out.append(s)
            continue
        if in_diff:
            if s.startswith(("+", "-", " ", "\\")):
                out.append(s)
            elif s == "":
                out.append("")
            elif s.startswith("diff "):
                out.append(s)
            # drop prose after hunks until next diff
            continue
        # before first diff: keep search-replace style blocks
        if s.startswith(("<<<<<<<", "=======", ">>>>>>>", "@@ ")):
            in_diff = True
            out.append(s)
    if not out:
        # no unified diff — treat as brief (still shrink filler)
        return _shrink_brief(text)
    return _collapse_ws("\n".join(out))


def _shrink_brief(text: str) -> str:
    kept: List[str] = []
    for ln in text.splitlines():
        if _FILLER_LINE.match(ln):
            continue
        # strip markdown bold spam wrappers lightly
        s = ln.rstrip()
        if s.strip() in ("---", "***", "```", "```markdown"):
            continue
        kept.append(s)
    return _collapse_ws("\n".join(kept))


def _collapse_ws(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def output_key(
    profile: str,
    body: str,
    *,
    pack_id: Optional[str] = None,
) -> str:
    """Content-addressed key: profile + body hash (+ optional pack_id for binding)."""
    h = hashlib.sha256()
    h.update((profile or "brief").encode("utf-8"))
    h.update(b"\0")
    h.update(body.encode("utf-8"))
    if pack_id:
        h.update(b"\0")
        h.update(pack_id.encode("utf-8"))
    return h.hexdigest()[:24]


def _entry_path(out_id: str) -> Path:
    return outputs_dir() / f"{out_id}.json"


def _index_path() -> Path:
    return outputs_dir() / "index.jsonl"


def load_output(out_id: str) -> Optional[Dict[str, Any]]:
    path = _entry_path(out_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_by_key(key: str) -> Optional[Dict[str, Any]]:
    """Scan index for key (newest wins)."""
    path = _index_path()
    if not path.is_file():
        return None
    hit = None
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("key") == key:
                hit = row
    if not hit:
        return None
    return load_output(hit["id"])


def store_shrunk(
    *,
    body: str,
    profile: str = "brief",
    pack_id: Optional[str] = None,
    summary: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Shrink body, store if new, or reuse existing.
    Returns store receipt with reuse flag and token deltas.
    """
    from aegis.ledger import record

    prof = (profile or "brief").lower()
    raw_tokens = estimate_tokens(body)
    shrunk = shrink_output(body, prof)
    shrunk_tokens = estimate_tokens(shrunk)
    key = output_key(prof, body, pack_id=None)  # content-only for cross-pack reuse
    key_bound = output_key(prof, body, pack_id=pack_id) if pack_id else key

    existing = find_by_key(key)
    if existing and existing.get("shrunk_text") == shrunk:
        # pure reuse — no re-write
        if not dry_run:
            entry = record(
                kind="output_reuse",
                task=f"output_reuse:{prof}",
                mode="output",
                raw_out=raw_tokens,
                processed_out=0,  # re-inject cost already paid / avoided
                meta={
                    "output_id": existing["id"],
                    "key": key,
                    "profile": prof,
                    "pack_id": pack_id,
                    "reuse": True,
                    "shrunk_tokens": existing.get("shrunk_tokens"),
                },
            )
        else:
            entry = None
        return {
            "reuse": True,
            "id": existing["id"],
            "key": key,
            "profile": prof,
            "raw_tokens": raw_tokens,
            "shrunk_tokens": int(existing.get("shrunk_tokens") or shrunk_tokens),
            "bytes_raw": len(body.encode("utf-8")),
            "bytes_shrunk": len((existing.get("shrunk_text") or shrunk).encode("utf-8")),
            "tokens_saved": raw_tokens,  # full avoid on reuse of stored final
            "shrunk_text": existing.get("shrunk_text") or shrunk,
            "pack_id": pack_id,
            "ledger_id": (entry or {}).get("id"),
            "summary": summary or existing.get("summary"),
            "token_accounting": "output_reduce_reuse",
        }

    out_id = f"out_{key[:16]}"
    entry_doc = {
        "id": out_id,
        "key": key,
        "key_bound": key_bound,
        "profile": prof,
        "pack_id": pack_id,
        "raw_tokens": raw_tokens,
        "shrunk_tokens": shrunk_tokens,
        "bytes_raw": len(body.encode("utf-8")),
        "bytes_shrunk": len(shrunk.encode("utf-8")),
        "tokens_saved": max(0, raw_tokens - shrunk_tokens),
        "shrunk_text": shrunk,
        "summary": summary[:500],
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "token_accounting": "output_reduce_store",
    }
    ledger_id = None
    if not dry_run:
        ensure_home()
        _entry_path(out_id).write_text(
            json.dumps(entry_doc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with _index_path().open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "id": out_id,
                        "key": key,
                        "profile": prof,
                        "shrunk_tokens": shrunk_tokens,
                        "ts": entry_doc["ts"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        entry = record(
            kind="output_store",
            task=f"output_store:{prof}",
            mode="output",
            raw_out=raw_tokens,
            processed_out=shrunk_tokens,
            meta={
                "output_id": out_id,
                "key": key,
                "profile": prof,
                "pack_id": pack_id,
                "bytes_raw": entry_doc["bytes_raw"],
                "bytes_shrunk": entry_doc["bytes_shrunk"],
                "reuse": False,
            },
        )
        ledger_id = entry["id"]

    entry_doc["reuse"] = False
    entry_doc["ledger_id"] = ledger_id
    return entry_doc


def store_stats() -> Dict[str, Any]:
    """Aggregate store metrics for budget/doctor."""
    d = outputs_dir()
    if not d.is_dir():
        return {
            "entries": 0,
            "bytes_raw": 0,
            "bytes_shrunk": 0,
            "tokens_raw": 0,
            "tokens_shrunk": 0,
        }
    entries = 0
    br = bs = tr = ts = 0
    for p in d.glob("out_*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries += 1
        br += int(doc.get("bytes_raw") or 0)
        bs += int(doc.get("bytes_shrunk") or 0)
        tr += int(doc.get("raw_tokens") or 0)
        ts += int(doc.get("shrunk_tokens") or 0)
    return {
        "entries": entries,
        "bytes_raw": br,
        "bytes_shrunk": bs,
        "bytes_saved": max(0, br - bs),
        "tokens_raw": tr,
        "tokens_shrunk": ts,
        "tokens_saved": max(0, tr - ts),
    }
