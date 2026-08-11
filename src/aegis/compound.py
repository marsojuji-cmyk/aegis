"""Compound engine matrix — structured languages + slicer backends (v1.0)."""

from __future__ import annotations

from typing import Any, Dict, List

from aegis.lang import FIRST_CLASS, STRUCTURED
from aegis.treesitter_backend import treesitter_available, tsx_status


def language_matrix() -> List[Dict[str, Any]]:
    """Return first-class + structured language capabilities."""
    ts = treesitter_available()
    tsx = tsx_status() if ts else {"validated": False}
    rows = [
        {"lang": "python", "slicer": "tree-sitter|stdlib_ast", "tier": "first_class"},
        {"lang": "javascript", "slicer": "tree-sitter|regex", "tier": "first_class"},
        {"lang": "typescript", "slicer": "tree-sitter|regex", "tier": "first_class"},
        {
            "lang": "tsx",
            "slicer": "tree-sitter-tsx|typescript|regex",
            "tier": "first_class",
            "tsx_validated": bool(tsx.get("validated")),
        },
        {"lang": "java", "slicer": "regex_java", "tier": "structured"},
        {"lang": "kotlin", "slicer": "regex_kotlin", "tier": "structured"},
        {"lang": "csharp", "slicer": "regex_csharp", "tier": "structured"},
        {"lang": "go", "slicer": "regex_go", "tier": "structured"},
        {"lang": "rust", "slicer": "regex_rust", "tier": "structured"},
    ]
    for r in rows:
        r["structured"] = r["lang"] in STRUCTURED or r["lang"] == "tsx"
        r["treesitter"] = ts and r["lang"] in (
            "python",
            "javascript",
            "typescript",
            "tsx",
        )
    return rows


def compound_status() -> Dict[str, Any]:
    matrix = language_matrix()
    return {
        "version_target": "1.0.0",
        "structured_count": len(STRUCTURED) + (1 if "tsx" not in STRUCTURED else 0),
        "first_class": sorted(FIRST_CLASS | {"typescript", "javascript", "tsx"}),
        "treesitter_active": treesitter_available(),
        "tsx_validated": bool(tsx_status().get("validated"))
        if treesitter_available()
        else False,
        "matrix": matrix,
        "pipeline": [
            "preflight",
            "pack",
            "quality",
            "receipt",
            "output_lane",
            "shrink_store_reuse",
            "ledger",
            "router",
            "cursor",
        ],
    }
