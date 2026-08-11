"""
Optional tree-sitter AST backend for Python / JavaScript / TypeScript / TSX.

Hardens slices when installed; other languages stay on regex slicers.
Enable/disable: AEGIS_TREE_SITTER=0 to force fallback.
TSX: validated against a React fixture before enable-by-default;
  fails open to TypeScript grammar, then regex via router.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_AVAILABLE = None
_PARSERS: Dict[str, Any] = {}
_TSX_VALIDATED: Optional[bool] = None
_TSX_VALIDATION_DETAIL: Dict[str, Any] = {}

# Minimal React fixture used once to gate TSX default enablement
_TSX_FIXTURE = """
import React from "react";

export function App(props: { title: string }): JSX.Element {
  return (
    <div className="app">
      <h1>{props.title}</h1>
      <Button onClick={() => null}>Go</Button>
    </div>
  );
}

export const Button = ({ children }: { children: React.ReactNode }) => {
  return <button type="button">{children}</button>;
};
"""


def treesitter_available() -> bool:
    global _AVAILABLE
    if os.environ.get("AEGIS_TREE_SITTER", "1").strip() in ("0", "false", "no"):
        return False
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        from tree_sitter import Language, Parser  # noqa: F401
        import tree_sitter_python  # noqa: F401
        import tree_sitter_javascript  # noqa: F401
        import tree_sitter_typescript  # noqa: F401

        _AVAILABLE = True
    except Exception:
        _AVAILABLE = False
    return _AVAILABLE


def _count_errors(node) -> int:
    n = 1 if node.type == "ERROR" else 0
    for c in node.children:
        n += _count_errors(c)
    return n


def _parser_for(lang: str):
    if lang in _PARSERS:
        return _PARSERS[lang]
    from tree_sitter import Language, Parser

    if lang == "python":
        import tree_sitter_python as tspy

        language = Language(tspy.language())
    elif lang == "javascript":
        import tree_sitter_javascript as tsjs

        language = Language(tsjs.language())
    elif lang == "typescript":
        import tree_sitter_typescript as tsts

        language = Language(tsts.language_typescript())
    elif lang == "tsx":
        import tree_sitter_typescript as tsts

        language = Language(tsts.language_tsx())
    else:
        raise ValueError(f"unsupported treesitter lang {lang}")
    parser = Parser(language)
    _PARSERS[lang] = parser
    return parser


def validate_tsx_grammar() -> bool:
    """
    Validate TSX grammar on a React fixture before enabling by default.
    Cached for process lifetime. Force off: AEGIS_TSX=0. Force on: AEGIS_TSX=1.
    """
    global _TSX_VALIDATED, _TSX_VALIDATION_DETAIL
    force = os.environ.get("AEGIS_TSX", "").strip().lower()
    if force in ("0", "false", "no"):
        _TSX_VALIDATED = False
        _TSX_VALIDATION_DETAIL = {"reason": "disabled_by_env", "ok": False}
        return False
    if force in ("1", "true", "yes"):
        _TSX_VALIDATED = True
        _TSX_VALIDATION_DETAIL = {"reason": "forced_on", "ok": True}
        return True
    if _TSX_VALIDATED is not None:
        return _TSX_VALIDATED
    if not treesitter_available():
        _TSX_VALIDATED = False
        _TSX_VALIDATION_DETAIL = {"reason": "treesitter_unavailable", "ok": False}
        return False
    try:
        parser = _parser_for("tsx")
        src = _TSX_FIXTURE.encode("utf-8")
        tree = parser.parse(src)
        errs = _count_errors(tree.root_node)
        units = _extract_js_units(src, tree.root_node)
        names = {u["name"] for u in units}
        # Must parse cleanly and see both components
        ok = errs == 0 and "App" in names and "Button" in names
        _TSX_VALIDATED = ok
        _TSX_VALIDATION_DETAIL = {
            "ok": ok,
            "errors": errs,
            "units": len(units),
            "names": sorted(names),
            "reason": "fixture_ok" if ok else "fixture_failed",
        }
    except Exception as exc:  # noqa: BLE001
        _TSX_VALIDATED = False
        _TSX_VALIDATION_DETAIL = {"ok": False, "reason": f"exception:{exc}"}
    return bool(_TSX_VALIDATED)


def tsx_status() -> Dict[str, Any]:
    """Doctor/status: validation detail (runs validation once if needed)."""
    validate_tsx_grammar()
    return {
        "validated": bool(_TSX_VALIDATED),
        "detail": dict(_TSX_VALIDATION_DETAIL),
    }


def _text(src: bytes, node) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _line_range(node) -> Tuple[int, int]:
    # tree-sitter points are 0-based rows
    return node.start_point[0] + 1, node.end_point[0] + 1


def _child_by_type(node, types: Sequence[str]):
    want = set(types)
    for c in node.children:
        if c.type in want:
            return c
    return None


def _name_from_node(src: bytes, node) -> str:
    # direct name field-ish: first identifier among named children
    for c in node.children:
        if c.type == "identifier" or c.type == "property_identifier" or c.type == "type_identifier":
            return _text(src, c)
        if c.type == "name":  # some grammars
            return _text(src, c)
    # method_definition: name often property_identifier
    for c in node.children:
        if "identifier" in c.type:
            return _text(src, c)
    return "anon"


def _extract_python_units(src: bytes, root) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    lines = src.decode("utf-8", errors="replace").splitlines()

    def walk(node, stack: List[str]) -> None:
        ntype = node.type
        if ntype == "decorated_definition":
            # peel to inner def/class
            for c in node.children:
                if c.type in ("function_definition", "class_definition", "async_function_definition"):
                    walk(c, stack)
            return
        if ntype in ("function_definition", "async_function_definition", "class_definition"):
            name = _name_from_node(src, node)
            qn = ".".join(stack + [name]) if stack else name
            start, end = _line_range(node)
            # include decorators: if parent is decorated_definition, expand start
            sig = lines[start - 1].rstrip() if 0 < start <= len(lines) else name
            kind = "class" if ntype == "class_definition" else "def"
            units.append(
                {
                    "name": name,
                    "qualname": qn,
                    "kind": kind,
                    "start": start,
                    "end": end,
                    "sig_line": sig,
                }
            )
            if ntype == "class_definition":
                for c in node.children:
                    walk(c, stack + [name])
                return
        for c in node.children:
            walk(c, stack)

    walk(root, [])
    return units


def _extract_js_units(src: bytes, root) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    lines = src.decode("utf-8", errors="replace").splitlines()
    interesting = {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "method_definition",
        "lexical_declaration",
        "export_statement",
    }

    def walk(node, stack: List[str]) -> None:
        ntype = node.type
        if ntype == "export_statement":
            for c in node.children:
                walk(c, stack)
            return
        if ntype in ("function_declaration", "generator_function_declaration"):
            name = _name_from_node(src, node)
            qn = ".".join(stack + [name]) if stack else name
            start, end = _line_range(node)
            units.append(
                {
                    "name": name,
                    "qualname": qn,
                    "kind": "function",
                    "start": start,
                    "end": end,
                    "sig_line": lines[start - 1].rstrip() if start <= len(lines) else name,
                }
            )
            return
        if ntype == "class_declaration":
            name = _name_from_node(src, node)
            qn = ".".join(stack + [name]) if stack else name
            start, end = _line_range(node)
            units.append(
                {
                    "name": name,
                    "qualname": qn,
                    "kind": "class",
                    "start": start,
                    "end": end,
                    "sig_line": lines[start - 1].rstrip() if start <= len(lines) else name,
                }
            )
            for c in node.children:
                walk(c, stack + [name])
            return
        if ntype == "method_definition":
            name = _name_from_node(src, node)
            qn = ".".join(stack + [name]) if stack else name
            start, end = _line_range(node)
            units.append(
                {
                    "name": name,
                    "qualname": qn,
                    "kind": "method",
                    "start": start,
                    "end": end,
                    "sig_line": lines[start - 1].rstrip() if start <= len(lines) else name,
                }
            )
            return
        if ntype == "lexical_declaration":
            # const foo = (...) => {} or function
            text = _text(src, node)
            m = re.search(
                r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>|\w+\s*=>)",
                text,
            )
            if m:
                name = m.group(1)
                qn = ".".join(stack + [name]) if stack else name
                start, end = _line_range(node)
                units.append(
                    {
                        "name": name,
                        "qualname": qn,
                        "kind": "const_fn",
                        "start": start,
                        "end": end,
                        "sig_line": lines[start - 1].rstrip() if start <= len(lines) else name,
                    }
                )
            return
        for c in node.children:
            if c.type in interesting or c.child_count:
                walk(c, stack)

    walk(root, [])
    return units


def extract_units_ts(lang: str, source: str) -> List[Dict[str, Any]]:
    parse_lang = lang if lang != "tsx" else "tsx"
    parser = _parser_for(parse_lang)
    src = source.encode("utf-8")
    tree = parser.parse(src)
    if lang == "python":
        return _extract_python_units(src, tree.root_node)
    return _extract_js_units(src, tree.root_node)


def extract_imports_ts(lang: str, source: str) -> List[str]:
    if lang == "python":
        out = []
        for line in source.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                out.append(line.rstrip())
        return out
    out = []
    for line in source.splitlines():
        s = line.strip()
        # Module imports only — not `export function` / `export class`
        if s.startswith("import "):
            out.append(line.rstrip())
        elif s.startswith("export ") and (
            " from " in s
            or s.startswith("export *")
            or s.startswith("export {")
            or s.startswith("export type {")
        ):
            out.append(line.rstrip())
        elif "require(" in s and (
            s.startswith("const ") or s.startswith("var ") or s.startswith("let ")
        ):
            out.append(line.rstrip())
    return out


def _match_targets(units: List[Dict[str, Any]], targets: Sequence[str]) -> Set[str]:
    if not targets:
        return set()
    wanted = {t.strip() for t in targets if t and t.strip()}
    matched: Set[str] = set()
    for u in units:
        for t in wanted:
            if (
                t == u["qualname"]
                or t == u["name"]
                or t.lower() == u["name"].lower()
                or t in u["qualname"]
            ):
                matched.add(u["qualname"])
    return matched


def _infer(task: str, units: List[Dict[str, Any]]) -> Set[str]:
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", task or ""))
    return {u["qualname"] for u in units if u["name"] in tokens}


def build_explore(lang: str, source: str) -> Tuple[str, Dict[str, Any]]:
    units = extract_units_ts(lang, source)
    imports = extract_imports_ts(lang, source)
    parts: List[str] = []
    if imports:
        parts.append("// imports" if lang != "python" else "# imports")
        parts.extend(imports)
    if units:
        parts.append("// signatures" if lang != "python" else "# signatures")
        for u in units:
            mark = "#" if lang == "python" else "//"
            parts.append(f"{u['sig_line']}  {mark} {u['qualname']} L{u['start']}-{u['end']}")
    meta = {"slicer": "tree-sitter", "lang": lang, "units": len(units), "fidelity": "explore_sigs"}
    if not parts:
        return "\n".join(ln for ln in source.splitlines() if ln.strip())[:40], meta
    return "\n".join(parts), meta


def build_implement(
    lang: str,
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_units_ts(lang, source)
    meta: Dict[str, Any] = {
        "slicer": "tree-sitter",
        "lang": lang,
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
    }
    if not units:
        return source, meta
    resolved = _match_targets(units, targets or [])
    if not resolved:
        resolved = _infer(task, units)
    if not resolved:
        meta["fidelity"] = "full_file"
        return source, meta
    meta["targets_resolved"] = sorted(resolved)
    meta["fidelity"] = "target_bodies"
    imports = extract_imports_ts(lang, source)
    mark = "#" if lang == "python" else "//"
    parts: List[str] = []
    if imports:
        parts.append(f"{mark} imports")
        parts.extend(imports)
    neighbors = [u for u in units if u["qualname"] not in resolved]
    if neighbors:
        parts.append(f"{mark} neighbor signatures")
        for u in neighbors:
            parts.append(f"{u['sig_line']}  {mark} {u['qualname']}")
    parts.append(f"{mark} implement targets (full bodies)")
    for u in sorted((x for x in units if x["qualname"] in resolved), key=lambda x: x["start"]):
        parts.append(f"{mark} --- {u['qualname']} L{u['start']}-{u['end']} ---")
        parts.append("\n".join(lines[u["start"] - 1 : u["end"]]))
    return "\n".join(parts), meta


def build_review(lang: str, source: str) -> Tuple[str, Dict[str, Any]]:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source, {"slicer": "tree-sitter", "lang": lang, "fidelity": "diff"}
    text, meta = build_explore(lang, source)
    meta["fidelity"] = "review"
    return text, meta


def _build_mode(
    lang: str,
    source: str,
    mode: str,
    targets: Optional[Sequence[str]],
    task: str,
) -> Tuple[str, Dict[str, Any]]:
    if mode == "implement":
        return build_implement(lang, source, targets=targets, task=task)
    if mode == "review":
        return build_review(lang, source)
    return build_explore(lang, source)


def pack_with_treesitter(
    lang: str,
    source: str,
    mode: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Return (text, meta) or None if unavailable / unsupported.

    TSX path (minimize risk):
      1) If TSX grammar validated → parse as tsx
      2) Else try TypeScript grammar (may degrade on JSX)
      3) Else None → router regex fallback
    """
    if lang not in ("python", "javascript", "typescript", "tsx"):
        return None
    if not treesitter_available():
        return None

    # --- TSX safe chain ---
    if lang == "tsx":
        # 1) validated TSX grammar
        if validate_tsx_grammar():
            try:
                text, meta = _build_mode("tsx", source, mode, targets, task)
                meta["grammar"] = "tsx"
                meta["tsx_validated"] = True
                return text, meta
            except Exception:
                pass  # fall through to typescript
        # 2) TypeScript grammar fallback (clear, lower fidelity on JSX)
        try:
            text, meta = _build_mode("typescript", source, mode, targets, task)
            meta["grammar"] = "typescript_fallback"
            meta["tsx_validated"] = bool(_TSX_VALIDATED)
            meta["slicer"] = "tree-sitter"
            meta["lang"] = "tsx"
            meta["fallback"] = "typescript"
            return text, meta
        except Exception:
            return None

    try:
        text, meta = _build_mode(lang, source, mode, targets, task)
        meta["grammar"] = lang
        return text, meta
    except Exception:
        return None
