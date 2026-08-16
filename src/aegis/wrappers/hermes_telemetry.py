"""Persist measured Hermes token counts for matched ungated/gated pairs.

Does not infer savings from timing, middleware, or cache reuse.
`savings_percent` is always None. `token_delta` is set only when both
sides were admitted by the R-012 gate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from aegis.paths import ensure_home, hermes_token_pairs_path

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_read",
    "api_calls",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_token_counts(usage: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Copy measured usage fields only. Missing keys stay None."""
    if not isinstance(usage, Mapping):
        return {key: None for key in ("input_tokens", "output_tokens", "total_tokens", "cache_read_tokens", "api_calls")}
    cache = usage.get("cache_read_tokens")
    if cache is None:
        cache = usage.get("cache_read")
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cache_read_tokens": cache,
        "api_calls": usage.get("api_calls"),
    }


def comparable_usage(usage: Optional[Mapping[str, Any]]) -> bool:
    counts = extract_token_counts(usage)
    return all(counts[key] is not None for key in ("input_tokens", "output_tokens", "total_tokens"))


def token_delta(
    control: Optional[Mapping[str, Any]],
    treatment: Optional[Mapping[str, Any]],
    *,
    pair_valid: bool,
) -> Optional[Dict[str, Any]]:
    """Ungated minus gated totals. None unless the pair was admitted."""
    if not pair_valid:
        return None
    left = extract_token_counts(control)
    right = extract_token_counts(treatment)
    if left["total_tokens"] is None or right["total_tokens"] is None:
        return None
    try:
        return {
            "input_tokens": left["input_tokens"] - right["input_tokens"],
            "output_tokens": left["output_tokens"] - right["output_tokens"],
            "total_tokens": left["total_tokens"] - right["total_tokens"],
        }
    except TypeError:
        return None


def record_pair(
    *,
    task_id: str,
    control_usage: Optional[Mapping[str, Any]],
    treatment_usage: Optional[Mapping[str, Any]],
    pair_valid: bool,
    control_session_id: str = "",
    treatment_session_id: str = "",
    model: str = "",
    provider: str = "",
    note: str = "",
    extra: Optional[Mapping[str, Any]] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append one pair record. Never writes a savings percentage."""
    ensure_home()
    dest = path or hermes_token_pairs_path()
    record: Dict[str, Any] = {
        "ts": _now(),
        "task_id": task_id,
        "model": model,
        "provider": provider,
        "control": {
            "session_id": control_session_id,
            "usage": extract_token_counts(control_usage),
        },
        "treatment": {
            "session_id": treatment_session_id,
            "usage": extract_token_counts(treatment_usage),
        },
        "pair_valid": bool(pair_valid),
        "token_delta": token_delta(control_usage, treatment_usage, pair_valid=pair_valid),
        "savings_percent": None,
        "efficiency_result": "valid_pair" if pair_valid else "invalid_pair",
        "note": note
        or (
            None
            if pair_valid
            else "No efficiency conclusion; pair not admitted."
        ),
    }
    if extra:
        record["extra"] = dict(extra)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
