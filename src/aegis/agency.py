"""Bounded agency bands: reflective, assistive, autonomous."""

from __future__ import annotations

from typing import Optional, Tuple

AGENCY_MODES = ("reflective", "assistive", "autonomous")

READ_CAPABILITIES = frozenset({
    "fs.read",
    "net.search",
    "session.read",
    "skill.read",
    "project.read",
})

STAGE_CAPABILITIES = frozenset({
    "fs.write",
    "session.write",
    "skill.write",
    "project.write",
})

CONSEQUENTIAL_CAPABILITIES = frozenset({
    "net.browser",
    "exec.shell",
    "sched.write",
    "net.fetch",
})

ACTION_ALLOW = "allow"
ACTION_STAGE = "stage"
ACTION_CONFIRM = "confirm"
ACTION_DENY = "deny"


def normalize_mode(mode: str) -> str:
    m = (mode or "assistive").strip().lower()
    if m not in AGENCY_MODES:
        return "assistive"
    return m


def classify_action(
    capability: Optional[str],
    risk: Optional[str],
    *,
    durable_memory: bool = False,
) -> str:
    """Map capability + risk to allow | stage | confirm | deny."""
    cap = str(capability or "")
    r = str(risk or "medium").lower()
    if not cap:
        return ACTION_DENY
    if durable_memory and cap == "memory.write":
        return ACTION_CONFIRM
    if cap in CONSEQUENTIAL_CAPABILITIES or r == "high":
        return ACTION_CONFIRM
    if cap in STAGE_CAPABILITIES or r == "medium":
        return ACTION_STAGE
    if cap in READ_CAPABILITIES or r == "low":
        return ACTION_ALLOW
    return ACTION_STAGE


def mode_allows(mode: str, action_class: str) -> Tuple[bool, str]:
    """Return (permitted, reason). confirm → require-review at gate."""
    m = normalize_mode(mode)
    ac = action_class
    if ac == ACTION_DENY:
        return False, "action class denied"
    if m == "reflective":
        if ac == ACTION_ALLOW:
            return True, "reflective read-only allow"
        return False, f"reflective mode blocks {ac}"
    if m == "assistive":
        if ac in {ACTION_ALLOW, ACTION_STAGE}:
            return True, f"assistive permits {ac}"
        return False, f"assistive requires review for {ac}"
    if m == "autonomous":
        if ac == ACTION_ALLOW:
            return True, "autonomous pre-approved allow"
        return False, f"autonomous band blocks {ac} without workflow allowlist"
    return False, "unknown agency mode"


def gate_decision(
    mode: str,
    capability: Optional[str],
    risk: Optional[str],
    *,
    durable_memory: bool = False,
) -> Tuple[str, str]:
    """
    Returns (decision, reason) where decision is allow | require-review | deny.
    """
    action = classify_action(capability, risk, durable_memory=durable_memory)
    allowed, reason = mode_allows(mode, action)
    if allowed and action == ACTION_ALLOW:
        return "allow", reason
    if allowed and action == ACTION_STAGE:
        return "allow", f"{reason}; staged execution permitted"
    if action == ACTION_CONFIRM:
        return "require-review", reason or f"confirm required for {capability}"
    return "deny", reason
