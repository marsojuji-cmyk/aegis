"""
Self-optimizing pack cache — track hits/misses, widen fallbacks, prune cold packs.

Production-hardened: RLock, atomic stats write, safe mode keys, prune caps.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from aegis.pack_cache import MODE_FALLBACKS, packs_dir
from aegis.paths import cache_stats_path, ensure_home

_LOCK = threading.RLock()
MAX_LEARNED_PER_MODE = 3
VALID_MODES = frozenset({"explore", "implement", "review"})


def _default_stats() -> Dict[str, Any]:
    return {
        "hits": 0,
        "misses": 0,
        "fallback_hits": 0,
        "by_mode": {},
        "learned_fallbacks": {},
        "pruned": 0,
        "last_optimize_ts": None,
    }


def _atomic_save(stats: Dict[str, Any]) -> None:
    ensure_home()
    path = cache_stats_path()
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(stats, indent=2)
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except OSError:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        path.write_text(payload, encoding="utf-8")


def load_stats() -> Dict[str, Any]:
    ensure_home()
    path = cache_stats_path()
    with _LOCK:
        if not path.is_file():
            st = _default_stats()
            _atomic_save(st)
            return dict(st)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, json.JSONDecodeError):
            data = {}
        base = _default_stats()
        base.update(data)
        if not isinstance(base.get("by_mode"), dict):
            base["by_mode"] = {}
        if not isinstance(base.get("learned_fallbacks"), dict):
            base["learned_fallbacks"] = {}
        return base


def save_stats(stats: Dict[str, Any]) -> None:
    with _LOCK:
        _atomic_save(stats)


def _norm_mode(mode: str) -> str:
    m = (mode or "explore").strip().lower()
    if m in VALID_MODES:
        return m
    return "explore"


def record_lookup(
    mode: str,
    *,
    hit: bool,
    fallback_used: bool = False,
) -> Dict[str, Any]:
    mode = _norm_mode(mode)
    with _LOCK:
        st = load_stats()
        if hit:
            st["hits"] = int(st.get("hits") or 0) + 1
            if fallback_used:
                st["fallback_hits"] = int(st.get("fallback_hits") or 0) + 1
        else:
            st["misses"] = int(st.get("misses") or 0) + 1
        by = st.setdefault("by_mode", {})
        m = by.setdefault(mode, {"hits": 0, "misses": 0, "fallback_hits": 0})
        if hit:
            m["hits"] = int(m.get("hits") or 0) + 1
            if fallback_used:
                m["fallback_hits"] = int(m.get("fallback_hits") or 0) + 1
        else:
            m["misses"] = int(m.get("misses") or 0) + 1
        _atomic_save(st)
        return dict(st)


def hit_rate(stats: Optional[Dict[str, Any]] = None) -> float:
    st = stats if stats is not None else load_stats()
    h = int(st.get("hits") or 0)
    m = int(st.get("misses") or 0)
    t = h + m
    return round((h / float(t)) * 100.0, 1) if t else 0.0


def effective_fallbacks(mode: str) -> List[str]:
    """Static fallbacks + learned extras (deduped, capped)."""
    mode = _norm_mode(mode)
    st = load_stats()
    base = list(MODE_FALLBACKS.get(mode, []))
    raw_learned = st.get("learned_fallbacks", {}).get(mode) or []
    if not isinstance(raw_learned, list):
        raw_learned = []
    learned = [str(x) for x in raw_learned if str(x) in VALID_MODES]
    out: List[str] = []
    for x in base + learned:
        if x not in out and x != mode and x in VALID_MODES:
            out.append(x)
        if len(out) >= MAX_LEARNED_PER_MODE + 2:
            break
    return out


def optimize_cache(*, max_prune: int = 40, cold_days: int = 14) -> Dict[str, Any]:
    """
    Self-optimize:
    1) Low mode hit-rate → learn safe fallbacks
    2) Prune pack files older than cold_days (capped)
    """
    max_prune = max(0, min(int(max_prune or 40), 200))
    cold_days = max(1, min(int(cold_days or 14), 90))
    actions: List[str] = []
    pruned = 0

    with _LOCK:
        st = load_stats()
        learned = dict(st.get("learned_fallbacks") or {})
        if not isinstance(learned, dict):
            learned = {}

        by = st.get("by_mode") or {}
        if not isinstance(by, dict):
            by = {}

        for mode, mstats in list(by.items()):
            if mode not in VALID_MODES:
                continue
            if not isinstance(mstats, dict):
                continue
            h = int(mstats.get("hits") or 0)
            miss = int(mstats.get("misses") or 0)
            total = h + miss
            if total < 8:
                continue
            rate = h / float(total)
            cur = list(learned.get(mode) or [])
            if not isinstance(cur, list):
                cur = []
            cur = [c for c in cur if c in VALID_MODES and c != mode]

            if rate < 0.25 and mode in ("implement", "review"):
                if "explore" not in cur:
                    cur.append("explore")
                    actions.append(
                        f"learned fallback {mode}→explore (hit_rate={rate:.0%})"
                    )
            if rate < 0.15 and mode == "implement":
                if "review" not in cur:
                    cur.append("review")
                    actions.append(f"learned fallback {mode}→review")

            learned[mode] = cur[:MAX_LEARNED_PER_MODE]

        st["learned_fallbacks"] = learned

        pdir = packs_dir()
        if pdir.is_dir() and max_prune > 0:
            now = time.time()
            cold_age = cold_days * 86400
            candidates: List[Path] = []
            try:
                for p in pdir.glob("*.json"):
                    try:
                        age = now - p.stat().st_mtime
                        if age > cold_age:
                            candidates.append(p)
                    except OSError:
                        continue
                candidates.sort(key=lambda p: p.stat().st_mtime)
                for p in candidates[:max_prune]:
                    try:
                        p.unlink()
                        pruned += 1
                    except OSError:
                        pass
            except OSError:
                pass

        if pruned:
            actions.append(f"pruned {pruned} cold pack files (>{cold_days}d)")
            st["pruned"] = int(st.get("pruned") or 0) + pruned

        st["last_optimize_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _atomic_save(st)
        rate = hit_rate(st)
        return {
            "ok": True,
            "hit_rate_percent": rate,
            "hits": st.get("hits"),
            "misses": st.get("misses"),
            "actions": actions,
            "learned_fallbacks": learned,
            "pruned": pruned,
            "stats": st,
        }


def patch_get_or_none_meta(meta: Dict[str, Any], mode: str) -> None:
    """Call after pack get_or_none to feed optimizer."""
    if not isinstance(meta, dict):
        return
    hit = meta.get("hit")
    if hit is None:
        return
    try:
        record_lookup(
            mode,
            hit=bool(hit),
            fallback_used=bool(meta.get("fallback_used")),
        )
    except Exception:  # noqa: BLE001
        pass
