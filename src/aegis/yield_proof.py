"""Honest economic-yield harness.

Fixture naive-vs-pack is labeled counterfactual_chars4.
savings_percent stays null unless an admitted Hermes pair exists.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from aegis.paths import hermes_token_pairs_path


ACCOUNTING = "counterfactual_chars4"


def admitted_pair_present() -> bool:
    path = hermes_token_pairs_path()
    if not path.is_file():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if '"admitted": true' in line or '"admitted":true' in line:
                return True
    except OSError:
        return False
    return False


def _naive_chars(paths: Sequence[str]) -> int:
    total = 0
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            total += p.stat().st_size
    return total


def prove(paths: Sequence[str], *, task: str = "yield-prove") -> Dict[str, Any]:
    from aegis.bento import assemble
    from aegis.pack_cache import get_or_none, save_pack

    files = [str(Path(p).expanduser().resolve()) for p in paths if Path(p).is_file()]
    if not files:
        return {"ok": False, "error": "no readable files", "savings_percent": None}
    snippets: List[Dict[str, str]] = []
    for path in files:
        snippets.append(
            {
                "path": path,
                "content": Path(path).read_text(encoding="utf-8", errors="replace"),
            }
        )
    naive = _naive_chars(files)
    naive_tok = naive // 4
    t0 = time.perf_counter()
    pack_id, cached, meta = get_or_none("explore", files, task)
    if cached is None:
        payload = assemble(core_task=task, code_snippets=snippets, mode="explore")
        save_pack(pack_id, payload)
        reuse = False
    else:
        payload = cached
        reuse = True
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    packed_tok = int(
        payload.get("total_compressed_tokens")
        or payload.get("compressed_tokens")
        or payload.get("tokens")
        or 0
    )
    if packed_tok <= 0:
        text = str(payload.get("bento") or payload.get("text") or "")
        packed_tok = max(1, len(text) // 4)
    saved = max(0, naive_tok - packed_tok)
    reduction = round((saved / float(naive_tok)) * 100.0, 1) if naive_tok else 0.0
    admitted = admitted_pair_present()
    return {
        "ok": True,
        "accounting": ACCOUNTING,
        "savings_percent": None,
        "admitted_pair": admitted,
        "naive_bytes": naive,
        "naive_tokens": naive_tok,
        "packed_tokens": packed_tok,
        "tokens_saved_counterfactual": saved,
        "reduction_percent_counterfactual": reduction,
        "reuse": reuse,
        "pack_id": pack_id,
        "fallback_used": bool(meta.get("fallback_used")),
        "elapsed_ms": elapsed_ms,
        "paths": files,
        "note": "reduction is chars/4 local counterfactual; not model savings",
    }


def bench(paths: Sequence[str], *, rounds: int = 12, task: str = "bench") -> Dict[str, Any]:
    files = [str(Path(p).expanduser().resolve()) for p in paths if Path(p).is_file()]
    if not files:
        return {"ok": False, "error": "no readable files"}
    cold: List[float] = []
    warm: List[float] = []
    naive: List[float] = []
    from aegis.pack_cache import file_hash, get_or_none
    from aegis.yield_proof import prove as _prove

    for _ in range(max(1, rounds)):
        t0 = time.perf_counter()
        for f in files:
            Path(f).read_text(encoding="utf-8", errors="replace")
        naive.append((time.perf_counter() - t0) * 1000.0)
        t1 = time.perf_counter()
        for f in files:
            file_hash(f)
        cold.append((time.perf_counter() - t1) * 1000.0)
        t2 = time.perf_counter()
        for f in files:
            file_hash(f)
        warm.append((time.perf_counter() - t2) * 1000.0)
        get_or_none("explore", files, task)

    def _pct(vals: List[float], p: float) -> float:
        if not vals:
            return 0.0
        ordered = sorted(vals)
        idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
        return round(ordered[idx], 3)

    proof = _prove(files, task=task)
    speedup = None
    if _pct(warm, 50) > 0:
        speedup = round(_pct(cold, 50) / max(_pct(warm, 50), 0.001), 2)
    return {
        "ok": True,
        "rounds": rounds,
        "naive_read_ms_p50": _pct(naive, 50),
        "hash_cold_ms_p50": _pct(cold, 50),
        "hash_warm_ms_p50": _pct(warm, 50),
        "hash_warm_ms_p95": _pct(warm, 95),
        "hash_cache_speedup_x": speedup,
        "yield": proof,
        "savings_percent": None,
    }


def yield_report() -> Dict[str, Any]:
    from aegis.ledger import generate_report

    report = generate_report()
    return {
        "ok": True,
        "accounting": ACCOUNTING,
        "savings_percent": None,
        "admitted_pair": admitted_pair_present(),
        "ledger_tokens_saved_local": report.get("total_tokens_saved"),
        "reuse_hit_rate": report.get("reuse_hit_rate_percent"),
        "note": "ledger saved tokens are local counterfactual unless admitted_pair",
    }
