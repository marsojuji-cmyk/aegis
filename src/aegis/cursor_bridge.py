"""
Cursor composer bridge — route edits through Aegis 10x pipeline.

Provides:
  - context pack for Composer (@files → preflight bento)
  - run through universal router (optional model)
  - access to unified output store index
  - .cursorrules / .cursorignore install
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aegis.output_store import load_output, store_stats
from aegis.paths import aegis_home, ensure_home, outputs_dir
from aegis.preflight import run_preflight
from aegis.router_pipeline import run_pipeline

CURSORRULES = """# Aegis Absolute — Cursor Composer Protocol (v1.0)

You co-own craft with the user. Tokenomics is material, not a soft guideline.
Tune: austere · aggressive on drift · protective weekly reserve (≥80%).

## Continuity rules
1. For every long or multi-file coding task, begin with `python3 -m aegis continuity start --task "<intent>" --mode implement path [path...]`. This is the default; dashboards are not part of the task path.
2. At checkpoint/compact, write a concise verified receipt with `aegis continuity checkpoint --objective ... --verified ... --next-action ...` and use JIT packs only.
3. At transfer, start a clean task from the capsule; do not drag opaque chat history forward.

## Hard rules
1. Tokens are finite inventory. Waste is failure. Prefer Aegis packs over whole-file dumps.
2. Before multi-file edits, use `aegis continuity start` above. `aegis cursor` and `aegis preflight` remain lower-level escape hatches.
3. Use pack receipt + bento context from that command. Do NOT re-read entire trees already packed.
4. Output ONLY diffs / search-replace hunks / minimal JSON. Zero filler ("Sure", "Happy to help").
5. After completing an edit, land the final reply body:
   `python3 -m aegis land --body-file /tmp/cursor_final.txt --summary "<what shipped>"`
   (or pipe Composer output). This shrinks, stores, and reuses via `~/.aegis/outputs/out_*.json`.
6. Check budget before heavy fan-out: `python3 -m aegis budget`
   If reserve is throttle/hard_stop: explore/reuse only — no invest, no parallel agents.
7. Prefer symbols and active diffs. implement mode = full target bodies only (never skeleton-only on edits).
8. Unified index access:
   - list: `python3 -m aegis cursor outputs`
   - get:  `python3 -m aegis output-get out_<id>`
9. Optional live model route (mock/ollama/grok/claude/openai):
   `python3 -m aegis cursor --task "..." --model mock --mode implement <files>`
10. Absolute Form: peer standard. No enthusiasm theater. Show naive vs Aegis cost when material.

## Router daemon (optional)
If `aegis serve` is running at http://127.0.0.1:8787, prefer it for OpenAI-compatible calls
with body.aegis.pipeline=true and body.aegis.paths=[...].

## Data plane
- Packs:   ~/.aegis/packs/
- Outputs: ~/.aegis/outputs/out_*.json  (unified slim index)
- Ledger:  ~/.aegis/ledger.jsonl
"""

CURSORIGNORE = """# Aegis — keep Cursor index lean (token + CPU)
node_modules/
.git/
.venv/
venv/
dist/
build/
__pycache__/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.log
*.sqlite
*.db
*.bin
*.png
*.jpg
*.jpeg
*.gif
*.svg
*.webp
*.mp4
*.zip
*.tar
*.gz
.DS_Store
.aegis/
**/.aegis/
"""


def install_cursor_rules(
    target_dir: Optional[str] = None,
    *,
    also_home: bool = False,
) -> Dict[str, Any]:
    """Write .cursorrules + .cursorignore. Returns paths written."""
    written: List[str] = []
    dirs: List[Path] = []
    if target_dir:
        dirs.append(Path(target_dir).expanduser().resolve())
    else:
        dirs.append(Path.cwd().resolve())
    # Always install into product repo when available
    product = Path.home() / "Projects" / "aegis"
    if product.is_dir() and product not in dirs:
        dirs.append(product)
    if also_home:
        home_cursor = Path.home() / ".cursor"
        home_cursor.mkdir(parents=True, exist_ok=True)
        # global-ish rules file some setups read
        global_rules = home_cursor / "aegis.cursorrules"
        global_rules.write_text(CURSORRULES, encoding="utf-8")
        written.append(str(global_rules))

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        rules = d / ".cursorrules"
        ignore = d / ".cursorignore"
        rules.write_text(CURSORRULES, encoding="utf-8")
        ignore.write_text(CURSORIGNORE, encoding="utf-8")
        written.extend([str(rules), str(ignore)])

    # integrations mirror
    integ = Path.home() / "Projects" / "aegis" / "integrations" / "cursor"
    integ.mkdir(parents=True, exist_ok=True)
    (integ / "cursorrules").write_text(CURSORRULES, encoding="utf-8")
    (integ / "cursorignore").write_text(CURSORIGNORE, encoding="utf-8")
    written.append(str(integ / "cursorrules"))
    return {"written": written, "count": len(written)}


def cursor_context(
    *,
    task: str,
    paths: Sequence[str],
    mode: str = "implement",
    targets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Run preflight and return Composer-ready context block + pack/receipt/output lane.
    """
    paths = [str(Path(p).expanduser().resolve()) for p in paths]
    pf = run_preflight(
        paths=paths,
        task=task,
        mode=mode,
        targets=list(targets or []),
        strict=False,
        no_output=False,
        recover=True,
    )
    payload = (pf.summary or {}).get("payload") or {}
    comps = payload.get("bento_components") or []
    bento_md = []
    for c in comps:
        bento_md.append(
            f"### {c.get('path')} [{c.get('lang')}] "
            f"{c.get('raw_tokens')}→{c.get('compressed_tokens')} tok\n"
            f"```\n{c.get('payload_snippet') or ''}\n```"
        )
    composer_block = "\n".join(
        [
            "[AEGIS CURSOR CONTEXT]",
            f"task={task}",
            f"mode={pf.mode_used} quality={pf.quality_grade} reserve={pf.reserve_signal}",
            f"pack_id={pf.pack_id}",
            f"output_profile={pf.output_profile}",
            "rule=edit from this pack only; land final with `aegis land --body-file …`",
            "",
            "## Bento",
            "\n".join(bento_md) if bento_md else "(no components)",
        ]
    )
    # write last cursor context for IDE pickup
    ensure_home()
    last = aegis_home() / "cursor_last_context.md"
    last.write_text(composer_block, encoding="utf-8")
    meta_path = aegis_home() / "cursor_last.json"
    meta = {
        "task": task,
        "mode": pf.mode_used,
        "pack_id": pf.pack_id,
        "quality": pf.quality_grade,
        "reserve": pf.reserve_signal,
        "paths": paths,
        "output_profile": pf.output_profile,
        "context_path": str(last),
        "outputs_dir": str(outputs_dir()),
        "ok": pf.ok,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {
        "ok": pf.ok,
        "composer_block": composer_block,
        "meta": meta,
        "preflight": pf.as_dict(),
    }


def cursor_run(
    *,
    task: str,
    paths: Sequence[str],
    mode: str = "implement",
    model: str = "mock",
    provider: str = "",
    targets: Optional[Sequence[str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Full Cursor edit route: preflight + optional model via universal router."""
    ctx = cursor_context(
        task=task, paths=paths, mode=mode, targets=targets
    )
    result = run_pipeline(
        task=task,
        model=model,
        provider=provider,
        paths=list(paths),
        mode=mode,
        targets=list(targets or []),
        prompt=task,
        profile="diff" if mode == "implement" else "brief",
        skip_preflight=True,  # already did cursor_context preflight
        dry_run=dry_run,
    )
    # attach prior pack id from context if run skipped pack
    if not result.pack_id:
        result.pack_id = (ctx.get("meta") or {}).get("pack_id")
    return {
        "context": ctx,
        "run": result.as_dict(),
        "outputs_dir": str(outputs_dir()),
    }


def list_cursor_outputs(limit: int = 20) -> List[Dict[str, Any]]:
    """List unified output index entries for Composer."""
    d = outputs_dir()
    if not d.is_dir():
        return []
    rows = []
    for p in sorted(d.glob("out_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "id": doc.get("id"),
                "profile": doc.get("profile"),
                "raw_tokens": doc.get("raw_tokens"),
                "shrunk_tokens": doc.get("shrunk_tokens"),
                "tokens_saved": doc.get("tokens_saved"),
                "summary": doc.get("summary"),
                "path": str(p),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def cursor_status() -> Dict[str, Any]:
    product_rules = Path.home() / "Projects" / "aegis" / ".cursorrules"
    cwd_rules = Path.cwd() / ".cursorrules"
    return {
        "cursorrules_product": product_rules.is_file(),
        "cursorrules_cwd": cwd_rules.is_file(),
        "outputs_dir": str(outputs_dir()),
        "store": store_stats(),
        "last_context": str(aegis_home() / "cursor_last_context.md"),
        "last_meta": str(aegis_home() / "cursor_last.json"),
        "router_hint": "python3 -m aegis serve --port 8787",
        "cli": "python3 -m aegis cursor --task '…' --mode implement <files>",
    }
