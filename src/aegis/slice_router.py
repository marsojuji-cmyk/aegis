"""Route packing by language — tree-sitter first for py/js/ts when available."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis import ast_slice
from aegis import csharp_slice
from aegis import go_slice
from aegis import java_slice
from aegis import kotlin_slice
from aegis import rust_slice
from aegis import ts_slice
from aegis.lang import detect_lang
from aegis.pack_cache import normalize_mode
from aegis.treesitter_backend import pack_with_treesitter, treesitter_available


def pack_file(
    path: str,
    source: str,
    mode: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lang = detect_lang(path, source)
    mode = normalize_mode(mode or "explore")
    meta: Dict[str, Any] = {
        "lang": lang,
        "path": path,
        "mode": mode,
        "treesitter": treesitter_available(),
    }

    # Harden py/js/ts/tsx with tree-sitter when optional dep present
    if lang in ("python", "javascript", "typescript", "tsx"):
        ts_result = pack_with_treesitter(
            lang, source, mode, targets=targets, task=task
        )
        if ts_result is not None:
            text, m = ts_result
            meta.update(m)
            meta["slicer"] = m.get("slicer") or "tree-sitter"
            return text, meta
        meta["slicer"] = "fallback"

    if lang == "python":
        if mode == "implement":
            text, m = ast_slice.build_implement_payload(
                source, targets=targets, task=task
            )
            meta.update(m)
            meta["slicer"] = meta.get("slicer", "stdlib_ast")
            return text, meta
        if mode == "review":
            return ast_slice.build_review_payload(source), {
                **meta,
                "fidelity": "review",
                "slicer": "stdlib_ast",
            }
        return ast_slice.build_explore_payload(source), {
            **meta,
            "fidelity": "explore_sigs",
            "slicer": "stdlib_ast",
        }

    if lang in ("typescript", "javascript", "tsx"):
        if mode == "implement":
            text, m = ts_slice.build_implement_js(source, targets=targets, task=task)
            meta.update(m)
            meta["lang"] = lang
            meta["slicer"] = "regex"
            meta["grammar"] = "regex_fallback"
            return text, meta
        if mode == "review":
            return ts_slice.build_review_js(source), {
                **meta,
                "fidelity": "review",
                "slicer": "regex",
                "grammar": "regex_fallback",
            }
        return ts_slice.build_explore_js(source), {
            **meta,
            "fidelity": "explore_sigs",
            "slicer": "regex",
            "grammar": "regex_fallback",
        }

    if lang == "go":
        if mode == "implement":
            text, m = go_slice.build_implement_go(source, targets=targets, task=task)
            meta.update(m)
            return text, meta
        if mode == "review":
            return go_slice.build_review_go(source), {**meta, "fidelity": "review"}
        return go_slice.build_explore_go(source), {**meta, "fidelity": "explore_sigs"}

    if lang == "rust":
        if mode == "implement":
            text, m = rust_slice.build_implement_rust(
                source, targets=targets, task=task
            )
            meta.update(m)
            return text, meta
        if mode == "review":
            return rust_slice.build_review_rust(source), {**meta, "fidelity": "review"}
        return rust_slice.build_explore_rust(source), {
            **meta,
            "fidelity": "explore_sigs",
        }

    if lang == "java":
        if mode == "implement":
            text, m = java_slice.build_implement_java(
                source, targets=targets, task=task
            )
            meta.update(m)
            return text, meta
        if mode == "review":
            return java_slice.build_review_java(source), {**meta, "fidelity": "review"}
        return java_slice.build_explore_java(source), {
            **meta,
            "fidelity": "explore_sigs",
        }

    if lang == "kotlin":
        if mode == "implement":
            text, m = kotlin_slice.build_implement_kotlin(
                source, targets=targets, task=task
            )
            meta.update(m)
            return text, meta
        if mode == "review":
            return kotlin_slice.build_review_kotlin(source), {
                **meta,
                "fidelity": "review",
            }
        return kotlin_slice.build_explore_kotlin(source), {
            **meta,
            "fidelity": "explore_sigs",
        }

    if lang == "csharp":
        if mode == "implement":
            text, m = csharp_slice.build_implement_csharp(
                source, targets=targets, task=task
            )
            meta.update(m)
            return text, meta
        if mode == "review":
            return csharp_slice.build_review_csharp(source), {
                **meta,
                "fidelity": "review",
            }
        return csharp_slice.build_explore_csharp(source), {
            **meta,
            "fidelity": "explore_sigs",
        }

    # scrub-only fallback for remaining langs (tree-sitter not applied)
    if mode == "implement":
        return source, {
            **meta,
            "fidelity": "full_file_scrub_only",
            "slicer": "none",
        }
    if mode == "review" and (
        source.lstrip().startswith("diff ") or "\n@@" in source
    ):
        return source, {**meta, "fidelity": "diff", "slicer": "none"}
    lines = source.splitlines()
    keep: List[str] = []
    for ln in lines:
        s = ln.strip()
        if any(
            s.startswith(p)
            for p in (
                "package ",
                "import ",
                "using ",
                "namespace ",
                "from ",
                "export ",
                "func ",
                "fn ",
                "pub ",
                "class ",
                "struct ",
                "interface ",
                "type ",
                "def ",
            )
        ):
            keep.append(ln.rstrip())
    if len(keep) < 5:
        keep = [ln for ln in lines if ln.strip()][:40]
    return "\n".join(keep), {
        **meta,
        "fidelity": "explore_heuristic",
        "slicer": "scrub_only",
    }
