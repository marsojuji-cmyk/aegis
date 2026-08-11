"""Honest token estimates — count code, not Aegis annotation chrome."""

from __future__ import annotations

import re
from typing import Iterable

# Lines that are pack metadata, not model-useful code body
_ANNOTATION = re.compile(
    r"^\s*("
    r"//\s*---|"  # // --- qualname ---
    r"#\s*---|"
    r"//\s*(imports|signatures|neighbor|package|using|use/mod|implement targets|package/imports|using/namespace)\b|"
    r"#\s*(imports|signatures|neighbor|implement targets)\b|"
    r"//\s*…|"
    r"#\s*…"
    r")"
)

# Trailing slicer comments: "  // Foo.bar L1-2" or "  # Foo L1-2"
_TRAIL_META = re.compile(r"\s+(?://|#)\s+[\w.<>]+\s+L\d+-\d+\s*$")


def strip_annotations(text: str) -> str:
    """Remove pack annotation lines and trailing Lstart-end meta comments."""
    if not text:
        return ""
    out = []
    for line in text.splitlines():
        if _ANNOTATION.match(line):
            continue
        # drop pure section headers we might have missed
        s = line.strip()
        if s in (
            "// imports",
            "# imports",
            "// signatures",
            "# signatures",
            "// neighbor signatures",
            "# neighbor signatures",
            "// implement targets (full bodies)",
            "# implement targets (full bodies)",
            "// package/imports",
            "// using/namespace",
            "// use/mod",
        ):
            continue
        cleaned = _TRAIL_META.sub("", line)
        out.append(cleaned)
    return "\n".join(out).strip()


def estimate_tokens(text: str) -> int:
    """Rough tokens: ~4 chars per token on full text."""
    return max(0, int(len(text) / 4.0))


def estimate_code_tokens(text: str) -> int:
    """Tokens after stripping pack annotations (ledger/gate honesty)."""
    return estimate_tokens(strip_annotations(text))


def estimate_many(texts: Iterable[str], *, code_only: bool = False) -> int:
    fn = estimate_code_tokens if code_only else estimate_tokens
    return sum(fn(t) for t in texts)
