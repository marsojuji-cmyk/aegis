"""Content-addressed pack reuse — mode map + path-set keys + soft fallbacks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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
