"""Multi-lang waste scrub (E3) — product QC, no language-specific breakage."""

from __future__ import annotations

import re
from typing import Dict, Tuple

from aegis.lang import detect_lang


def scrub(text: str, lang: str = "unknown") -> Tuple[str, Dict[str, int]]:
    """
    Strip comment/license noise and blank padding.
    Preserves code structure. Safe default for unknown langs.
    """
    initial = len(text)
    cleaned = text

    # Block comments (C-like + CSS + many langs)
    if lang not in ("python",):  # python handled with care below
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)

    if lang == "python":
        # module/long docstrings (triple quotes) — keep short one-liners? strip multi-line
        cleaned = re.sub(r'^[ \t]*("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', "", cleaned, flags=re.M)
        # also /* */ if present
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)
        # full-line # comments (not shebang)
        cleaned = re.sub(r"(?m)^[ \t]*#(?!!).*$", "", cleaned)
    elif lang in (
        "javascript",
        "typescript",
        "java",
        "kotlin",
        "go",
        "rust",
        "c",
        "cpp",
        "csharp",
        "swift",
    ):
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)
        cleaned = re.sub(r"(?m)^[ \t]*//.*$", "", cleaned)
    elif lang == "shell":
        cleaned = re.sub(r"(?m)^[ \t]*#(?!!).*$", "", cleaned)
    elif lang == "ruby":
        cleaned = re.sub(r"(?m)^[ \t]*#.*$", "", cleaned)
        cleaned = re.sub(r"=begin[\s\S]*?=end", "", cleaned)
    elif lang in ("json", "toml", "yaml"):
        # minimal: only blank squeeze
        pass
    else:
        # unknown: try both // and # full-line + block
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)
        cleaned = re.sub(r"(?m)^[ \t]*//.*$", "", cleaned)
        cleaned = re.sub(r"(?m)^[ \t]*#(?!!).*$", "", cleaned)

    # license-y header boxes often use = or * lines
    cleaned = re.sub(r"(?m)^[ \t]*[*=#/-]{8,}[ \t]*$", "", cleaned)

    # consecutive blank lines → one
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    # trailing spaces
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)

    cleaned = cleaned.strip()
    final = len(cleaned)
    saved = initial - final
    return cleaned, {
        "initial_chars": initial,
        "final_chars": final,
        "chars_saved": saved,
        "tokens_saved": int(saved / 4.0),
        "lang": lang,
    }


def scrub_path(path: str, text: str) -> Tuple[str, Dict[str, int]]:
    lang = detect_lang(path, text)
    scrubbed, stats = scrub(text, lang)
    stats["lang"] = lang
    return scrubbed, stats
