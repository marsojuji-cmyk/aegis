"""Output reduce profiles — instruction blocks for quantized replies."""

from __future__ import annotations

from typing import Dict

PROFILES: Dict[str, str] = {
    "diff": (
        "OUTPUT PROFILE: diff\n"
        "- Reply ONLY with unified diffs or search-replace hunks.\n"
        "- No preamble, no closing summary, no apologies.\n"
        "- If no code change needed, reply with a single line: NO_CHANGE\n"
    ),
    "json": (
        "OUTPUT PROFILE: json\n"
        "- Reply with a single valid JSON object only.\n"
        "- No markdown fences, no prose before/after.\n"
        '- Prefer keys: {"summary":"...","actions":[],"files":[]}\n'
    ),
    "brief": (
        "OUTPUT PROFILE: brief\n"
        "- Max {max_tokens} tokens.\n"
        "- At most 3 short sentences, then optional bullets.\n"
        "- No filler openings (skip Sure/Happy to help).\n"
        "- Prefer actions and file paths over explanations.\n"
    ),
}


def render_profile(name: str, max_tokens: int = 800) -> str:
    key = name.strip().lower()
    if key not in PROFILES:
        raise ValueError(f"unknown profile {name!r}; choose from {sorted(PROFILES)}")
    return PROFILES[key].format(max_tokens=max_tokens)


def estimated_raw_out(profile: str, max_tokens: int) -> int:
    """Heuristic 'verbose default' vs profile budget for savings estimates."""
    # Assume unconstrained chatty reply ~ 3x profile max
    return max_tokens * 3


def estimated_processed_out(profile: str, max_tokens: int) -> int:
    return max_tokens
