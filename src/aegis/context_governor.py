"""Context-window governor: meter, checkpoint, and transfer before failure."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from aegis.tokens import estimate_tokens
from aegis.paths import context_capsules_dir, ensure_home

_PRIVACY_CLASSES = frozenset({"public", "internal", "private", "sensitive", "restricted"})


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

_PLACEHOLDERS = {"...", "…", "todo", "tbd", "n/a", "na", "none", "unknown"}


def _meaningful(value: str) -> bool:
    """Reject template filler: a handoff is evidence, not a form submission."""
    normalized = " ".join(value.strip().lower().split())
    return len(normalized) >= 4 and normalized not in _PLACEHOLDERS and any(
        char.isalnum() for char in normalized
    )


def _local_embed(text: str, dims: int = 64) -> List[float]:
    vec = [0.0] * dims
    tokens = re.findall(r"[a-z0-9_./-]{2,}", (text or "").lower())
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(dims):
            b = digest[i % len(digest)]
            vec[i] += (b / 127.5) - 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def evaluate_drift(mission: str, next_action: str) -> float:
    if not mission or not next_action:
        return 0.0
    v1 = _local_embed(mission)
    v2 = _local_embed(next_action)
    dot = sum(x * y for x, y in zip(v1, v2))
    return max(0.0, 1.0 - dot)


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
    mission: str = "",
    owner: str = "operator",
    privacy_class: str = "internal",
    open_risks: Iterable[str] = (),
    evidence_refs: Iterable[Mapping[str, Any]] = (),
    deletion_path: str = "",
) -> Dict[str, Any]:
    """Create a bounded resume receipt; raw evidence stays outside the prompt."""
    if verification_status not in {"verified", "provisional"}:
        raise ValueError("verification_status must be verified or provisional")
    if not _meaningful(objective) or not _meaningful(next_action):
        raise ValueError("capsule objective and next_action must be specific, not placeholders")
    verified_items = [str(x).strip() for x in verified if str(x).strip()]
    if verification_status == "verified":
        if not verified_items or not all(_meaningful(x) for x in verified_items):
            raise ValueError("verified capsule needs at least one specific verified fact")
    pc = (privacy_class or "internal").strip().lower()
    if pc not in _PRIVACY_CLASSES:
        raise ValueError(f"privacy_class must be one of {sorted(_PRIVACY_CLASSES)}")

    capsule = {
        "objective": objective.strip(),
        "constraints": [str(x).strip() for x in constraints if str(x).strip()],
        "decisions": [str(x).strip() for x in decisions if str(x).strip()],
        "artifacts": [dict(x) for x in artifacts],
        "verified": verified_items,
        "current_defect": current_defect.strip(),
        "next_action": next_action.strip(),
        "verification_status": verification_status,
        "owner": (owner or "operator").strip()[:64],
        "privacy_class": pc,
        "open_risks": [str(x).strip() for x in open_risks if str(x).strip()],
        "evidence_refs": [dict(x) for x in evidence_refs],
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if deletion_path.strip():
        capsule["deletion_path"] = deletion_path.strip()

    if mission:
        capsule["mission"] = mission.strip()
        drift_score = evaluate_drift(capsule["mission"], objective + "\n" + next_action)
        capsule["drift_score"] = round(drift_score, 4)
        if drift_score >= 0.7:
            capsule["drift_status"] = "quarantine"
        elif drift_score >= 0.4:
            capsule["drift_status"] = "warn"
        else:
            capsule["drift_status"] = "ok"

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
    try:
        from aegis.relay import append_continuity_event

        append_continuity_event({
            "kind": "capsule",
            "fingerprint": capsule.get("fingerprint"),
            "verification_status": capsule.get("verification_status"),
            "owner": capsule.get("owner"),
            "privacy_class": capsule.get("privacy_class"),
            "drift_status": capsule.get("drift_status"),
            "path": str(path),
        })
    except Exception:  # noqa: BLE001
        pass
    return path


def load_latest_capsule() -> Optional[Dict[str, Any]]:
    """Load the newest capsule only when its JSON and fingerprint are intact."""
    directory = context_capsules_dir()
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if not paths:
        return None
    path = paths[-1]
    try:
        capsule = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"latest context capsule is corrupt: {path}") from exc
    if not isinstance(capsule, dict):
        raise ValueError(f"latest context capsule is not an object: {path}")
    fingerprint = capsule.get("fingerprint")
    unsigned = {key: value for key, value in capsule.items() if key not in {"tokens", "fingerprint"}}
    text = json.dumps(unsigned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    if fingerprint != expected:
        raise ValueError(f"latest context capsule fingerprint mismatch: {path}")
    if capsule.get("verification_status") not in {"verified", "provisional"}:
        raise ValueError(f"latest context capsule has invalid verification status: {path}")
    return capsule
