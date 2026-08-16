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
from typing import Any, Dict, List, Mapping, Optional, Sequence

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
11. If the composer block says `reuse=hit`, do not Read `packed_paths`. Use the bento.

## Flow (driver / car / track)
Driver = you. Car = Cursor (execute) + Perplexity (research). Track = One (repo + ~/.aegis + AGIS MUL).
Track first (`aegis hermes search`). Perplexity only for a live/external miss. Perplexity never edits. Cursor judges and lands. One research query. Freeze list unchanged. Skill: `aegis-flow`.

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


CURSOR_SKILL_NAMES = (
    "aegis-pack-first",
    "aegis-continuity",
    "aegis-sprint",
    "aegis-hermes",
    "aegis-flow",
)


def cursor_skills_src() -> Path:
    here = Path(__file__).resolve()
    repo = here.parents[2] / "integrations" / "cursor" / "skills"
    if repo.is_dir():
        return repo
    return Path.home() / "Projects" / "aegis" / "integrations" / "cursor" / "skills"


def agents_skills_dir() -> Path:
    raw = os.environ.get("AEGIS_AGENTS_SKILLS")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".agents" / "skills"


def install_cursor_skills(*, dest: Optional[Path] = None) -> List[str]:
    """Copy Cursor skills from the repo SoT into an agents skills dir."""
    src_root = cursor_skills_src()
    dest_root = Path(dest) if dest is not None else agents_skills_dir()
    written: List[str] = []
    for name in CURSOR_SKILL_NAMES:
        src = src_root / name / "SKILL.md"
        if not src.is_file():
            continue
        out = dest_root / name / "SKILL.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(str(out))
    return written


def installed_cursor_skills(*, dest: Optional[Path] = None) -> List[str]:
    root = Path(dest) if dest is not None else agents_skills_dir()
    found: List[str] = []
    for name in CURSOR_SKILL_NAMES:
        if (root / name / "SKILL.md").is_file():
            found.append(name)
    return found


def install_cursor_rules(
    target_dir: Optional[str] = None,
    *,
    also_home: bool = False,
) -> Dict[str, Any]:
    """Write .cursorrules + .cursorignore + Cursor skills."""
    written: List[str] = []
    dirs: List[Path] = []
    if target_dir:
        dirs.append(Path(target_dir).expanduser().resolve())
    else:
        dirs.append(Path.cwd().resolve())
        product = Path.home() / "Projects" / "aegis"
        if product.is_dir() and product not in dirs:
            dirs.append(product)
    if also_home:
        home_cursor = Path.home() / ".cursor"
        home_cursor.mkdir(parents=True, exist_ok=True)
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

    if not target_dir:
        integ = Path.home() / "Projects" / "aegis" / "integrations" / "cursor"
        integ.mkdir(parents=True, exist_ok=True)
        (integ / "cursorrules").write_text(CURSORRULES, encoding="utf-8")
        (integ / "cursorignore").write_text(CURSORIGNORE, encoding="utf-8")
        written.append(str(integ / "cursorrules"))

    skill_dest = (
        Path(target_dir).expanduser().resolve() / "skills" if target_dir else None
    )
    skills = install_cursor_skills(dest=skill_dest)
    written.extend(skills)
    return {"written": written, "count": len(written), "skills": skills}


NEIGHBOR_CAP = 3
NEIGHBOR_SUFFIXES = {".py", ".md", ".ts", ".js", ".tsx"}


def _resolve_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def last_cursor_meta_path() -> Path:
    return aegis_home() / "cursor_last.json"


def load_last_cursor_meta() -> Dict[str, Any]:
    path = last_cursor_meta_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def expand_pack_paths(paths: Sequence[str]) -> Dict[str, Any]:
    """Keep existing files. If none exist, add up to 3 same-dir neighbors."""
    existing: List[str] = []
    missing: List[str] = []
    for raw in paths:
        path = _resolve_path(str(raw))
        if path.is_file():
            existing.append(str(path))
        else:
            missing.append(str(path))
    neighbors: List[str] = []
    if existing:
        return {
            "paths": existing,
            "neighbors": neighbors,
            "missing": missing,
        }
    seen = set()
    for missed in missing:
        parent = Path(missed).parent
        init = parent / "__init__.py"
        if init.is_file():
            resolved = str(init.resolve())
            if resolved not in seen:
                neighbors.append(resolved)
                seen.add(resolved)
        if parent.is_dir():
            sibs = sorted(
                child
                for child in parent.iterdir()
                if child.is_file()
                and child.suffix in NEIGHBOR_SUFFIXES
                and child.name != "__init__.py"
            )
            for sib in sibs:
                if len(neighbors) >= NEIGHBOR_CAP:
                    break
                resolved = str(sib.resolve())
                if resolved not in seen:
                    neighbors.append(resolved)
                    seen.add(resolved)
        if len(neighbors) >= NEIGHBOR_CAP:
            break
    return {
        "paths": neighbors,
        "neighbors": neighbors,
        "missing": missing,
    }


def last_pack_covers(paths: Sequence[str], mode: str) -> Optional[Dict[str, Any]]:
    """Reuse last Cursor pack when requested paths are a subset. No file read."""
    from aegis.pack_cache import load_pack, normalize_mode

    meta = load_last_cursor_meta()
    pack_id = str(meta.get("pack_id") or "")
    if not pack_id:
        return None
    last_paths = {str(_resolve_path(p)) for p in (meta.get("paths") or []) if p}
    want = {str(_resolve_path(p)) for p in paths if p}
    if not want or not want.issubset(last_paths):
        return None
    last_mode = normalize_mode(str(meta.get("mode") or "explore"))
    want_mode = normalize_mode(mode)
    if want_mode == "implement" and last_mode != "implement":
        return None
    payload = load_pack(pack_id)
    if not payload:
        return None
    return {"pack_id": pack_id, "payload": payload, "meta": meta}


def cursor_gate(path: str, *, mode: str = "implement") -> Dict[str, Any]:
    """Tell Composer whether to reuse the last pack or Read/pack."""
    resolved = str(_resolve_path(path))
    covered = last_pack_covers([resolved], mode)
    if covered:
        return {
            "action": "reuse",
            "pack_id": covered["pack_id"],
            "packed_paths": list((covered["meta"] or {}).get("paths") or []),
            "path": resolved,
        }
    return {
        "action": "pack",
        "pack_id": None,
        "packed_paths": [],
        "path": resolved,
    }


def pack_id_from_ctx(ctx: Mapping[str, Any]) -> str:
    if not ctx:
        return ""
    direct = ctx.get("pack_id")
    if direct:
        return str(direct)
    meta = ctx.get("meta") or {}
    if meta.get("pack_id"):
        return str(meta["pack_id"])
    pre = ctx.get("preflight") or {}
    return str(pre.get("pack_id") or "")


def _bento_markdown(comps: Sequence[Mapping[str, Any]]) -> str:
    blocks = []
    for item in comps:
        blocks.append(
            f"### {item.get('path')} [{item.get('lang')}] "
            f"{item.get('raw_tokens')}→{item.get('compressed_tokens')} tok\n"
            f"```\n{item.get('payload_snippet') or ''}\n```"
        )
    return "\n".join(blocks) if blocks else "(no components)"


def _filter_components(
    comps: Sequence[Mapping[str, Any]], paths: Sequence[str]
) -> List[Mapping[str, Any]]:
    want = {str(_resolve_path(p)) for p in paths}
    kept = [
        item
        for item in comps
        if str(_resolve_path(str(item.get("path") or "."))) in want
    ]
    return list(kept or comps)


def cursor_context(
    *,
    task: str,
    paths: Sequence[str],
    mode: str = "implement",
    targets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Pack-first Cursor context. Reuse last pack when it covers the paths."""
    from aegis.ledger import record
    from aegis.receipt import write_last_receipt

    expanded = expand_pack_paths(paths)
    path_list = list(expanded["paths"])
    if not path_list:
        block = "\n".join(
            [
                "[AEGIS CURSOR CONTEXT]",
                f"task={task}",
                "reuse=miss pack_id=",
                "rule=empty pack; pass an existing file or a dir with neighbors",
            ]
        )
        meta = {
            "task": task,
            "mode": mode,
            "pack_id": None,
            "reuse": False,
            "ok": False,
            "reason": "EMPTY_PACK",
            "paths": [],
            "missing": expanded["missing"],
        }
        return {
            "ok": False,
            "pack_id": None,
            "reuse": False,
            "reason": "EMPTY_PACK",
            "composer_block": block,
            "meta": meta,
            "preflight": {},
            "expanded": expanded,
        }

    covered = last_pack_covers(path_list, mode)
    reuse = bool(covered)
    pack_id = None
    payload: Dict[str, Any] = {}
    pf_dict: Dict[str, Any] = {}
    mode_used = mode
    quality = "pass"
    reserve = "ok"
    output_profile = None

    if covered:
        pack_id = covered["pack_id"]
        payload = dict(covered["payload"] or {})
        payload["reuse"] = True
        payload["pack_id"] = pack_id
        payload["core_task"] = task
        comps = _filter_components(payload.get("bento_components") or [], path_list)
        raw = int(payload.get("total_raw_tokens", 0))
        entry = record(
            kind="reuse_hit",
            task=f"cursor:{mode}:{task[:40]}",
            mode=mode,
            raw_in=raw,
            processed_in=0,
            pack_id=pack_id,
            reuse=True,
            meta={"paths": path_list, "cursor_gate": "last_pack", "preflight": False},
        )
        payload["ledger_entry"] = entry
        write_last_receipt(entry, payload)
        quality = str((payload.get("quality") or {}).get("grade") or "pass")
        mode_used = str(payload.get("mode") or mode)
    else:
        pf = run_preflight(
            paths=path_list,
            task=task,
            mode=mode,
            targets=list(targets or []),
            strict=False,
            no_output=False,
            recover=True,
        )
        payload = (pf.summary or {}).get("payload") or {}
        comps = payload.get("bento_components") or []
        pack_id = pf.pack_id
        reuse = bool(payload.get("reuse"))
        mode_used = pf.mode_used
        quality = pf.quality_grade
        reserve = pf.reserve_signal
        output_profile = pf.output_profile
        pf_dict = pf.as_dict()

    reuse_token = "hit" if reuse and pack_id else "miss"
    stored_paths = path_list
    if covered:
        stored_paths = list((covered.get("meta") or {}).get("paths") or path_list)
    composer_block = "\n".join(
        [
            "[AEGIS CURSOR CONTEXT]",
            f"task={task}",
            f"mode={mode_used} quality={quality} reserve={reserve}",
            f"reuse={reuse_token} pack_id={pack_id or ''}",
            f"packed_paths={','.join(path_list)}",
            f"output_profile={output_profile}",
            "rule=if reuse=hit do not Read packed_paths; land final with `aegis land --body-file …`",
            "",
            "## Bento",
            _bento_markdown(comps),
        ]
    )
    ensure_home()
    last = aegis_home() / "cursor_last_context.md"
    last.write_text(composer_block, encoding="utf-8")
    meta = {
        "task": task,
        "mode": mode_used,
        "pack_id": pack_id,
        "quality": quality,
        "reserve": reserve,
        "reuse": reuse_token,
        "paths": stored_paths,
        "neighbors": expanded["neighbors"],
        "missing": expanded["missing"],
        "output_profile": output_profile,
        "context_path": str(last),
        "outputs_dir": str(outputs_dir()),
        "ok": bool(pack_id),
    }
    last_cursor_meta_path().write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {
        "ok": bool(pack_id),
        "pack_id": pack_id,
        "reuse": reuse_token,
        "composer_block": composer_block,
        "meta": meta,
        "preflight": pf_dict,
        "expanded": expanded,
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
    skills = installed_cursor_skills()
    return {
        "cursorrules_product": product_rules.is_file(),
        "cursorrules_cwd": cwd_rules.is_file(),
        "outputs_dir": str(outputs_dir()),
        "store": store_stats(),
        "last_context": str(aegis_home() / "cursor_last_context.md"),
        "last_meta": str(aegis_home() / "cursor_last.json"),
        "skills_src": str(cursor_skills_src()),
        "skills_dest": str(agents_skills_dir()),
        "skills": skills,
        "router_hint": "python3 -m aegis serve --port 8787",
        "cli": "python3 -m aegis cursor --task '…' --mode implement <files>",
    }
