"""Language detection for multi-lang packing (E3)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# ext → language id
EXT_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".c": "c",
    ".md": "markdown",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
}

# languages with structure slicers (beyond scrub-only)
STRUCTURED = frozenset(
    {
        "python",
        "typescript",
        "tsx",
        "javascript",
        "go",
        "rust",
        "java",
        "csharp",
        "kotlin",
    }
)

# JVM family for compound engine routing hints
JVM_LANGS = frozenset({"java", "kotlin", "csharp"})
FIRST_CLASS = frozenset(
    {"python", "javascript", "typescript", "tsx", "java", "kotlin"}
)


def detect_lang(path: str, content: str = "") -> str:
    ext = Path(path).suffix.lower()
    if ext in EXT_MAP:
        return EXT_MAP[ext]
    head = (content or "")[:240]
    if "fun " in head and ("package " in head or "import " in head):
        return "kotlin"
    if "def " in head and "import " in head:
        return "python"
    if "function " in head or "=>" in head or "export " in head:
        return "javascript"
    if "public class " in head or "package " in head and ";" in head:
        return "java"
    return "unknown"


def has_structure_slicer(lang: str) -> bool:
    return lang in STRUCTURED
