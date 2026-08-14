"""Append-only outcome evidence for the Aegis production workflow."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from aegis.paths import ensure_home, outcomes_path


REQUIRED_VARIANTS = {"baseline", "governed"}
# A routing trial is a policy change, not a one-off anecdote.  Keep this
# explicit and conservative until an evidence-backed configuration layer is
# introduced.
MINIMUM_MATCHED_TASKS = 10
OBSERVED_COST_STATUSES = {"observed", "verified_zero"}
ALL_COST_STATUSES = OBSERVED_COST_STATUSES | {"unknown", "legacy_unknown"}
PILOT_WORKFLOW = "decision_grade_code_change"


def _pilot_state_path(task_id: str) -> Path:
    safe = task_id.strip()
    if not safe or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in safe):
        raise ValueError("pilot task_id may contain only letters, numbers, hyphens, and underscores")
    directory = ensure_home() / "pilot-sessions"
    directory.mkdir(exist_ok=True)
    return directory / f"{safe}.json"


def _write_pilot_state(path: Path, state: Dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def pilot_status(task_id: str) -> Dict[str, Any]:
    path = _pilot_state_path(task_id)
    if not path.is_file():
        raise ValueError(f"pilot session does not exist: {task_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def init_pilot(
    *, task_id: str, source_dir: str, first_variant: str,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Create two identical local workspaces and freeze their execution order."""
    if first_variant not in REQUIRED_VARIANTS:
        raise ValueError("first_variant must be baseline or governed")
    state_path = _pilot_state_path(task_id)
    if state_path.exists():
        raise ValueError(f"pilot session already exists: {task_id}")
    source = Path(source_dir).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"pilot source_dir is not a directory: {source}")
    root = (
        Path(workspace_root).expanduser().resolve()
        if workspace_root else ensure_home() / "pilot-workspaces"
    )
    if root == source or source in root.parents:
        raise ValueError("pilot workspace_root must be outside source_dir")
    task_root = root / task_id
    if task_root.exists():
        raise ValueError(f"pilot workspace already exists: {task_root}")
    task_root.mkdir(parents=True)
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
    workspaces = {}
    for variant in ("baseline", "governed"):
        destination = task_root / variant
        shutil.copytree(source, destination, ignore=ignore)
        workspaces[variant] = str(destination)
    second = "governed" if first_variant == "baseline" else "baseline"
    state = {
        "task_id": task_id,
        "source_dir": str(source),
        "workspace_root": str(task_root),
        "workspaces": workspaces,
        "order": [first_variant, second],
        "current": None,
        "results": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_pilot_state(state_path, state)
    return state


def start_pilot(task_id: str, variant: str) -> Dict[str, Any]:
    """Start the next frozen variant using a durable wall-clock timestamp."""
    state_path = _pilot_state_path(task_id)
    state = pilot_status(task_id)
    if state["current"] is not None:
        raise ValueError(f"pilot variant already running: {state['current']['variant']}")
    completed = len(state["results"])
    if completed >= len(state["order"]):
        raise ValueError("pilot pair is already complete")
    expected = state["order"][completed]
    if variant != expected:
        raise ValueError(f"pilot order requires {expected} next")
    state["current"] = {
        "variant": variant,
        "started_at_epoch": time.time(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_pilot_state(state_path, state)
    return {"task_id": task_id, "variant": variant, "workspace": state["workspaces"][variant]}


def finish_pilot(
    task_id: str, *, accepted: bool, retries: int = 0,
    correction_minutes: float = 0.0, notes: str = "",
    cost_usd: float | None = None, cost_status: str | None = None,
    cost_source: str = "",
) -> Dict[str, Any]:
    """Stop the active timer and append one cost-unknown production outcome."""
    state_path = _pilot_state_path(task_id)
    state = pilot_status(task_id)
    current = state.get("current")
    if not current:
        raise ValueError("pilot has no active variant")
    elapsed = max(0.0, time.time() - float(current["started_at_epoch"]))
    row = record_outcome(
        task_id=task_id,
        variant=current["variant"],
        accepted=accepted,
        elapsed_seconds=elapsed,
        retries=retries,
        correction_minutes=correction_minutes,
        cost_usd=cost_usd,
        cost_status=cost_status or "unknown",
        cost_source=cost_source,
        workflow=PILOT_WORKFLOW,
        notes=notes,
    )
    state["results"][current["variant"]] = row
    state["current"] = None
    _write_pilot_state(state_path, state)
    return {"outcome": row, "pair_complete": len(state["results"]) == 2}


def record_outcome(
    *, task_id: str, variant: str, accepted: bool, elapsed_seconds: float,
    retries: int = 0, correction_minutes: float = 0.0,
    cost_usd: Optional[float] = None, cost_status: Optional[str] = None,
    cost_source: str = "",
    workflow: str = "production_code_change", notes: str = "",
) -> Dict[str, Any]:
    """Write an observed task result; unknown cost is never stored as zero."""
    if variant not in REQUIRED_VARIANTS:
        raise ValueError("variant must be baseline or governed")
    if not task_id.strip():
        raise ValueError("task_id is required")
    status = (cost_status or ("unknown" if cost_usd is None else "legacy_unknown")).strip()
    source = cost_source.strip()
    if status not in ALL_COST_STATUSES:
        raise ValueError(f"cost_status must be one of: {sorted(ALL_COST_STATUSES)}")
    if status in OBSERVED_COST_STATUSES:
        if cost_usd is None:
            raise ValueError("observed or verified_zero cost requires cost_usd")
        if not source:
            raise ValueError("observed or verified_zero cost requires cost_source")
    elif source:
        raise ValueError("unknown or legacy_unknown cost cannot declare cost_source")
    normalized_cost = None if cost_usd is None else max(0.0, float(cost_usd))
    if status == "verified_zero" and normalized_cost != 0.0:
        raise ValueError("verified_zero cost requires cost_usd=0")
    if status == "unknown" and normalized_cost is not None:
        raise ValueError("unknown cost cannot include cost_usd")
    normalized_task_id = task_id.strip()
    duplicate = any(
        row.get("task_id") == normalized_task_id
        and row.get("workflow", "production_code_change") == workflow
        and row.get("variant") == variant
        for row in load_outcomes()
    )
    if duplicate:
        raise ValueError(
            f"outcome already recorded for task_id={normalized_task_id}, "
            f"workflow={workflow}, variant={variant}"
        )
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": normalized_task_id, "workflow": workflow,
        "variant": variant, "accepted": bool(accepted),
        "elapsed_seconds": max(0.0, float(elapsed_seconds)),
        "retries": max(0, int(retries)),
        "correction_minutes": max(0.0, float(correction_minutes)),
        "cost_usd": normalized_cost, "cost_status": status,
        "cost_source": source, "notes": notes.strip(),
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


def outcome_report(*, workflow: str = "production_code_change") -> Dict[str, Any]:
    """Read-only matched-task report; recommendation is withheld until evidence."""
    rows = [row for row in load_outcomes() if row.get("workflow") == workflow]
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["task_id"], {})[row["variant"]] = row
    pairs = [pair for pair in grouped.values() if REQUIRED_VARIANTS <= set(pair)]
    if not pairs:
        return {"workflow": workflow, "paired_tasks": 0, "routing_authorized": False,
                "minimum_matched_tasks": MINIMUM_MATCHED_TASKS,
                "cost_decision": "withhold: no matched outcomes with provider-cost evidence",
                "decision": "withhold: no matched baseline/governed outcomes"}
    base = [pair["baseline"] for pair in pairs]
    governed = [pair["governed"] for pair in pairs]
    acceptance_delta = (sum(x["accepted"] for x in governed) - sum(x["accepted"] for x in base)) / len(pairs)
    time_delta = sum(b["elapsed_seconds"] - g["elapsed_seconds"] for b, g in zip(base, governed)) / len(pairs)
    retry_delta = sum(b["retries"] - g["retries"] for b, g in zip(base, governed)) / len(pairs)
    observed_cost_pairs = [
        (b, g) for b, g in zip(base, governed)
        if b.get("cost_status") in OBSERVED_COST_STATUSES
        and g.get("cost_status") in OBSERVED_COST_STATUSES
    ]
    cost_complete = len(observed_cost_pairs) == len(pairs)
    cost_delta = (
        sum(b["cost_usd"] - g["cost_usd"] for b, g in observed_cost_pairs)
        if cost_complete else None
    )
    cost_decision = (
        "available: all matched pairs have observed provider-cost evidence"
        if cost_complete else
        f"withhold: {len(observed_cost_pairs)}/{len(pairs)} matched pairs have observed provider-cost evidence"
    )
    sample_sufficient = len(pairs) >= MINIMUM_MATCHED_TASKS
    pipeline_trustworthy = cost_verification_report(limit=5)["trustworthy_for_routing"]
    authorized = (
        sample_sufficient and acceptance_delta >= 0 and time_delta >= 0
        and cost_complete and pipeline_trustworthy
        and cost_delta is not None and cost_delta > 0
    )
    if not pipeline_trustworthy:
        decision = "withhold: cost provenance pipeline is not verified as trustworthy"
    elif not sample_sufficient:
        decision = (
            f"withhold: {len(pairs)}/{MINIMUM_MATCHED_TASKS} matched tasks; "
            "routing evidence is insufficient"
        )
    elif not cost_complete:
        decision = "withhold: not all matched outcomes have provider-cost evidence"
    elif not (cost_delta is not None and cost_delta > 0):
        decision = "withhold: no quality-preserving cost reduction"
    elif authorized:
        decision = "eligible for routing trial"
    else:
        decision = "withhold: no quality-preserving time gain"
    return {"workflow": workflow, "paired_tasks": len(pairs), "minimum_matched_tasks": MINIMUM_MATCHED_TASKS,
            "acceptance_delta": round(acceptance_delta, 4),
            "mean_seconds_saved": round(time_delta, 2), "mean_retries_avoided": round(retry_delta, 2),
            "observed_cost_pairs": len(observed_cost_pairs),
            "cost_comparison_complete": cost_complete,
            "cost_decision": cost_decision,
            "total_cost_usd_saved": None if cost_delta is None else round(cost_delta, 6),
            "routing_authorized": authorized,
            "decision": decision}


def cost_verification_report(limit: int = 5) -> Dict[str, Any]:
    """Audit the durable ledger for live cost provenance gaps in recent runs."""
    all_rows = list(load_outcomes())
    recent = all_rows[-limit:] if limit > 0 else all_rows

    gaps = []
    audited = 0
    for row in recent:
        audited += 1
        task_id = row.get("task_id", "missing")
        status = row.get("cost_status")
        usd = row.get("cost_usd")
        source = row.get("cost_source", "").strip()

        if status not in ALL_COST_STATUSES:
            gaps.append({"task_id": task_id, "error": f"invalid status: {status}"})
            continue

        if status in OBSERVED_COST_STATUSES:
            if usd is None or not isinstance(usd, (int, float)):
                gaps.append({"task_id": task_id, "error": "missing float cost_usd for observed status"})
            elif status == "verified_zero" and float(usd) != 0.0:
                gaps.append({"task_id": task_id, "error": "verified_zero requires cost_usd=0.0"})
            if not source:
                gaps.append({"task_id": task_id, "error": "missing cost_source for observed status"})
        else:
            if usd is not None:
                gaps.append({"task_id": task_id, "error": "cost_usd present for unknown status"})
            if source:
                gaps.append({"task_id": task_id, "error": "cost_source present for unknown status"})
            gaps.append({"task_id": task_id, "error": f"cost provenance missing (status={status})"})

    trustworthy = (audited == limit and len(gaps) == 0)
    return {
        "audited_runs": audited,
        "gaps_found": len(gaps),
        "gaps": gaps,
        "trustworthy_for_routing": trustworthy
    }
