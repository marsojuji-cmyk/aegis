"""Mode-aware multi-lang bento assembler (E3)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from aegis.slice_router import pack_file
from aegis.scrub import scrub_path
from aegis.tokens import estimate_code_tokens, estimate_tokens


def assemble(
    *,
    core_task: str,
    code_snippets: List[Dict[str, str]],
    mode: str = "explore",
    targets: Optional[Sequence[str]] = None,
    max_token_budget: int = 8192,
) -> Dict[str, Any]:
    """
    Assemble bento by mode + language.

    Compressed token counts use code-only estimate (annotations excluded).
    """
    start = time.time()
    mode = (mode or "explore").lower()
    components: List[Dict[str, Any]] = []
    # Task counted once as raw demand; not re-counted as compressed body
    total_raw = estimate_tokens(core_task)
    total_comp = 0
    total_comp_raw_annotated = 0
    fidelity_notes: List[Dict[str, Any]] = []
    langs: List[str] = []

    for item in code_snippets:
        path = item.get("path", "unknown")
        content = item.get("content", "")
        raw_tkn = estimate_tokens(content)

        scrubbed, scrub_stats = scrub_path(path, content)
        src = scrubbed if scrubbed.strip() else content
        lang = scrub_stats.get("lang", "unknown")
        langs.append(str(lang))

        payload_text, meta = pack_file(
            path, src, mode, targets=targets, task=core_task
        )
        if mode == "implement" and not payload_text.strip():
            payload_text = src
            meta["fidelity"] = "full_file_fallback"

        fidelity_notes.append({"path": path, **meta})

        annotated_tkn = estimate_tokens(payload_text)
        comp_tkn = estimate_code_tokens(payload_text)
        if mode == "explore" and comp_tkn > max_token_budget:
            keep = payload_text.splitlines()[: max(20, max_token_budget // 8)]
            payload_text = "\n".join(keep) + "\n// …truncated for budget"
            annotated_tkn = estimate_tokens(payload_text)
            comp_tkn = estimate_code_tokens(payload_text)

        total_raw += raw_tkn
        total_comp += comp_tkn
        total_comp_raw_annotated += annotated_tkn
        components.append(
            {
                "path": path,
                "lang": lang,
                "raw_tokens": raw_tkn,
                "compressed_tokens": comp_tkn,
                "compressed_tokens_annotated": annotated_tkn,
                "reduction_percent": round(
                    (1 - (comp_tkn / (raw_tkn + 1e-5))) * 100, 1
                ),
                "payload_snippet": payload_text,
                "scrub_stats": scrub_stats,
            }
        )

    return {
        "core_task": core_task,
        "mode": mode,
        "engine": "product_e3",
        "languages": sorted(set(langs)),
        "slicers": sorted(
            {
                str(f.get("slicer") or "unknown")
                for f in fidelity_notes
            }
        ),
        "total_raw_tokens": total_raw,
        "total_compressed_tokens": total_comp,
        "total_compressed_annotated": total_comp_raw_annotated,
        "overall_reduction_percent": round(
            (1 - (total_comp / (total_raw + 1e-5))) * 100, 1
        ),
        "assembly_time_ms": round((time.time() - start) * 1000, 2),
        "bento_components": components,
        "fidelity": fidelity_notes,
        "targets": list(targets or []),
        "token_accounting": "code_only",
    }


def assert_implement_fidelity(
    source: str,
    payload: str,
    target_names: Sequence[str],
) -> bool:
    """Python fidelity helper (E2); still used by tests."""
    from aegis.ast_slice import extract_python_units, match_targets

    units = extract_python_units(source)
    resolved = match_targets(units, target_names)
    if not resolved:
        return len(payload) >= max(1, int(len(source) * 0.5))
    lines = source.splitlines()
    for u in units:
        if u["qualname"] not in resolved:
            continue
        body = "\n".join(lines[u["start"] - 1 : u["end"]])
        body_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if not body_lines:
            continue
        if body_lines[0] not in payload:
            return False
        if body_lines[-1] not in payload and len(body_lines) > 1:
            if f"def {u['name']}" not in payload and f"class {u['name']}" not in payload:
                return False
        must = body_lines[1:-1] if len(body_lines) > 2 else []
        hit = sum(1 for ln in must if ln in payload)
        if must and hit < max(1, int(len(must) * 0.8)):
            return False
    return True
