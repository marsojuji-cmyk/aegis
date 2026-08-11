"""Output lane — activate, land, shrink+store finals (thought→ship)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aegis.config import load_config
from aegis.ledger import record
from aegis.output_profiles import (
    estimated_processed_out,
    estimated_raw_out,
    render_profile,
)
from aegis.output_store import store_shrunk, store_stats
from aegis.paths import aegis_home, ensure_home
from aegis.tokens import estimate_tokens


def last_output_path() -> Path:
    return aegis_home() / "last_output.json"


def landed_log_path() -> Path:
    return aegis_home() / "landed.jsonl"


def mode_default_profile(mode: str) -> str:
    m = (mode or "explore").strip().lower()
    aliases = {
        "edit": "implement",
        "fix": "implement",
        "write": "implement",
        "read": "explore",
        "search": "explore",
        "pr": "review",
        "diff": "review",
    }
    m = aliases.get(m, m)
    if m == "implement":
        return "diff"
    if m == "review":
        return "json"
    return "brief"


def activate_output(
    *,
    profile: Optional[str] = None,
    mode: str = "explore",
    max_tokens: Optional[int] = None,
    task: str = "",
    dry_run: bool = False,
    pack_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit profile and persist policy receipt; do not book fake completion usage."""
    cfg = load_config()
    prof = (profile or mode_default_profile(mode)).lower()
    max_tok = max_tokens if max_tokens is not None else cfg.output_default_max
    block = render_profile(prof, max_tok)
    raw = estimated_raw_out(prof, max_tok)
    proc = estimated_processed_out(prof, max_tok)

    # A planned response is not a model response. Keeping estimates outside the
    # ledger prevents double/triple counting with land and router events.
    entry = None

    receipt = {
        "profile": prof,
        "max_tokens": max_tok,
        "instruction": block,
        "raw_out": raw,
        "processed_out": proc,
        "tokens_saved_est": max(0, raw - proc),
        "pack_id": pack_id,
        "ledger_id": None,
        "landed": False,
        "token_accounting": "code_only_in_pack; out_lane_separate",
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if not dry_run:
        ensure_home()
        last_output_path().write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def land_output(
    *,
    actual_tokens: Optional[int] = None,
    raw_tokens: Optional[int] = None,
    summary: str = "",
    files: Optional[List[str]] = None,
    task: str = "",
    body: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Land completed work: shrink+store body when provided, book ledger, mark landed.

    If body is set, actual_tokens defaults to shrunk size (code-honest).
    """
    last = load_last_output() or {}
    prof = last.get("profile") or "brief"
    pack_id = last.get("pack_id")

    store_receipt = None
    if body is not None and body != "":
        store_receipt = store_shrunk(
            body=body,
            profile=prof,
            pack_id=pack_id,
            summary=summary,
            dry_run=dry_run,
        )
        # Prefer shrunk size as "actual" when not explicitly given
        if actual_tokens is None:
            actual_tokens = int(store_receipt.get("shrunk_tokens") or 0)
        if raw_tokens is None:
            raw_tokens = int(store_receipt.get("raw_tokens") or estimate_tokens(body))

    if actual_tokens is None:
        raise ValueError("land requires --actual and/or --body/--body-file")

    raw = int(
        raw_tokens
        if raw_tokens is not None
        else last.get("raw_out") or actual_tokens * 3
    )
    actual = max(0, int(actual_tokens))
    entry = None
    if not dry_run:
        entry = record(
            kind="output_record",
            task=task or f"land:{prof}",
            mode="output",
            raw_out=raw,
            processed_out=actual,
            meta={
                "profile": prof,
                "landed": True,
                "summary": summary[:500],
                "files": files or [],
                "pack_id": pack_id,
                "estimate_ledger_id": last.get("ledger_id"),
                "output_id": (store_receipt or {}).get("id"),
                "output_reuse": (store_receipt or {}).get("reuse"),
                "shrunk_tokens": (store_receipt or {}).get("shrunk_tokens"),
                "bytes_saved": max(
                    0,
                    int((store_receipt or {}).get("bytes_raw") or 0)
                    - int((store_receipt or {}).get("bytes_shrunk") or 0),
                ),
            },
        )

    landed = {
        "landed": True,
        "profile": prof,
        "raw_out": raw,
        "actual_out": actual,
        "tokens_saved": max(0, raw - actual),
        "summary": summary,
        "files": files or [],
        "pack_id": pack_id,
        "ledger_id": (entry or {}).get("id"),
        "prior_estimate_save": last.get("tokens_saved_est"),
        "output_id": (store_receipt or {}).get("id"),
        "output_reuse": (store_receipt or {}).get("reuse", False),
        "shrunk_text": (store_receipt or {}).get("shrunk_text"),
        "bytes_raw": (store_receipt or {}).get("bytes_raw"),
        "bytes_shrunk": (store_receipt or {}).get("bytes_shrunk"),
        "store_tokens_saved": (store_receipt or {}).get("tokens_saved"),
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "token_accounting": "landed_actual+output_reduce_store",
    }
    if not dry_run:
        ensure_home()
        merged = dict(last)
        merged.update(
            {
                "landed": True,
                "actual_out": actual,
                "tokens_saved_actual": landed["tokens_saved"],
                "land_ledger_id": landed["ledger_id"],
                "summary": summary,
                "output_id": landed.get("output_id"),
                "output_reuse": landed.get("output_reuse"),
                "shrunk_text": landed.get("shrunk_text"),
            }
        )
        last_output_path().write_text(json.dumps(merged, indent=2), encoding="utf-8")
        # slim landed log (no full body) — full body lives in outputs/
        log_row = {
            k: v
            for k, v in landed.items()
            if k != "shrunk_text"
        }
        with landed_log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_row, ensure_ascii=False) + "\n")
    return landed


def load_last_output() -> Optional[Dict[str, Any]]:
    path = last_output_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def count_landed() -> int:
    path = landed_log_path()
    if not path.is_file():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def format_output_block(receipt: Dict[str, Any]) -> str:
    landed = receipt.get("landed")
    tag = "LANDED" if landed else "ACTIVE"
    lines = [
        f"[AEGIS OUTPUT LANE — {tag}]",
        f"profile={receipt.get('profile')} max_out={receipt.get('max_tokens')} "
        f"est_save={receipt.get('tokens_saved_est')}",
    ]
    if landed:
        lines.append(
            f"actual_out={receipt.get('actual_out')} "
            f"saved_actual={receipt.get('tokens_saved_actual')}"
        )
        if receipt.get("output_id"):
            lines.append(
                f"store={receipt.get('output_id')} reuse={receipt.get('output_reuse')}"
            )
    lines.append(
        "rule=obey profile; land with body: `aegis land --body-file out.txt --actual N`"
    )
    lines.append("")
    if not landed:
        lines.append(receipt.get("instruction") or "")
    elif receipt.get("shrunk_text"):
        lines.append("--- shrunk final ---")
        lines.append(receipt["shrunk_text"])
    return "\n".join(lines).rstrip() + "\n"


def format_land_block(landed: Dict[str, Any]) -> str:
    lines = [
        "[AEGIS WORK LANDED]",
        f"profile={landed.get('profile')} actual_out={landed.get('actual_out')} "
        f"saved={landed.get('tokens_saved')} ledger={landed.get('ledger_id')}",
    ]
    if landed.get("output_id"):
        lines.append(
            f"store={landed.get('output_id')} reuse={landed.get('output_reuse')} "
            f"bytes={landed.get('bytes_raw')}→{landed.get('bytes_shrunk')} "
            f"store_tok_saved={landed.get('store_tokens_saved')}"
        )
    lines.append(f"summary={landed.get('summary') or '—'}")
    if landed.get("shrunk_text"):
        lines.append("--- shrunk final ---")
        lines.append(str(landed["shrunk_text"]))
    return "\n".join(lines) + "\n"
