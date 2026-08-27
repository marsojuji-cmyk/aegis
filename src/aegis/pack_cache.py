"""Content-addressed pack reuse — mode map + path-set keys + soft fallbacks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# (resolved path, mtime_ns, size) → sha256. Unchanged files skip a full read.
_FILE_HASH_CACHE: Dict[Tuple[str, int, int], str] = {}
_FILE_HASH_LAST: Dict[str, Tuple[int, int]] = {}

from aegis.paths import ensure_home, packs_dir

# Canonical modes + aliases → boost hit rate without wrong payload families
MODE_ALIASES: Dict[str, str] = {
    "explore": "explore",
    "read": "explore",
    "search": "explore",
    "nav": "explore",
    "scan": "explore",
    "implement": "implement",
    "edit": "implement",
    "fix": "implement",
    "write": "implement",
    "code": "implement",
    "review": "review",
    "diff": "review",
    "pr": "review",
    "audit": "review",
}

# Soft fallbacks: try these cache modes on miss (payload must be safe substitute)
MODE_FALLBACKS: Dict[str, List[str]] = {
    "review": ["explore"],  # sigs-only explore is safe lower bound for review
}


def normalize_mode(mode: str) -> str:
    m = (mode or "explore").strip().lower()
    return MODE_ALIASES.get(m, m if m in ("explore", "implement", "review") else "explore")


def file_hash(path: str) -> str:
    resolved = str(Path(path).resolve())
    st = os.stat(resolved)
    key = (resolved, int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))), int(st.st_size))
    cached = _FILE_HASH_CACHE.get(key)
    if cached is not None:
        return cached
    prev = _FILE_HASH_LAST.get(resolved)
    if prev is not None:
        _FILE_HASH_CACHE.pop((resolved, prev[0], prev[1]), None)
    h = hashlib.sha256()
    with open(resolved, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _FILE_HASH_CACHE[key] = digest
    _FILE_HASH_LAST[resolved] = (key[1], key[2])
    return digest


def path_set_fingerprint(paths: List[str]) -> str:
    """Content-only path-set id (order-independent; path location ignored)."""
    digests = sorted(file_hash(p) for p in paths)
    blob = "|".join(digests).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def pack_key(
    mode: str,
    paths: List[str],
    task: str = "",
    *,
    targets: Optional[Sequence[str]] = None,
    include_task: bool = False,
) -> str:
    """
    Stable key: normalized_mode + path-set content fingerprint + targets.
    Task excluded by default (reuse boost).
    """
    canon = normalize_mode(mode)
    parts = [canon, "ps:" + path_set_fingerprint(paths)]
    tgts = sorted({t.strip() for t in (targets or []) if t and str(t).strip()})
    if tgts:
        parts.append("t:" + ",".join(tgts))
    elif canon == "implement":
        parts.append("t:")  # distinguish no-target implement from explore
    if include_task:
        norm_task = " ".join((task or "").strip().lower().split())
        parts.append("task:" + norm_task)
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


def pack_path(pack_id: str) -> Path:
    return packs_dir() / f"{pack_id}.json"


def load_pack(pack_id: str) -> Optional[Dict[str, Any]]:
    path = pack_path(pack_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_pack(pack_id: str, payload: Dict[str, Any]) -> Path:
    ensure_home()
    path = pack_path(pack_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _index_append(pack_id, payload)
    return path


def get_or_none(
    mode: str,
    paths: List[str],
    task: str = "",
    *,
    targets: Optional[Sequence[str]] = None,
    include_task: bool = False,
    allow_fallback: bool = True,
) -> Tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Returns (pack_id, payload|None, meta).
    meta: {canon_mode, fallback_used, tried_keys}
    """
    canon = normalize_mode(mode)
    tgts = list(targets or [])
    primary = pack_key(
        canon, paths, task, targets=tgts, include_task=include_task
    )
    tried = [primary]
    cached = load_pack(primary)
    meta: Dict[str, Any] = {
        "canon_mode": canon,
        "fallback_used": False,
        "tried_keys": tried,
    }
    if cached is not None:
        try:
            from aegis.cache_optimizer import record_lookup

            record_lookup(canon, hit=True, fallback_used=False)
        except Exception:  # noqa: BLE001
            pass
        return primary, cached, meta

    covered = covering_pack(canon, paths, targets=tgts)
    if covered is not None:
        kid, payload, cover_meta = covered
        cover_meta["tried_keys"] = tried + [kid]
        try:
            from aegis.cache_optimizer import record_lookup

            record_lookup(canon, hit=True, fallback_used=bool(cover_meta.get("fallback_used")))
        except Exception:  # noqa: BLE001
            pass
        return kid, payload, cover_meta

    if allow_fallback and not tgts:
        # static + learned fallbacks (self-optimizing cache)
        try:
            from aegis.cache_optimizer import effective_fallbacks

            fallbacks = effective_fallbacks(canon)
        except Exception:  # noqa: BLE001
            fallbacks = list(MODE_FALLBACKS.get(canon, []))
        for fb in fallbacks:
            kid = pack_key(fb, paths, task, targets=[], include_task=include_task)
            tried.append(kid)
            hit = load_pack(kid)
            if hit is not None:
                meta["fallback_used"] = True
                meta["fallback_mode"] = fb
                meta["tried_keys"] = tried
                try:
                    from aegis.cache_optimizer import record_lookup

                    record_lookup(canon, hit=True, fallback_used=True)
                except Exception:  # noqa: BLE001
                    pass
                # Reuse the key that actually holds the payload
                return kid, hit, meta

    try:
        from aegis.cache_optimizer import record_lookup

        record_lookup(canon, hit=False, fallback_used=False)
    except Exception:  # noqa: BLE001
        pass
    return primary, None, meta


INDEX_CAP = 80


def _resolve_files(paths: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in paths or []:
        p = Path(str(raw)).expanduser()
        if not p.is_file():
            continue
        resolved = str(p.resolve())
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def attach_reuse_meta(
    payload: Dict[str, Any],
    paths: Sequence[str],
    mode: str,
    targets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Stamp hashes so later covering reuse can refuse stale bytes."""
    resolved = _resolve_files(paths)
    if not resolved:
        for item in payload.get("bento_components") or []:
            raw = str(item.get("path") or "")
            if raw and Path(raw).is_file():
                resolved.append(str(Path(raw).resolve()))
        resolved = list(dict.fromkeys(resolved))
    payload["path_set"] = resolved
    payload["path_hashes"] = {p: file_hash(p) for p in resolved}
    payload["canon_mode"] = normalize_mode(mode)
    payload["cache_targets"] = sorted(
        {t.strip() for t in (targets or []) if t and str(t).strip()}
    )
    return payload


def _index_path() -> Path:
    return packs_dir() / "index.jsonl"


def _index_append(pack_id: str, payload: Dict[str, Any]) -> None:
    paths = [str(p) for p in (payload.get("path_set") or []) if p]
    hashes = payload.get("path_hashes") or {}
    if not paths or not isinstance(hashes, dict):
        return
    entry = {
        "pack_id": pack_id,
        "mode": str(payload.get("canon_mode") or payload.get("mode") or "explore"),
        "paths": paths,
        "hashes": hashes,
        "targets": list(payload.get("cache_targets") or []),
    }
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: List[str] = []
    if path.is_file():
        try:
            rows = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            rows = []
    rows.append(json.dumps(entry, ensure_ascii=False))
    rows = rows[-INDEX_CAP:]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _read_index() -> List[Dict[str, Any]]:
    path = _index_path()
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("pack_id"):
                out.append(row)
    except OSError:
        return []
    return out


def _mode_covers(want: str, have: str) -> bool:
    want_m = normalize_mode(want)
    have_m = normalize_mode(have)
    if want_m == "implement":
        return have_m == "implement"
    if want_m == "review":
        return have_m in ("review", "explore")
    return have_m == "explore"


def _targets_match(want: Optional[Sequence[str]], have: Optional[Sequence[str]]) -> bool:
    a = sorted({str(t).strip() for t in (want or []) if t and str(t).strip()})
    b = sorted({str(t).strip() for t in (have or []) if t and str(t).strip()})
    return a == b


def _hashes_fresh(paths: Sequence[str], stored: Dict[str, Any]) -> bool:
    if not stored:
        return False
    for p in paths:
        got = stored.get(p) or stored.get(str(Path(p).resolve()))
        try:
            if not got or str(got) != file_hash(p):
                return False
        except OSError:
            return False
    return True


def covering_pack(
    mode: str,
    paths: Sequence[str],
    *,
    targets: Optional[Sequence[str]] = None,
) -> Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Reuse a prior pack whose path-set covers these files and whose hashes still match."""
    want = _resolve_files(paths)
    if not want:
        return None
    want_set = set(want)
    for entry in reversed(_read_index()):
        have_paths = [str(p) for p in (entry.get("paths") or []) if p]
        if not want_set.issubset(set(have_paths)):
            continue
        if not _mode_covers(mode, str(entry.get("mode") or "explore")):
            continue
        if not _targets_match(targets, entry.get("targets")):
            continue
        hashes = entry.get("hashes") if isinstance(entry.get("hashes"), dict) else {}
        if not _hashes_fresh(want, hashes):
            continue
        kid = str(entry.get("pack_id") or "")
        payload = load_pack(kid)
        if not payload:
            continue
        have_mode = normalize_mode(str(entry.get("mode") or "explore"))
        meta = {
            "canon_mode": normalize_mode(mode),
            "fallback_used": have_mode != normalize_mode(mode),
            "covering": True,
            "tried_keys": [kid],
        }
        return kid, payload, meta
    return None
