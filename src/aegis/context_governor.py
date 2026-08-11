"""Context-window governor: meter, checkpoint, and transfer before failure."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from aegis.tokens import estimate_tokens
from aegis.paths import context_capsules_dir, ensure_home


@dataclass(frozen=True)
class ContextStatus:
    capacity: int
    assembled_tokens: int
    expected_output_tokens: int
    occupancy_percent: float
    band: str
    action: str

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


_BANDS = (
    (45.0, "green", "work"),
    (60.0, "checkpoint", "write_verified_capsule"),
    (75.0, "compact", "replace_history_with_capsule_and_jit_pack"),
    (85.0, "transfer", "start_clean_task_from_verified_capsule"),
    (float("inf"), "red", "recover_only_from_last_verified_capsule"),
)


def meter_context(
    messages: Iterable[Mapping[str, Any]],
    *,
    tool_schemas: Optional[Iterable[Mapping[str, Any]]] = None,
    attachment_tokens: int = 0,
    expected_output_tokens: int = 0,
    capacity: int = 258_000,
) -> ContextStatus:
    """Estimate the full assembled request; never silently omit tool overhead."""
    payload = list(messages)
    tools = list(tool_schemas or [])
    assembled = estimate_tokens(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    assembled += estimate_tokens(json.dumps(tools, sort_keys=True, ensure_ascii=False))
    assembled += max(0, int(attachment_tokens))
    expected = max(0, int(expected_output_tokens))
    cap = max(1, int(capacity))
    occupancy = round(((assembled + expected) / float(cap)) * 100.0, 2)
    for threshold, band, action in _BANDS:
        if occupancy < threshold:
            return ContextStatus(cap, assembled, expected, occupancy, band, action)
    raise AssertionError("unreachable")


def state_capsule(
    *,
    objective: str,
    constraints: Iterable[str] = (),
    decisions: Iterable[str] = (),
    artifacts: Iterable[Mapping[str, str]] = (),
    verified: Iterable[str] = (),
    current_defect: str = "",
    next_action: str = "",
    verification_status: str = "verified",
    max_tokens: int = 1500,
) -> Dict[str, Any]:
    """Create a bounded resume receipt; raw evidence stays outside the prompt."""
    if verification_status not in {"verified", "provisional"}:
        raise ValueError("verification_status must be verified or provisional")
    capsule = {
        "objective": objective.strip(),
        "constraints": [str(x).strip() for x in constraints if str(x).strip()],
        "decisions": [str(x).strip() for x in decisions if str(x).strip()],
        "artifacts": [dict(x) for x in artifacts],
        "verified": [str(x).strip() for x in verified if str(x).strip()],
        "current_defect": current_defect.strip(),
        "next_action": next_action.strip(),
        "verification_status": verification_status,
    }
    text = json.dumps(capsule, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    tokens = estimate_tokens(text)
    if tokens > max(1, int(max_tokens)):
        raise ValueError(f"capsule exceeds limit: {tokens}>{max_tokens} tokens")
    capsule["tokens"] = tokens
    capsule["fingerprint"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return capsule


def persist_capsule(capsule: Mapping[str, Any]) -> Path:
    """Persist a bounded handoff receipt; never rewrite chat history."""
    ensure_home()
    directory = context_capsules_dir()
    directory.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}_{capsule['fingerprint']}.json"
    path.write_text(json.dumps(dict(capsule), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
