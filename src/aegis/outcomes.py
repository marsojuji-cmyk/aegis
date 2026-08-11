"""Append-only outcome evidence for the Aegis production workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from aegis.paths import ensure_home, outcomes_path


REQUIRED_VARIANTS = {"baseline", "governed"}


def record_outcome(
    *, task_id: str, variant: str, accepted: bool, elapsed_seconds: float,
    retries: int = 0, correction_minutes: float = 0.0, cost_usd: float = 0.0,
    workflow: str = "production_code_change", notes: str = "",
) -> Dict[str, Any]:
    """Write an observed task result; no estimated result is manufactured."""
    if variant not in REQUIRED_VARIANTS:
        raise ValueError("variant must be baseline or governed")
    if not task_id.strip():
        raise ValueError("task_id is required")
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id.strip(), "workflow": workflow,
        "variant": variant, "accepted": bool(accepted),
        "elapsed_seconds": max(0.0, float(elapsed_seconds)),
        "retries": max(0, int(retries)),
        "correction_minutes": max(0.0, float(correction_minutes)),
        "cost_usd": max(0.0, float(cost_usd)), "notes": notes.strip(),
    }
    ensure_home()
    with outcomes_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def load_outcomes() -> Iterable[Dict[str, Any]]:
    path = outcomes_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if row.get("variant") in REQUIRED_VARIANTS:
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def outcome_report() -> Dict[str, Any]:
    """Read-only matched-task report; recommendation is withheld until evidence."""
    rows = list(load_outcomes())
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["task_id"], {})[row["variant"]] = row
    pairs = [pair for pair in grouped.values() if REQUIRED_VARIANTS <= set(pair)]
    if not pairs:
        return {"paired_tasks": 0, "routing_authorized": False,
                "decision": "withhold: no matched baseline/governed outcomes"}
    base = [pair["baseline"] for pair in pairs]
    governed = [pair["governed"] for pair in pairs]
    acceptance_delta = (sum(x["accepted"] for x in governed) - sum(x["accepted"] for x in base)) / len(pairs)
    time_delta = sum(b["elapsed_seconds"] - g["elapsed_seconds"] for b, g in zip(base, governed)) / len(pairs)
    retry_delta = sum(b["retries"] - g["retries"] for b, g in zip(base, governed)) / len(pairs)
    cost_delta = sum(b["cost_usd"] - g["cost_usd"] for b, g in zip(base, governed))
    authorized = acceptance_delta >= 0 and time_delta > 0
    return {"paired_tasks": len(pairs), "acceptance_delta": round(acceptance_delta, 4),
            "mean_seconds_saved": round(time_delta, 2), "mean_retries_avoided": round(retry_delta, 2),
            "total_cost_usd_saved": round(cost_delta, 6), "routing_authorized": authorized,
            "decision": "eligible for routing trial" if authorized else "withhold: no quality-preserving time gain"}
