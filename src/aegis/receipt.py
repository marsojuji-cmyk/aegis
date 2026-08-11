"""Last pack receipt — attach pack_id + stats to the next agent turn."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from aegis.ledger import read_all
from aegis.pack_cache import load_pack
from aegis.paths import ensure_home, aegis_home


def last_receipt_path():
    return aegis_home() / "last_pack.json"


def write_last_receipt(entry: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_home()
    receipt = {
        "pack_id": entry.get("pack_id"),
        "txn_id": entry.get("id"),
        "ts": entry.get("ts"),
        "kind": entry.get("kind"),
        "mode": entry.get("mode"),
        "task": entry.get("task"),
        "raw_in": entry.get("raw_in"),
        "processed_in": entry.get("processed_in"),
        "tokens_saved": entry.get("tokens_saved"),
        "reuse": entry.get("reuse"),
        "paths": (entry.get("meta") or {}).get("paths"),
        "targets": (entry.get("meta") or {}).get("targets"),
        "engine": (entry.get("meta") or {}).get("engine")
        or (payload or {}).get("engine"),
        "reduction_percent": (payload or {}).get("overall_reduction_percent"),
    }
    last_receipt_path().write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def load_last_receipt() -> Optional[Dict[str, Any]]:
    path = last_receipt_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    # fallback: last pack/reuse from ledger
    rows = [r for r in read_all() if r.get("kind") in ("pack", "reuse_hit")]
    if not rows:
        return None
    last = rows[-1]
    return write_last_receipt(last)


def format_receipt_block(receipt: Dict[str, Any]) -> str:
    """Compact block agents can paste into a turn."""
    lines = [
        "[AEGIS PACK RECEIPT]",
        f"pack_id={receipt.get('pack_id')} mode={receipt.get('mode')} "
        f"reuse={receipt.get('reuse')}",
        f"tokens={receipt.get('raw_in')}→{receipt.get('processed_in')} "
        f"saved={receipt.get('tokens_saved')} "
        f"cut={receipt.get('reduction_percent')}%",
        f"task={receipt.get('task')}",
    ]
    paths = receipt.get("paths") or []
    if paths:
        lines.append("paths=" + ",".join(str(p) for p in paths[:12]))
    targets = receipt.get("targets") or []
    if targets:
        lines.append("targets=" + ",".join(str(t) for t in targets))
    lines.append("rule=prefer this payload over re-reading listed paths")
    return "\n".join(lines)
