"""Aegis CLI — piggy bank + 3R (reduce/reuse/recycle) + surplus → ideas."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _ensure_seeded() -> None:
    """Create home, config, optional one-time legacy import, starter ideas."""
    from aegis.compat.legacy import load_expense_report
    from aegis.config import load_config
    from aegis.ideas import list_ideas, rescore_all, seed_starter_ideas
    from aegis.ledger import import_legacy_expense_once
    from aegis.paths import ensure_home

    ensure_home()
    load_config()
    legacy = load_expense_report()
    if legacy:
        import_legacy_expense_once(legacy)
    raw = list_ideas(by_roi=False)
    if not raw:
        seed_starter_ideas()
    else:
        rescore_all()


def _prepare_read() -> None:
    """Read-only command boundary: no seeding, imports, or rescoring."""
    return None


def _cmd_doctor(args: argparse.Namespace) -> int:
    from aegis.doctor import doctor_report, format_doctor_text

    _prepare_read()
    report = doctor_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_doctor_text(report))
        if getattr(args, "product", False):
            print(f"  product_ready: {report.get('product_ready')}")
    if getattr(args, "product", False):
        return 0 if report.get("product_ready") else 1
    return 0 if report["ok"] else 1


def _cmd_scrub(args: argparse.Namespace) -> int:
    from aegis.ledger import record
    from aegis.scrub import scrub_path

    _ensure_seeded()

    path = args.path
    if path == "-":
        text = sys.stdin.read()
        label = "<stdin>"
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        label = path

    scrubbed, stats = scrub_path(label if path != "-" else "stdin.py", text)
    raw = int(stats.get("initial_chars", len(text)) / 4.0)
    saved = int(stats.get("tokens_saved", 0))
    processed = max(0, raw - saved)

    entry = None
    if not args.dry_run:
        entry = record(
            kind="scrub",
            task=f"scrub:{label}",
            mode="scrub",
            raw_in=raw,
            processed_in=processed,
            meta={"path": label, "chars": stats, "lang": stats.get("lang")},
        )

    out = {
        "path": label,
        "engine": "product_e3",
        "lang": stats.get("lang"),
        "stats": stats,
        "ledger": entry,
        "scrubbed": scrubbed if args.show else None,
    }
    if args.show:
        print(scrubbed)
        if not args.json:
            print(
                f"\n# stats lang={stats.get('lang')} "
                f"chars {stats['initial_chars']}→{stats['final_chars']} "
                f"tokens_saved≈{stats['tokens_saved']}",
                file=sys.stderr,
            )
    elif args.json:
        print(json.dumps({k: v for k, v in out.items() if v is not None}, indent=2))
    else:
        print(
            f"{label} [{stats.get('lang')}]: "
            f"{stats['initial_chars']}→{stats['final_chars']} chars "
            f"(≈{stats['tokens_saved']} tokens saved) [ledger={'yes' if entry else 'dry'}]"
        )
    return 0


def _read_snippets(paths: List[str]) -> List[Dict[str, str]]:
    snippets = []
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            snippets.append({"path": p, "content": f.read()})
    return snippets


def _print_pack(payload: Dict[str, Any], args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    reuse = payload.get("reuse", False)
    tag = "REUSE" if reuse else "pack"
    print(f"# aegis {tag} [{payload.get('mode')}] engine={payload.get('engine', 'legacy')}")
    print(f"# task: {payload.get('core_task')}")
    print(
        f"# tokens: {payload['total_raw_tokens']} → "
        f"{payload['total_compressed_tokens']} "
        f"({payload['overall_reduction_percent']}% reduction)"
        + (f" in {payload['assembly_time_ms']}ms" if "assembly_time_ms" in payload else "")
    )
    if payload.get("pack_id"):
        print(f"# pack_id: {payload['pack_id']}")
    if payload.get("ledger_entry"):
        print(f"# ledger: {payload['ledger_entry'].get('id')} saved={payload['ledger_entry'].get('tokens_saved')}")
    if payload.get("note"):
        print(f"# note: {payload['note']}")
    if payload.get("cache_policy"):
        print(f"# cache: {payload['cache_policy']}")
    if payload.get("token_accounting"):
        print(f"# tokens: accounting={payload['token_accounting']}")
    gates = payload.get("quality")
    if gates:
        from aegis.quality import GateResult, format_gates

        gr = GateResult(
            ok=gates.get("ok", True),
            strict_fail=gates.get("strict_fail", False),
            grade=gates.get("grade", "pass"),
            issues=gates.get("issues") or [],
        )
        print(format_gates(gr))
    print()
    print(f"## Task\n{payload.get('core_task')}\n")
    for comp in payload.get("bento_components", []):
        print(
            f"## {comp['path']} "
            f"({comp['raw_tokens']}→{comp['compressed_tokens']} tok, "
            f"{comp['reduction_percent']}% cut)\n"
        )
        print("```")
        print(comp["payload_snippet"])
        print("```\n")
    # Auto-receipt: always attach compact block unless silenced
    auto = not getattr(args, "no_receipt", False)
    if auto and not args.json:
        from aegis.receipt import format_receipt_block, load_last_receipt

        rec = load_last_receipt()
        if rec:
            print(format_receipt_block(rec))
            print()


def _cmd_pack(args: argparse.Namespace) -> int:
    from aegis.bento import assemble
    from aegis.compat.legacy import load_legacy_modules
    from aegis.ledger import record
    from aegis.pack_cache import attach_reuse_meta, get_or_none, pack_key, save_pack
    from aegis.quality import evaluate_pack
    from aegis.receipt import write_last_receipt

    _ensure_seeded()
    if not args.paths:
        print("aegis pack: need at least one file path", file=sys.stderr)
        return 2

    targets = list(args.target or [])
    snippets = _read_snippets(args.paths)
    sources = {s["path"]: s["content"] for s in snippets}
    # Reuse boost: mode + path hashes + targets; task excluded unless --task-in-cache
    include_task = bool(getattr(args, "task_in_cache", False))
    pack_id, cached = None, None
    cache_meta: Dict[str, Any] = {}
    if not args.no_cache and not args.refresh:
        pack_id, cached, cache_meta = get_or_none(
            args.mode,
            args.paths,
            args.task,
            targets=targets,
            include_task=include_task,
        )

    if cached and not args.refresh:
        payload = dict(cached)
        payload["reuse"] = True
        payload["pack_id"] = pack_id
        payload["core_task"] = args.task  # current intent; body still reused
        payload["cache_policy"] = "mode_map+path_set" + (
            "+task" if include_task else ""
        )
        if cache_meta.get("fallback_used"):
            payload["cache_fallback"] = cache_meta.get("fallback_mode")
        raw = int(payload.get("total_raw_tokens", 0))
        processed = 0
        entry = None
        if not args.dry_run:
            entry = record(
                kind="reuse_hit",
                task=f"pack:{args.mode}:{args.task[:48]}",
                mode=args.mode,
                raw_in=raw,
                processed_in=processed,
                pack_id=pack_id,
                reuse=True,
                meta={"paths": args.paths, "targets": targets},
            )
        payload["ledger_entry"] = entry
        payload["note"] = "REUSE hit — avoided re-pack (mode+paths+targets; task ignored)."
        gate = evaluate_pack(
            payload, mode=args.mode, targets=targets, sources=sources
        )
        payload["quality"] = gate.as_dict()
        if entry:
            write_last_receipt(entry, payload)
        _print_pack(payload, args)
        if args.strict and gate.strict_fail:
            return 3
        return 0

    from aegis.fund import pack_write_allowed

    allowed, refuse_reason = pack_write_allowed(reuse=False)
    if not allowed:
        print(f"aegis pack: {refuse_reason}", file=sys.stderr)
        return 4

    use_legacy = getattr(args, "legacy", False)
    if use_legacy:
        mods = load_legacy_modules()
        Assembler = mods["JITContextAssembler"]
        payload = Assembler(max_token_budget=args.budget).assemble_bento_payload(
            core_task=args.task,
            code_snippets=snippets,
        )
        payload["mode"] = args.mode
        payload["engine"] = "legacy"
        payload["note"] = "Legacy line-heuristic bento (--legacy)."
    else:
        payload = assemble(
            core_task=args.task,
            code_snippets=snippets,
            mode=args.mode,
            targets=targets,
            max_token_budget=args.budget,
        )
        payload["reuse"] = False
        langs = ",".join(payload.get("languages") or [])
        slicers = ",".join(payload.get("slicers") or [])
        if args.mode == "implement":
            payload["note"] = (
                f"E3 implement [{langs}] slicers=[{slicers}]: full target bodies "
                "+ neighbor sigs (full file if unresolved)."
            )
        elif args.mode == "review":
            payload["note"] = (
                f"E3 review [{langs}] slicers=[{slicers}]: diffs or structure previews."
            )
        else:
            payload["note"] = (
                f"E3 explore [{langs}] slicers=[{slicers}]: imports + signatures."
            )

    payload["reuse"] = False
    if pack_id is None:
        pack_id = pack_key(
            args.mode,
            args.paths,
            args.task,
            targets=targets,
            include_task=include_task,
        )
    payload["pack_id"] = pack_id
    payload["cache_policy"] = "mode_map+path_set" + (
        "+task" if include_task else ""
    )

    gate = evaluate_pack(
        payload, mode=args.mode, targets=targets, sources=sources
    )
    payload["quality"] = gate.as_dict()

    if not args.no_cache and not (args.strict and gate.strict_fail):
        attach_reuse_meta(payload, args.paths, args.mode, targets)
        save_pack(pack_id, payload)

    entry = None
    if not args.dry_run:
        entry = record(
            kind="pack",
            task=f"pack:{args.mode}:{args.task[:48]}",
            mode=args.mode,
            raw_in=int(payload["total_raw_tokens"]),
            processed_in=int(payload["total_compressed_tokens"]),
            pack_id=pack_id,
            reuse=False,
            meta={
                "paths": args.paths,
                "targets": targets,
                "engine": payload.get("engine"),
                "quality_grade": gate.grade,
            },
        )
    payload["ledger_entry"] = entry
    if entry:
        write_last_receipt(entry, payload)
    _print_pack(payload, args)
    emit = getattr(args, "emit_output_profile", None)
    if emit and not (args.strict and gate.strict_fail):
        from aegis.output_lane import activate_output, format_output_block

        out = activate_output(
            profile=emit,
            mode=args.mode,
            task=f"pack:{args.task[:40]}",
            dry_run=args.dry_run,
            pack_id=pack_id,
        )
        if not args.json:
            print(format_output_block(out))
    if args.strict and gate.strict_fail:
        print("aegis pack: strict quality gate failed", file=sys.stderr)
        return 3
    return 0


def _cmd_receipt(args: argparse.Namespace) -> int:
    from aegis.pack_cache import load_pack
    from aegis.receipt import format_receipt_block, load_last_receipt

    _ensure_seeded()
    receipt = load_last_receipt()
    if args.pack_id:
        cached = load_pack(args.pack_id)
        if not cached and (not receipt or receipt.get("pack_id") != args.pack_id):
            print(f"aegis receipt: unknown pack_id {args.pack_id}", file=sys.stderr)
            return 1
        if receipt and receipt.get("pack_id") == args.pack_id:
            pass
        elif cached:
            receipt = {
                "pack_id": args.pack_id,
                "mode": cached.get("mode"),
                "task": cached.get("core_task"),
                "raw_in": cached.get("total_raw_tokens"),
                "processed_in": cached.get("total_compressed_tokens"),
                "tokens_saved": int(cached.get("total_raw_tokens", 0))
                - int(cached.get("total_compressed_tokens", 0)),
                "reuse": cached.get("reuse"),
                "reduction_percent": cached.get("overall_reduction_percent"),
                "engine": cached.get("engine"),
                "paths": [
                    c.get("path") for c in cached.get("bento_components", [])
                ],
            }
    if not receipt:
        print("aegis receipt: no pack yet — run aegis pack first", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(format_receipt_block(receipt))
    return 0


def _cmd_budget(args: argparse.Namespace) -> int:
    from aegis.fund import surplus_snapshot
    from aegis.ledger import generate_report
    from aegis.output_lane import load_last_output

    _ensure_seeded()
    report = generate_report()
    surplus = surplus_snapshot()
    report["surplus_available_credits"] = surplus["available_credits"]
    report["can_invest"] = surplus["can_invest"]
    last_out = load_last_output()
    report["output_lane"] = {
        "active": last_out is not None,
        "last_profile": (last_out or {}).get("profile"),
        "week_raw_out": report.get("raw_out", 0),
        "week_processed_out": report.get("processed_out", 0),
        "week_out_saved": max(
            0, int(report.get("raw_out", 0)) - int(report.get("processed_out", 0))
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Aegis budget (piggy bank)")
        print(f"  week:       {report.get('week')}")
        print(f"  source:     {report.get('source')}")
        print(f"  accounting:  code_only (pack in) + out_lane")
        print(f"  consumed:   {report.get('total_tokens_consumed', 0):,} tok "
              f"(in={report.get('processed_in', 0):,} + out={report.get('processed_out', 0):,})")
        print(f"  saved:      {report.get('total_tokens_saved', 0):,} tok")
        print(f"  reduction:  {report.get('overall_token_reduction_percent', 0)}%")
        print(
            f"  reuse:      {report.get('reuse_hits', 0)} hits / "
            f"{report.get('pack_attempts', 0)} packs "
            f"({report.get('reuse_hit_rate_percent', 0)}% hit rate) · "
            f"{report.get('reuse_tokens_saved', 0):,} tok avoided"
        )
        print(
            f"  reuse life: {report.get('lifetime_reuse_hits', 0)} hits / "
            f"{report.get('lifetime_pack_attempts', 0)} packs "
            f"({report.get('lifetime_reuse_hit_rate_percent', 0)}%)"
        )
        ol = report["output_lane"]
        from aegis.output_lane import count_landed, load_last_output
        from aegis.output_store import store_stats

        last_o = load_last_output() or {}
        landed_n = count_landed()
        st = store_stats()
        print(
            f"  output:     lane={'on' if ol['active'] else 'off'} "
            f"profile={ol.get('last_profile') or '—'} · "
            f"week {ol['week_raw_out']}→{ol['week_processed_out']} "
            f"(saved {ol['week_out_saved']}) · landed={landed_n}"
        )
        print(
            f"  out store:  {st['entries']} entries · "
            f"tok {st['tokens_raw']}→{st['tokens_shrunk']} "
            f"(saved {st['tokens_saved']}) · "
            f"bytes {st['bytes_raw']}→{st['bytes_shrunk']}"
        )
        # reuse target signal (10x path → aim 50%+)
        rate = float(report.get("reuse_hit_rate_percent") or 0)
        print(
            f"  reuse aim:  target ≥50% · now {rate}% "
            f"{'OK' if rate >= 50 else 'BUILD'}"
        )
        if last_o.get("landed"):
            print(
                f"  last land:  actual={last_o.get('actual_out')} "
                f"saved={last_o.get('tokens_saved_actual')} "
                f"store={last_o.get('output_id') or '—'}"
            )
        if not ol["active"] or ol["week_raw_out"] == 0:
            print("  cue:        output lane cold — run: aegis preflight … or aegis output")
        elif landed_n == 0:
            print("  cue:        work not landed — run: aegis land --body-file out.txt")
        print(f"  weekly cap: {report.get('weekly_token_cap', 0):,}")
        print(
            f"  remaining:  {report.get('remaining_weekly_capacity_percent')}%  "
            f"[{report.get('reserve_signal')}]"
        )
        print(f"  wish jar:   {surplus['available_credits']:,} credits "
              f"(invest={'yes' if surplus['can_invest'] else 'no'})")
        rate = float(report.get("reuse_hit_rate_percent") or 0)
        attempts = int(report.get("pack_attempts") or 0)
        if attempts >= 3 and rate < 20:
            print("  cue:        low reuse — pack the same files until they change; covering hits only on unchanged hashes")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from aegis.ledger import generate_report

    _prepare_read()
    print(json.dumps(generate_report(accounting="provider_observed"), indent=2))
    return 0


def _cmd_context(args: argparse.Namespace) -> int:
    """Meter a candidate prompt or persist an explicit verified handoff capsule."""
    from aegis.config import load_config
    from aegis.context_governor import meter_context, persist_capsule, state_capsule

    cfg = load_config()
    if args.objective:
        capsule = state_capsule(
            objective=args.objective,
            constraints=args.constraint,
            decisions=args.decision,
            verified=args.verified,
            current_defect=args.defect,
            next_action=args.next_action,
        )
        path = persist_capsule(capsule)
        out = {"capsule": capsule, "path": str(path)}
    else:
        messages = [{"role": "user", "content": args.message or ""}]
        out = meter_context(
            messages,
            expected_output_tokens=args.expected_output,
            capacity=int(cfg.context_window_tokens),
        ).as_dict()
    print(json.dumps(out, indent=2) if args.json else out)
    return 0


def _load_source_manifest(path_text: str) -> Tuple[Dict[str, str], Set[str]]:
    """Load a small, auditable task-input manifest without copying its evidence."""
    path = Path(path_text).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source manifest must be a JSON object")

    required_text = ("task_id", "owner", "authority", "rollback")
    missing = [key for key in required_text if not isinstance(payload.get(key), str) or not payload[key].strip()]
    if missing:
        raise ValueError("source manifest needs non-empty " + ", ".join(missing))

    inputs = payload.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("source manifest needs a non-empty inputs list")
    for index, item in enumerate(inputs):
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in ("path", "kind", "status")
        ):
            raise ValueError(
                f"source manifest input {index} needs non-empty path, kind, and status"
            )

    excluded = payload.get("excluded", [])
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        raise ValueError("source manifest excluded must be a list of strings")

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    artifact = {
        "kind": "source_manifest",
        "path": str(path),
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "task_id": payload["task_id"],
    }
    normalized_paths = [str(Path(item["path"]).expanduser().resolve()) for item in inputs]
    approved_paths = set(normalized_paths)
    if len(approved_paths) != len(normalized_paths):
        raise ValueError("source manifest must not contain duplicate input paths")
    missing_paths = sorted(path for path in approved_paths if not Path(path).is_file())
    if missing_paths:
        raise ValueError("source manifest input paths must be existing files: " + ", ".join(missing_paths))
    return artifact, approved_paths


def _parse_evidence_refs(raw: list) -> list:
    refs = []
    for item in raw or []:
        text = str(item).strip()
        if not text:
            continue
        if "=" in text:
            kind, _, path = text.partition("=")
            refs.append({"kind": kind.strip(), "ref": path.strip()})
        else:
            refs.append({"kind": "path", "ref": text})
    return refs


def _cmd_continuity_bench(args: argparse.Namespace) -> int:
    from pathlib import Path

    from aegis.continuity_bench import run_bench

    path = Path(args.cases).expanduser()
    if not path.is_file():
        print(f"aegis continuity bench: cases file not found: {path}", file=sys.stderr)
        return 2
    report = run_bench(path)
    print(json.dumps(report, indent=2))
    return 0


def _cmd_continuity(args: argparse.Namespace) -> int:
    """Default continuity entry/exit for a long code task."""
    from aegis.context_governor import persist_capsule, state_capsule

    if args.continuity_action == "bench":
        return _cmd_continuity_bench(args)

    if args.continuity_action == "checkpoint":
        capsule = state_capsule(
            objective=args.objective,
            constraints=args.constraint,
            decisions=args.decision,
            verified=args.verified,
            current_defect=args.defect,
            next_action=args.next_action,
            mission=args.mission,
            owner=getattr(args, "owner", "operator"),
            privacy_class=getattr(args, "privacy_class", "internal"),
            open_risks=getattr(args, "open_risk", []),
            evidence_refs=_parse_evidence_refs(getattr(args, "evidence_ref", [])),
            deletion_path=getattr(args, "deletion_path", ""),
        )
        path = persist_capsule(capsule)
        out = {"capsule": capsule, "path": str(path)}
        if capsule.get("drift_status"):
            out["drift_status"] = capsule["drift_status"]
            out["drift_score"] = capsule["drift_score"]
        
        print(json.dumps(out, indent=2))
        if capsule.get("drift_status") == "quarantine":
            print(f"aegis continuity checkpoint: quarantine (drift score {capsule.get('drift_score')})", file=sys.stderr)
            return 3
        return 0

    if not args.paths:
        print("aegis continuity start: need code paths", file=sys.stderr)
        return 2
    source_manifest = None
    if args.source_manifest:
        try:
            source_manifest, approved_paths = _load_source_manifest(args.source_manifest)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"aegis continuity start: invalid source manifest: {exc}", file=sys.stderr)
            return 2
        unapproved = [path for path in args.paths if str(Path(path).expanduser().resolve()) not in approved_paths]
        if unapproved:
            print(
                "aegis continuity start: source manifest does not approve "
                + ", ".join(unapproved),
                file=sys.stderr,
            )
            return 2
    from aegis.cursor_bridge import cursor_context, pack_id_from_ctx

    ctx = cursor_context(
        task=args.task, paths=args.paths, mode=args.mode,
        targets=list(args.target or []),
    )
    pack_id = pack_id_from_ctx(ctx)
    if not pack_id or not ctx.get("ok"):
        print(
            "aegis continuity start: empty pack "
            "(no existing files or neighbors to pack)",
            file=sys.stderr,
        )
        return 2
    artifacts = [{"kind": "pack", "id": pack_id}]
    if source_manifest:
        artifacts.append(source_manifest)
    constraints = ["Use only the attached JIT pack; do not replay broad history."]
    if source_manifest:
        constraints.append("Use only sources approved by the attached source manifest.")
    capsule = state_capsule(
        objective=args.task,
        constraints=constraints,
        artifacts=artifacts,
        current_defect="Task in progress; claims remain provisional until checkpointed.",
        next_action="Implement from the pack, verify, then run aegis continuity checkpoint.",
        verification_status="provisional",
        mission=args.mission,
    )
    path = persist_capsule(capsule)
    out = {"continuity": "started", "context": ctx, "capsule": capsule,
           "capsule_path": str(path), "source_manifest": source_manifest}
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(ctx["composer_block"])
        print(f"\n# continuity capsule → {path}")
        print("# next: implement; verify; aegis continuity checkpoint --objective ... --next-action ...")
    return 0 if ctx.get("ok") else 1


def _cmd_outcome(args: argparse.Namespace) -> int:
    from aegis.outcomes import outcome_report, record_outcome

    if args.outcome_action == "report":
        print(json.dumps(outcome_report(workflow=args.workflow), indent=2))
        return 0
    if args.outcome_action == "verify-cost":
        from aegis.cost_provenance import classify_window
        window = classify_window(limit=args.limit)
        window["routing_authorized"] = False
        print(json.dumps(window, indent=2, default=str))
        return 0
    if args.outcome_action == "collect-receipts":
        from aegis.receipt_collect import collect_matched_pairs, collect_receipts
        pairs = int(getattr(args, "pairs", 0) or 0)
        execute = bool(getattr(args, "execute", False))
        model = str(getattr(args, "model", "") or "")
        if pairs > 0:
            payload = collect_matched_pairs(
                execute=execute,
                pairs=pairs,
                model=model,
                governed_model=str(getattr(args, "governed_model", "") or ""),
            )
        else:
            payload = collect_receipts(
                execute=execute,
                count=int(getattr(args, "count", 5)),
                model=model,
            )
        payload["routing_authorized"] = False
        print(json.dumps(payload, indent=2, default=str))
        return 0 if payload.get("ok") else 1
    row = record_outcome(
        task_id=args.task_id, variant=args.variant, accepted=args.accepted,
        elapsed_seconds=args.elapsed_seconds, retries=args.retries,
        correction_minutes=args.correction_minutes, cost_usd=args.cost_usd,
        cost_status=args.cost_status, cost_source=args.cost_source,
        workflow=args.workflow,
        notes=args.notes,
    )
    print(json.dumps(row, indent=2))
    return 0


def _cmd_guard(args: argparse.Namespace) -> int:
    from aegis.config import load_config
    cfg = load_config()
    
    if args.guard_action == "status":
        out = {
            "guard_active": True,
            "budget": {
                "max_tool_calls": cfg.guard_max_tool_calls,
                "max_velocity_per_min": cfg.guard_max_velocity_calls_per_min,
            },
            "signal_preservation": {
                "max_output_length": cfg.guard_max_output_length,
                "min_signal_score": cfg.guard_min_signal_score,
                "trim_strategy": cfg.guard_trim_strategy,
                "preserve_keywords": [k.strip() for k in cfg.guard_signal_preserve_keywords.split(",") if k.strip()],
            },
            "mission_lock": {
                "allowed_domains": [d.strip() for d in cfg.guard_allowed_domains.split(",") if d.strip()],
                "status": "locked" if [d.strip() for d in cfg.guard_allowed_domains.split(",") if d.strip()] else "unlocked",
                "require": bool(getattr(cfg, "guard_require_mission_lock", False)),
                "shadow_mode": bool(cfg.guard_shadow_mode),
                "mission": str(getattr(cfg, "guard_mission", "") or ""),
            },
            "agency": {
                "mode": str(getattr(cfg, "guard_agency_mode", "assistive")),
            },
            "memory_provenance": {
                "require": bool(getattr(cfg, "guard_require_memory_provenance", False)),
                "proposed_max": int(getattr(cfg, "memory_proposed_max", 200)),
            },
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print("AEGIS GUARD STATUS")
            print("==================")
            print("Budget & Velocity:")
            print(f"  Max tool calls: {out['budget']['max_tool_calls']}")
            print(f"  Max velocity: {out['budget']['max_velocity_per_min']}/min")
            print("Signal Preservation:")
            print(f"  Max output length: {out['signal_preservation']['max_output_length']}")
            print(f"  Min signal score: {out['signal_preservation']['min_signal_score']}")
            print(f"  Preserve keywords: {', '.join(out['signal_preservation']['preserve_keywords']) or 'unset'}")
            print("Mission Lock:")
            print(f"  Status: {out['mission_lock']['status'].upper()}")
            print(f"  Require: {out['mission_lock']['require']}")
            print(f"  Shadow: {out['mission_lock']['shadow_mode']}")
            print(f"  Allowed domains: {', '.join(out['mission_lock']['allowed_domains']) or 'unset'}")
            print(f"  Mission: {out['mission_lock']['mission'] or 'unset'}")
            print("Agency:")
            print(f"  Mode: {out['agency']['mode']}")
            print("Memory provenance:")
            print(f"  Require admitted id: {out['memory_provenance']['require']}")
            print(f"  Proposed max: {out['memory_provenance']['proposed_max']}")
        return 0

    if args.guard_action == "set-mode":
        from aegis.agency import AGENCY_MODES, normalize_mode
        from aegis.config import load_config, save_config

        mode = normalize_mode(args.mode)
        if mode not in AGENCY_MODES:
            print(f"aegis guard set-mode: invalid mode {args.mode!r}", file=sys.stderr)
            return 2
        cfg = load_config()
        cfg.guard_agency_mode = mode
        save_config(cfg)
        print(json.dumps({"guard_agency_mode": mode}) if args.json else f"guard_agency_mode={mode}")
        return 0

    if args.guard_action == "rotate":
        from aegis.guard import GUARD_LOG_PATH, rotate_guard_log
        res = rotate_guard_log(GUARD_LOG_PATH, if_larger_mb=args.if_larger_mb)
        if args.json:
            print(json.dumps(res, indent=2))
        elif res["rotated"]:
            print(f"Rotated {res['source_lines']} lines ({res['size_bytes']} B)")
            print(f"  Archive: {res['archive']}")
            print(f"  Manifest: {res['manifest']}")
        else:
            print(f"No rotation: {res['reason']} (log: {res['log_path']})")
        if res["rotated"] or res.get("reason") == "below_threshold":
            return 0
        return 2

    if args.guard_action == "log":
        # Try persistent log first
        from pathlib import Path
        import json as json_lib
        
        log_path = Path.home() / ".aegis" / "guard_log.jsonl"
        
        if log_path.exists():
            # Read last N entries from persistent log
            limit = getattr(args, 'limit', 50)
            entries = []
            
            with open(log_path, "r") as f:
                for line in f:
                    if line.strip():
                        entries.append(json_lib.loads(line))
            
            # Show most recent
            if args.json:
                print(json_lib.dumps(entries[-limit:], indent=2))
            else:
                print("AEGIS GUARD DECISIONS (Persistent Log)")
                print("=====================")
                for entry in reversed(entries[-limit:]):
                    ts = entry.get("timestamp_iso", "")[:19].replace("T", " ")
                    score_str = f" score={entry['score']:.2f} |" if entry.get('score') else ""
                    print(f"[{ts}] | {entry['rule']:8} | {entry['action']:7} |{score_str} {entry['reason']}")
            return 0
        
        # Fallback to in-memory (for daemon processes)
        from aegis.guard import _ACTIVE_GUARD
        if not _ACTIVE_GUARD:
            if args.json:
                print(json_lib.dumps({"error": "no live guard state available"}))
            else:
                print("No live guard state available. (AegisGuard runs in-memory and this CLI process is fresh.)")
            return 1
            
        decisions = _ACTIVE_GUARD.state.decisions
        if args.json:
            import dataclasses
            print(json_lib.dumps([dataclasses.asdict(d) for d in decisions], indent=2))
        else:
            print("AEGIS GUARD DECISIONS (In-Memory)")
            print("=====================")
            import datetime
            for d in decisions:
                dt = datetime.datetime.fromtimestamp(d.timestamp, tz=datetime.timezone.utc).isoformat()
                score_str = f" score={d.score:.2f} |" if d.score is not None else ""
                print(f"[{dt}] | {d.rule} | {d.action} |{score_str} {d.reason}")
        return 0
    return 1


def _cmd_memory(args: argparse.Namespace) -> int:
    import json as json_lib
    from pathlib import Path

    from aegis.memory_admit import (
        add_conflict,
        admit,
        delete_record,
        list_records,
        record_stats,
        validate_record,
    )

    action = args.memory_action
    if action == "stats":
        print(json_lib.dumps(record_stats(), indent=2) if args.json else json_lib.dumps(record_stats(), indent=2))
        return 0

    if action == "list":
        rows = list_records(
            memory_type=args.type or None,
            privacy_class=args.privacy or None,
            evidence_status=args.status or None,
            limit=args.limit,
        )
        print(json_lib.dumps(rows, indent=2) if args.json else json_lib.dumps(rows, indent=2))
        return 0

    if action == "admit":
        if args.file:
            payload = json_lib.loads(Path(args.file).read_text(encoding="utf-8"))
        elif args.stdin:
            payload = json_lib.loads(sys.stdin.read())
        else:
            print("aegis memory admit: need --file or --stdin", file=sys.stderr)
            return 2
        ok, errors = validate_record(payload)
        if not ok:
            print(json_lib.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
            return 2
        row = admit(payload, replace=bool(args.replace))
        print(json_lib.dumps({"ok": True, "record": row}, indent=2))
        return 0

    if action == "conflict":
        row = add_conflict(args.id, args.contradicts, reason=args.reason or "")
        print(json_lib.dumps(row, indent=2))
        return 0

    if action == "delete":
        out = delete_record(args.id, deletion_path=args.deletion_path or "cli")
        print(json_lib.dumps(out, indent=2))
        return 0

    return 1


def _cmd_relay(args: argparse.Namespace) -> int:
    import json as json_lib
    from pathlib import Path

    from aegis.relay import correlate, export_redacted, query, tail

    action = args.relay_action
    if action == "tail":
        rows = tail(args.source, limit=args.limit)
        print(json_lib.dumps(rows, indent=2) if args.json else json_lib.dumps(rows, indent=2))
        return 0
    if action == "query":
        rows = query(
            source=args.source,
            kind=args.kind or "",
            request_id=args.request_id or "",
            since=args.since or "",
            limit=args.limit,
        )
        print(json_lib.dumps(rows, indent=2))
        return 0
    if action == "correlate":
        out = correlate(args.request_id)
        print(json_lib.dumps(out, indent=2))
        return 0
    if action == "export":
        from aegis.paths import relay_export_dir

        dest = Path(args.output) if args.output else relay_export_dir() / "relay_export.json"
        count = export_redacted(dest, source=args.source, limit=args.limit)
        print(json_lib.dumps({"exported": count, "path": str(dest)}, indent=2))
        return 0
    return 1


def _cmd_pilot(args: argparse.Namespace) -> int:
    from aegis.outcomes import finish_pilot, init_pilot, pilot_status, start_pilot

    try:
        if args.pilot_action == "init":
            result = init_pilot(
                task_id=args.task_id, source_dir=args.source_dir,
                first_variant=args.first, workspace_root=args.workspace_root or None,
            )
        elif args.pilot_action == "start":
            result = start_pilot(args.task_id, args.variant)
        elif args.pilot_action == "finish":
            result = finish_pilot(
                args.task_id, accepted=args.accepted, retries=args.retries,
                correction_minutes=args.correction_minutes, notes=args.notes,
                cost_usd=args.cost_usd, cost_status=args.cost_status,
                cost_source=args.cost_source,
            )
        else:
            result = pilot_status(args.task_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"aegis pilot: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def _cmd_output(args: argparse.Namespace) -> int:
    from aegis.output_lane import activate_output, format_output_block

    _ensure_seeded()
    try:
        receipt = activate_output(
            profile=args.profile,
            mode=getattr(args, "mode", "explore") or "explore",
            max_tokens=args.max,
            task=f"output:{args.profile}",
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"aegis output: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(format_output_block(receipt))
        print(
            f"# lane on · est_save={receipt.get('tokens_saved_est')} "
            f"ledger={receipt.get('ledger_id')}",
            file=sys.stderr,
        )
    return 0


def _cmd_preflight(args: argparse.Namespace) -> int:
    from aegis.output_lane import format_output_block
    from aegis.preflight import format_preflight_banner, run_preflight
    from aegis.receipt import format_receipt_block

    _ensure_seeded()
    if not args.paths:
        print("aegis preflight: need at least one file path", file=sys.stderr)
        return 2

    result = run_preflight(
        paths=args.paths,
        task=args.task,
        mode=args.mode,
        targets=list(args.target or []),
        strict=args.strict,
        output_profile=args.output_profile,
        no_output=args.no_output,
        dry_run=args.dry_run,
        recover=not args.no_recover,
    )

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
        return result.exit_code

    print(format_preflight_banner(result))
    print()
    # pack body (compact)
    payload = (result.summary.get("payload") or {})
    if payload.get("bento_components") and not args.banner_only:
        print(f"## Task\n{args.task}\n")
        for comp in payload.get("bento_components", []):
            print(
                f"## {comp.get('path')} "
                f"({comp.get('raw_tokens')}→{comp.get('compressed_tokens')} tok, "
                f"{comp.get('reduction_percent')}% cut) [code_only]\n"
            )
            print("```")
            print(comp.get("payload_snippet") or "")
            print("```\n")
    rec = result.summary.get("receipt")
    if rec:
        print(format_receipt_block(rec))
        print()
    out = result.summary.get("output")
    if out and not args.no_output:
        print(format_output_block(out))
    return result.exit_code


def _cmd_record_out(args: argparse.Namespace) -> int:
    from aegis.output_lane import land_output

    _ensure_seeded()
    # land_output books actual; prefer as unified path
    landed = land_output(
        actual_tokens=args.actual,
        raw_tokens=args.raw,
        summary=args.task or "",
        task=args.task or "output:record",
    )
    if args.json:
        print(json.dumps(landed, indent=2))
    else:
        print(
            f"landed out {args.raw}→{args.actual} "
            f"(saved {landed['tokens_saved']}) id={landed.get('ledger_id')}"
        )
    return 0


def _cmd_land(args: argparse.Namespace) -> int:
    from aegis.output_lane import format_land_block, land_output

    _ensure_seeded()
    files = list(args.file or [])
    body = None
    if getattr(args, "body_file", None):
        with open(args.body_file, "r", encoding="utf-8", errors="replace") as f:
            body = f.read()
    elif getattr(args, "body", None) is not None:
        body = args.body
    elif getattr(args, "body_stdin", False):
        body = sys.stdin.read()

    try:
        landed = land_output(
            actual_tokens=args.actual,
            raw_tokens=args.raw,
            summary=args.summary or "",
            files=files,
            task=args.task or "land",
            body=body,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"aegis land: {exc}", file=sys.stderr)
        return 2
    if args.json:
        # omit huge body duplicate in json if present — keep shrunk
        print(json.dumps(landed, indent=2, ensure_ascii=False))
    else:
        print(format_land_block(landed))
    return 0


def _cmd_output_get(args: argparse.Namespace) -> int:
    from aegis.output_store import load_output

    _ensure_seeded()
    doc = load_output(args.output_id)
    if not doc:
        print(f"aegis output-get: unknown {args.output_id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print(doc.get("shrunk_text") or "")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from aegis import DEFAULT_BATCH_WORKERS, MAX_BATCH_WORKERS
    from aegis.router_pipeline import run_batch, run_pipeline

    _ensure_seeded()
    paths = list(args.paths or [])
    workers = args.workers if args.workers is not None else DEFAULT_BATCH_WORKERS
    workers = max(1, min(int(workers), MAX_BATCH_WORKERS))
    if getattr(args, "batch", None):
        # JSON list of jobs or newline models
        import pathlib

        raw = pathlib.Path(args.batch).read_text(encoding="utf-8")
        try:
            jobs_data = json.loads(raw)
            if not isinstance(jobs_data, list):
                raise ValueError("batch must be JSON list")
            jobs = []
            for j in jobs_data:
                jobs.append(
                    {
                        "task": j.get("task") or args.task,
                        "model": j.get("model") or args.model,
                        "provider": j.get("provider") or args.provider or "",
                        "paths": j.get("paths") or paths,
                        "mode": j.get("mode") or args.mode,
                        "prompt": j.get("prompt") or args.prompt or args.task,
                        "profile": j.get("profile") or args.profile,
                        "dry_run": args.dry_run,
                        "skip_preflight": args.skip_preflight or not (j.get("paths") or paths),
                        "max_tokens": args.max_tokens,
                    }
                )
        except json.JSONDecodeError:
            # one model per line
            jobs = [
                {
                    "task": args.task,
                    "model": line.strip(),
                    "provider": args.provider or "",
                    "paths": paths,
                    "mode": args.mode,
                    "prompt": args.prompt or args.task,
                    "profile": args.profile,
                    "dry_run": args.dry_run,
                    "skip_preflight": args.skip_preflight or not paths,
                    "max_tokens": args.max_tokens,
                }
                for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        results = run_batch(jobs, max_workers=workers)
        if args.json:
            print(json.dumps([r.as_dict() for r in results], indent=2))
        else:
            print(f"[AEGIS RUN BATCH] n={len(results)} workers={workers}")
            for r in results:
                print(
                    f"  {r.provider}/{r.model} ok={r.ok} reuse={r.output_reuse} "
                    f"out={r.output_id} err={r.error or '—'}"
                )
        return 0 if all(r.ok for r in results) else 1

    result = run_pipeline(
        task=args.task,
        model=args.model,
        provider=args.provider or "",
        paths=paths,
        mode=args.mode,
        targets=list(args.target or []),
        system=args.system or "",
        prompt=args.prompt or args.task,
        profile=args.profile,
        skip_preflight=args.skip_preflight or not paths,
        dry_run=args.dry_run,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(
            f"[AEGIS RUN] provider={result.provider} model={result.model} "
            f"ok={result.ok} mock={result.mock}"
        )
        print(
            f"pack_id={result.pack_id} output_id={result.output_id} "
            f"reuse={result.output_reuse}"
        )
        if result.error:
            print(f"error: {result.error}", file=sys.stderr)
        print("--- shrunk ---")
        print(result.shrunk or result.content)
    return 0 if result.ok else 1


def _cmd_serve(args: argparse.Namespace) -> int:
    from aegis.daemon_control import daemon_status, start_daemon, stop_daemon
    from aegis.router_daemon import serve_forever

    _ensure_seeded()
    # --stop / --status convenience on serve
    if getattr(args, "stop", False):
        res = stop_daemon()
        print(json.dumps(res, indent=2) if args.json else f"[AEGIS DAEMON] {res.get('message')}")
        return 0 if res.get("ok") else 1
    if getattr(args, "status", False):
        st = daemon_status()
        if args.json:
            print(json.dumps(st, indent=2))
        else:
            print(
                f"[AEGIS DAEMON] running={st['running']} pid={st.get('pid')} "
                f"url={st.get('url')} health={st.get('health', {}).get('reachable')}"
            )
            print(f"  log={st.get('log')}")
        return 0 if st.get("running") else 1

    background = getattr(args, "background", False) or getattr(args, "daemon", False)
    if background and not getattr(args, "foreground", False):
        res = start_daemon(args.host, args.port, force=bool(args.force))
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"[AEGIS DAEMON] {res.get('message')} "
                f"running={res.get('running')} pid={res.get('pid')} url={res.get('url')}"
            )
            print(f"  log={res.get('log')}")
            print("  stop:  aegis serve --stop   |  aegis daemon stop")
            print("  status: aegis serve --status |  aegis daemon status")
        return 0 if res.get("ok") else 1

    # foreground (default when not --background)
    serve_forever(host=args.host, port=args.port)
    return 0


def _cmd_daemon(args: argparse.Namespace) -> int:
    from aegis.daemon_control import (
        daemon_status,
        restart_daemon,
        start_daemon,
        stop_daemon,
    )
    from aegis.launchd import install_login, launchd_status, uninstall_login

    action = args.daemon_action
    if action == "status":
        _prepare_read()
    else:
        _ensure_seeded()
    host = args.host
    port = args.port

    if action == "start":
        res = start_daemon(host, port, force=bool(args.force))
    elif action == "stop":
        res = stop_daemon()
    elif action == "restart":
        res = restart_daemon(host, port)
    elif action == "status":
        res = daemon_status()
        res["launchd"] = launchd_status()
    elif action == "install-login":
        res = install_login(host, port)
    elif action == "uninstall-login":
        res = uninstall_login(stop=not bool(getattr(args, "keep_running", False)))
    else:
        print(f"aegis daemon: unknown action {action}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if action == "status":
            print(
                f"[AEGIS DAEMON] running={res.get('running')} pid={res.get('pid')} "
                f"url={res.get('url')}"
            )
            print(f"  health={res.get('health')}")
            print(f"  log={res.get('log')}")
            ld = res.get("launchd") or {}
            print(
                f"  launchd installed={ld.get('installed')} loaded={ld.get('loaded')} "
                f"label={ld.get('label')}"
            )
            if ld.get("plist"):
                print(f"  plist={ld.get('plist')}")
        elif action == "restart":
            print(f"[AEGIS DAEMON] restart ok={res.get('ok')}")
            print(f"  stop={res.get('stop', {}).get('message')}")
            print(f"  start={res.get('start', {}).get('message')} pid={res.get('start', {}).get('pid')}")
        elif action == "install-login":
            print(
                f"[AEGIS LAUNCHD] {res.get('message')} ok={res.get('ok')} "
                f"loaded={res.get('loaded')} running={res.get('running')}"
            )
            print(f"  plist={res.get('plist')}")
            print(f"  url={res.get('url')}")
            print(f"  logs: {res.get('log_out')} | {res.get('log_err')}")
            print("  next login: router starts automatically (KeepAlive)")
        elif action == "uninstall-login":
            print(f"[AEGIS LAUNCHD] {res.get('message')} ok={res.get('ok')}")
            print(f"  plist_removed={res.get('plist_removed')} bootout={res.get('bootout')}")
        else:
            print(
                f"[AEGIS DAEMON] {res.get('message')} "
                f"running={res.get('running', res.get('stopped'))} "
                f"pid={res.get('pid')}"
            )
            if res.get("url"):
                print(f"  url={res.get('url')}")
            if res.get("log"):
                print(f"  log={res.get('log')}")
    if action == "status":
        return 0 if res.get("running") else 1
    return 0 if res.get("ok", True) else 1


def _cmd_intel(args: argparse.Namespace) -> int:
    """Aegis Intelligence Layer — autonomous compound economy."""
    from aegis.forecast import predict_budget
    from aegis.intelligence import intel_status, tick
    from aegis.usage_intel import analyze_usage

    _prepare_read()
    action = args.intel_action or "status"

    if action == "tick":
        result = tick(force_report=bool(args.force_report))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"[AEGIS INTEL] ok={result.get('ok')} autonomous={result.get('autonomous')}")
            print(f"  {result.get('message')}")
            for a in result.get("actions") or []:
                print(f"  • {a}")
            fc = result.get("forecast") or {}
            print(
                f"  forecast: projected={fc.get('projected_signal')} "
                f"{fc.get('projected_remaining_pct')}% left · "
                f"safe_daily={fc.get('recommended_daily_budget')}"
            )
            if result.get("report_path"):
                print(f"  report: {result['report_path']}")
        return 0 if result.get("ok") else 1

    if action == "forecast":
        fc = predict_budget()
        if args.json:
            print(json.dumps(fc, indent=2))
        else:
            print("Aegis predictive budget")
            print(f"  week:              {fc.get('week')}")
            print(f"  consumed:          {fc.get('consumed'):,}")
            print(f"  avg daily burn:    {fc.get('avg_daily_burn')}")
            print(f"  projected week-end:{fc.get('projected_week_end_consumed'):,} "
                  f"→ {fc.get('projected_signal')} ({fc.get('projected_remaining_pct')}%)")
            print(f"  ETA to reserve:    {fc.get('eta_days_to_reserve')} days")
            print(f"  recommended/day:   {fc.get('recommended_daily_budget')}")
            bs = fc.get("burn_status") or {}
            if bs:
                print(f"  burn level:        {bs.get('level')} ({bs.get('ratio_pct')}% of safe)")
            for a in fc.get("advice") or []:
                print(f"  • {a}")
        return 0

    if action == "burn":
        from aegis.burn import burn_status, recent_burn_events

        st = burn_status(record_events=True)
        if args.json:
            st["recent_events"] = recent_burn_events(10)
            print(json.dumps(st, indent=2, default=str))
        else:
            print("Aegis burn status")
            print(f"  level:     {st.get('level')}  ({st.get('ratio_pct')}% of safe daily)")
            print(f"  burn/safe: {st.get('avg_daily_burn')} / {st.get('safe_daily')} tok/day")
            bands = st.get("bands") or {}
            print(
                f"  bands:     caution≥{bands.get('caution_at')} "
                f"warn≥{bands.get('warn_at')} critical≥{bands.get('critical_at')}"
            )
            print(f"  message:   {st.get('message')}")
            print(f"  action:    {st.get('fix_detail')}")
            ba = st.get("budget_aware") or {}
            print(f"  workers:   recommended={ba.get('recommended_workers')} "
                  f"(budget_aware={ba.get('enabled')})")
            if st.get("event"):
                print(f"  event:     {st['event'].get('from_level')}→{st['event'].get('to_level')}")
        return 0

    if action == "budget":
        from aegis.band_fanout import attach_fanout, fanout_log
        from aegis.budget_aware import evaluate, module_catalog, recent_budget_events, simulate

        attach_fanout(console=False)
        if getattr(args, "simulate", None):
            st = simulate(args.simulate)
        else:
            st = evaluate(dry_run=bool(getattr(args, "dry_run", False)))
        if args.json:
            st["recent_events"] = recent_budget_events(10)
            st["fanout_log"] = fanout_log(10)
            st["catalog"] = module_catalog()
            print(json.dumps(st, indent=2, default=str))
        else:
            print("Aegis Budget-Aware Mode")
            print(f"  enabled:   {st.get('enabled')}")
            print(f"  band:      {st.get('band')}  (level={st.get('level')}, "
                  f"instant={st.get('instant_level')})")
            print(f"  ratio:     {st.get('ratio_pct')}% of safe daily")
            if st.get("projected_ratio") is not None:
                print(f"  projected: {st.get('projected_ratio')} (rate horizon)")
            print(f"  summary:   {st.get('menu_summary')}")
            print(f"  shed:      {', '.join(st.get('modules_shed') or []) or 'none'}")
            print(f"  throttle:  {', '.join(st.get('modules_throttled') or []) or 'none'}")
            print(f"  sources:   {', '.join(st.get('source_preference') or [])}")
            print(f"  workers:   {st.get('recommended_workers')}")
            if st.get("dry_run"):
                print("  mode:      dry-run (not sticky)")
            if st.get("transition"):
                tr = st["transition"]
                print(f"  event:     {tr.get('from_band')}→{tr.get('to_band')}")
                if tr.get("reason"):
                    print(f"  reason:    {tr.get('reason')}")
        return 0

    if action == "continuity":
        from aegis.continuity import generate_bridge, latest_bridge_paths

        if getattr(args, "latest", False):
            paths = latest_bridge_paths()
            if args.json:
                print(json.dumps(paths, indent=2))
            else:
                print("Aegis Continuity Bridge (latest)")
                for k, v in paths.items():
                    print(f"  {k}: {v}")
            return 0
        bridge = generate_bridge(trigger="manual")
        if args.json:
            # omit full markdown body for size
            out = {k: v for k, v in bridge.items() if k not in ("markdown", "sections")}
            out["paths"] = bridge.get("paths")
            out["session_id"] = bridge.get("session_id")
            out["integrity_hash"] = (bridge.get("embedding_pack") or {}).get(
                "integrity_hash"
            )
            print(json.dumps(out, indent=2, default=str))
        else:
            print("Aegis Continuity Bridge")
            print(f"  ok={bridge.get('ok')} session={bridge.get('session_id')}")
            print(f"  trigger={bridge.get('trigger')}")
            paths = bridge.get("paths") or {}
            print(f"  markdown:   {paths.get('markdown')}")
            print(f"  json:       {paths.get('json')}")
            print(f"  embedding:  {paths.get('embedding')}")
            print(f"  latest:     {paths.get('latest_markdown')}")
            print("  Cross-AI next steps + embedding pack included.")
        return 0 if bridge.get("ok") else 1

    if action == "usage":
        u = analyze_usage()
        if args.json:
            print(json.dumps(u, indent=2))
        else:
            print("Aegis personal usage")
            print(f"  week: {u.get('week')}  txns={u.get('transactions')}")
            print(f"  cache hit: {u.get('cache_hit_rate_percent')}%  "
                  f"reduction: {u.get('reduction_percent')}%")
            print(f"  models: {u.get('model_distribution')}")
            print(f"  providers: {u.get('provider_distribution')}")
            print(f"  projects: {u.get('project_distribution')}")
            print(f"  types: {u.get('project_types')}  team≈{u.get('team_proxy', {}).get('estimate')}")
            print(f"  avg daily burn: {u.get('avg_daily_burn')}")
        return 0

    if action == "membership":
        from aegis.config import load_config, save_config
        from aegis.membership_guard import membership_status

        if args.membership_ceiling is not None or args.membership_reserve is not None:
            cfg = load_config()
            if args.membership_ceiling is not None:
                cfg.membership_shadow_weekly_tokens = max(0, args.membership_ceiling)
            if args.membership_reserve is not None:
                cfg.membership_reserve_percent = min(95.0, max(0.0, args.membership_reserve)) / 100.0
            save_config(cfg)
        status = membership_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("Aegis membership guard")
            print(f"  mode: {status['mode']} observed={status['observed_tokens']:,} tokens")
            print(f"  ceiling: {status['shadow_weekly_tokens'] or 'not calibrated'}")
            print(f"  reserve: {status['reserve_percent']}% source={status['source']}")
            print(f"  {status['detail']}")
        return 0

    if action == "report":
        result = tick(force_report=True)
        path = result.get("report_path")
        if args.json:
            print(json.dumps({"ok": True, "report_path": path, "actions": result.get("actions")}, indent=2))
        else:
            print(f"[AEGIS INTEL] weekly report → {path}")
        return 0

    # status
    st = intel_status()
    if args.json:
        print(json.dumps(st, indent=2, default=str))
    else:
        cfg = st.get("config") or {}
        state = st.get("state") or {}
        fc = st.get("forecast") or {}
        print("Aegis Intelligence Layer")
        print(f"  auto_tick={cfg.get('auto_tick')} auto_invest={cfg.get('auto_invest')} "
              f"auto_fixes={cfg.get('auto_apply_fixes')} auto_memory={cfg.get('auto_memory')}")
        print(f"  ticks={state.get('ticks')} invests={state.get('auto_invests')} "
              f"fixes={state.get('fixes_applied')} last={state.get('last_tick_ts')}")
        print(f"  bg_running={st.get('bg_tick_running')} cache_hit={st.get('cache_hit_rate_percent')}%")
        print(f"  reserve={ (st.get('usage') or {}).get('reserve_signal') } "
              f"remaining={ (st.get('usage') or {}).get('remaining_pct') }%")
        print(f"  forecast → {fc.get('projected_signal')} "
              f"({fc.get('projected_remaining_pct')}% @ week end)")
        for sig in (st.get("signals") or [])[:5]:
            print(f"  ! [{sig.get('severity')}] {sig.get('title')}")
        for idea in (st.get("top_ideas") or [])[:3]:
            print(f"  ★ [{idea.get('roi_grade')}] {idea.get('title')}")
    return 0


def _cmd_app(args: argparse.Namespace) -> int:
    """Build / open the native SwiftUI menu bar app."""
    import shutil
    import subprocess
    from pathlib import Path

    # src/aegis/cli.py → repo root
    repo = Path(__file__).resolve().parents[2]
    app_dir = repo / "apps" / "AegisMenu"
    script = app_dir / "scripts" / "build-app.sh"
    app_bundle = app_dir / "dist" / "AegisMenu.app"
    action = args.app_action or "open"

    if action == "path":
        print(str(app_bundle if app_bundle.is_dir() else app_dir))
        return 0

    if action == "status":
        st = {
            "app_dir": str(app_dir),
            "bundle": str(app_bundle),
            "built": app_bundle.is_dir(),
            "script": str(script),
            "swift": bool(shutil.which("swift")),
        }
        if args.json:
            print(json.dumps(st, indent=2))
        else:
            print(f"[AEGIS APP] built={st['built']} swift={st['swift']}")
            print(f"  bundle={st['bundle']}")
        return 0 if st["built"] else 1

    if action == "build":
        if not script.is_file():
            print(f"aegis app: missing {script}", file=sys.stderr)
            return 1
        if not shutil.which("swift"):
            print("aegis app: swift toolchain required (Xcode)", file=sys.stderr)
            return 1
        r = subprocess.run(["bash", str(script)], cwd=str(app_dir))
        return int(r.returncode)

    # open
    if not app_bundle.is_dir():
        print("[AEGIS APP] not built yet — running build…")
        if script.is_file() and shutil.which("swift"):
            r = subprocess.run(["bash", str(script)], cwd=str(app_dir))
            if r.returncode != 0:
                return int(r.returncode)
        else:
            print("aegis app: cannot build (need apps/AegisMenu + swift)", file=sys.stderr)
            return 1
    r = subprocess.run(["open", str(app_bundle)])
    if r.returncode == 0:
        print(f"[AEGIS APP] opened {app_bundle}")
    return int(r.returncode)


def _cmd_version(args: argparse.Namespace) -> int:
    from aegis import __version__
    from aegis.compound import compound_status

    _prepare_read()
    st = {
        "version": __version__,
        "epoch": "1.3",
        "compound": compound_status(),
    }
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        print(f"aegis {__version__} (epoch 1.3)")
        c = st["compound"]
        print(
            f"  compound engine: {c.get('structured_count')} structured · "
            f"treesitter={c.get('treesitter_active')} tsx={c.get('tsx_validated')}"
        )
        print(f"  pipeline: {' → '.join(c.get('pipeline') or [])}")
    return 0


def _cmd_langs(args: argparse.Namespace) -> int:
    from aegis.compound import compound_status

    _prepare_read()
    st = compound_status()
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        print("Aegis compound language matrix")
        for row in st["matrix"]:
            ts = "ts" if row.get("treesitter") else "  "
            print(
                f"  {row['lang']:<12} {row['tier']:<12} {ts}  {row['slicer']}"
            )
        print(
            f"  treesitter_active={st['treesitter_active']} "
            f"tsx_validated={st['tsx_validated']}"
        )
    return 0


def _cmd_wrap(args: argparse.Namespace) -> int:
    """CLI entry for OpenAI / Anti-Gravity / Hermes wrappers."""
    from aegis.wrappers.antigravity_wrapper import AntiGravityWrapper
    from aegis.wrappers.openai_wrapper import OpenAIWrapper

    _ensure_seeded()
    provider = (args.provider or "openai").lower()
    paths = list(args.paths or [])
    prompt = args.prompt or args.task
    if provider == "hermes":
        from aegis.wrappers.hermes_wrapper import HermesWrapper

        raw_text = prompt
        if args.body_file:
            raw_text = open(args.body_file, encoding="utf-8", errors="replace").read()
        try:
            req = json.loads(raw_text)
        except json.JSONDecodeError:
            print(
                "aegis wrap hermes: --prompt/--body-file must be a JSON request",
                file=sys.stderr,
            )
            return 2
        resp = HermesWrapper().handle(req)
        if args.json:
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            print(
                f"[AEGIS WRAP hermes] decision={resp.get('decision')} "
                f"ok={resp.get('ok')} executed={resp.get('executed')} "
                f"request_id={resp.get('request_id')}"
            )
            print(resp.get("reason") or "")
        return 0 if resp.get("decision") == "allow" else 1

    common = dict(
        task=args.task,
        paths=paths,
        mode=args.mode,
        targets=list(args.target or []),
        profile=args.profile,
        max_tokens=args.max_tokens,
        dry_run=args.dry_run,
        skip_preflight=args.skip_preflight or not paths,
    )
    if provider in ("openai", "gpt"):
        client = OpenAIWrapper(
            default_model=args.model or "gpt-4o-mini",
            dry_run=args.dry_run,
            profile=args.profile or "brief",
        )
        if args.body_file:
            body = open(args.body_file, encoding="utf-8", errors="replace").read()
            resp = OpenAIWrapper.intercept_output(
                body,
                model=args.model or "gpt-4o-mini",
                profile=args.profile or "brief",
                task=args.task,
                dry_run=args.dry_run,
            )
        else:
            resp = client.complete(prompt, model=args.model or "", **common)
    elif provider in ("antigravity", "gemini", "google"):
        client = AntiGravityWrapper(
            default_model=args.model or "",
            dry_run=args.dry_run,
            profile=args.profile or "brief",
        )
        if args.body_file:
            body = open(args.body_file, encoding="utf-8", errors="replace").read()
            resp = AntiGravityWrapper.intercept_output(
                body,
                model=args.model or client.default_model,
                profile=args.profile or "brief",
                task=args.task,
                dry_run=args.dry_run,
            )
        else:
            resp = client.chat(prompt, model=args.model or "", **common)
    else:
        print(
            f"aegis wrap: unknown provider {provider!r} "
            f"(openai|antigravity|hermes)",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        aeg = resp.get("aegis") or {}
        print(
            f"[AEGIS WRAP {provider}] ok={aeg.get('ok', True)} "
            f"output_id={aeg.get('output_id')} reuse={aeg.get('output_reuse')} "
            f"mock={aeg.get('mock')}"
        )
        if resp.get("error"):
            print(f"error: {resp['error']}", file=sys.stderr)
        content = ""
        try:
            content = resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = str(resp)[:500]
        print("--- shrunk ---")
        print(content)
    ok = (resp.get("aegis") or {}).get("ok", "error" not in resp)
    return 0 if ok else 1


def _cmd_providers(args: argparse.Namespace) -> int:
    from aegis.router_pipeline import router_status

    _prepare_read()
    st = router_status()
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        print("Aegis router providers")
        for p in st["providers"]:
            cred = "key" if p["credentials"] else "no-key"
            print(
                f"  {p['name']:<10} {p['default_model']:<24} {cred}  {p['base_url']}"
            )
        print(f"  outputs: {st['unified_output_dir']}")
        print(f"  reuse:   {st.get('reuse_hit_rate_percent')}%")
        print(f"  reserve: {st.get('remaining_pct')}% [{st.get('reserve_signal')}]")
        print(f"  concurrent default: {st.get('max_concurrent_default')}")
    return 0


def _cmd_cursor(args: argparse.Namespace) -> int:
    from aegis.cursor_bridge import (
        cursor_context,
        cursor_gate,
        cursor_run,
        cursor_status,
        install_cursor_rules,
        list_cursor_outputs,
    )
    from aegis.output_store import load_output

    _ensure_seeded()
    paths = list(getattr(args, "paths", None) or [])

    if getattr(args, "gate", None):
        gate = cursor_gate(args.gate, mode=getattr(args, "mode", "implement") or "implement")
        if getattr(args, "json", False):
            print(json.dumps(gate, indent=2))
        else:
            print(
                f"action={gate['action']} pack_id={gate.get('pack_id') or ''} "
                f"path={gate['path']}"
            )
        return 0 if gate.get("action") == "reuse" else 1

    if getattr(args, "install", False):
        res = install_cursor_rules(
            target_dir=getattr(args, "dir", None),
            also_home=bool(getattr(args, "home", False)),
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"[AEGIS CURSOR] installed {res['count']} files")
            for p in res["written"]:
                print(f"  {p}")
        return 0

    if getattr(args, "status", False):
        st = cursor_status()
        if getattr(args, "json", False):
            print(json.dumps(st, indent=2))
        else:
            print("Aegis ↔ Cursor")
            print(f"  .cursorrules product: {st['cursorrules_product']}")
            print(f"  .cursorrules cwd:     {st['cursorrules_cwd']}")
            print(f"  outputs: {st['outputs_dir']}")
            print(
                f"  store:   {st['store'].get('entries')} entries · "
                f"tok saved {st['store'].get('tokens_saved')}"
            )
            print(f"  last:    {st['last_context']}")
            print(f"  skills:  {', '.join(st.get('skills') or []) or '(none — aegis cursor --install)'}")
            print(f"  cli:     {st['cli']}")
        return 0

    if getattr(args, "outputs", False):
        rows = list_cursor_outputs(limit=getattr(args, "limit", 20))
        if getattr(args, "json", False):
            print(json.dumps(rows, indent=2))
        else:
            print(f"Unified output index ({len(rows)})")
            for r in rows:
                print(
                    f"  {r['id']}  {r.get('profile')}  "
                    f"{r.get('raw_tokens')}→{r.get('shrunk_tokens')}  "
                    f"{(r.get('summary') or '')[:40]}"
                )
        return 0

    if getattr(args, "output_id", None):
        doc = load_output(args.output_id)
        if not doc:
            print(f"aegis cursor --get: unknown {args.output_id}", file=sys.stderr)
            return 1
        if getattr(args, "json", False):
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            print(doc.get("shrunk_text") or "")
        return 0

    if not getattr(args, "task", None):
        print(
            'aegis cursor: need --task "..." and file paths '
            "(or --install | --status | --outputs | --get ID)",
            file=sys.stderr,
        )
        return 2
    if not paths:
        print("aegis cursor: need file paths for composer pack", file=sys.stderr)
        return 2

    model = getattr(args, "model", "none") or "none"
    if model and model != "none":
        result = cursor_run(
            task=args.task,
            paths=paths,
            mode=args.mode,
            model=model,
            provider=getattr(args, "provider", "") or "",
            targets=list(getattr(args, "target", None) or []),
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            ctx = result["context"]
            run = result["run"]
            print(ctx["composer_block"])
            print()
            print(
                f"[AEGIS CURSOR RUN] provider={run.get('provider')} "
                f"model={run.get('model')} ok={run.get('ok')} "
                f"output_id={run.get('output_id')} reuse={run.get('output_reuse')}"
            )
            print("--- shrunk ---")
            print(run.get("shrunk") or run.get("content") or "")
            print(f"\n# outputs_dir={result['outputs_dir']}")
        return 0 if result.get("run", {}).get("ok", True) else 1

    ctx = cursor_context(
        task=args.task,
        paths=paths,
        mode=args.mode,
        targets=list(getattr(args, "target", None) or []),
    )
    if getattr(args, "json", False):
        print(json.dumps(ctx, indent=2, ensure_ascii=False))
    else:
        print(ctx["composer_block"])
        print(f"\n# meta → {ctx['meta'].get('context_path')}")
        print(f"# outputs → {ctx['meta'].get('outputs_dir')}")
        print("# next: edit in Composer, then: aegis land --body-file <final.txt>")
    return 0 if ctx.get("ok") else 1


def _cmd_surplus(args: argparse.Namespace) -> int:
    from aegis.fund import surplus_snapshot

    _ensure_seeded()
    snap = surplus_snapshot()
    if args.json:
        print(json.dumps(snap, indent=2))
    else:
        print("Aegis surplus (wish jar)")
        print(f"  week:            {snap['week']}")
        print(f"  reserve:         [{snap['reserve_signal']}] "
              f"{snap['remaining_weekly_capacity_percent']}% remaining")
        print(f"  saved this week: {snap['gross_saved_week']:,} tok")
        print(f"  headroom:        {snap['headroom']:,} tok (above reserve floor)")
        print(f"  reinvest rate:   {snap['reinvest_rate']*100:.0f}% of new savings")
        print(f"  available:       {snap['available_credits']:,} credits")
        print(f"  reuse hit rate:  {snap.get('reuse_hit_rate_percent', 0)}% "
              f"({snap.get('pack_attempts', 0)} packs · "
              f"{snap.get('reuse_tokens_saved', 0):,} tok avoided)")
        print(f"  lifetime saved:  {snap['lifetime_saved']:,}")
        print(f"  lifetime credit: {snap['lifetime_credited']:,}")
        print(f"  lifetime invest: {snap['lifetime_invested']:,}")
        print(f"  can invest:      {snap['can_invest']}")
        if snap["reserve_signal"] != "ok":
            print("  note: invest frozen until reserve recovers (sustain first).")
    return 0


def _cmd_idea(args: argparse.Namespace) -> int:
    from aegis.ideas import (
        add_idea,
        complete_idea,
        list_ideas,
        rescore_all,
        seed_starter_ideas,
        suggest_ideas,
        update_idea_roi,
    )

    _ensure_seeded()
    action = args.idea_action
    if action == "add":
        idea = add_idea(
            args.title,
            body=args.body or "",
            tags=(args.tags.split(",") if args.tags else ["aegis"]),
            cost_estimate_tokens=args.cost,
            expected_savings_tokens=args.savings,
            confidence=args.confidence,
        )
        if args.json:
            print(json.dumps(idea, indent=2))
        else:
            print(
                f"added {idea['id']}: {idea['title']}  "
                f"ROI {idea.get('roi_grade')} score={idea.get('roi_score')} "
                f"ratio={idea.get('roi_ratio')}"
            )
        return 0
    if action == "list":
        rescore_all()
        ideas = list_ideas(status=args.status, by_roi=not args.no_rank)
        if args.json:
            print(json.dumps(ideas, indent=2))
        else:
            if not ideas:
                print("(no ideas — run: aegis idea suggest)")
            print(f"{'ID':<16} {'St':<8} {'G':<2} {'Score':>5} {'Ratio':>6} "
                  f"{'Effort':>7} {'Save/wk':>8} {'Funded':>7}  Title")
            for i in ideas:
                print(
                    f"{i['id']:<16} {i.get('status','?'):<8} "
                    f"{i.get('roi_grade','?'):<2} {i.get('roi_score',0):>5} "
                    f"{i.get('roi_ratio',0):>6} {i.get('effort_tokens',0):>7} "
                    f"{i.get('expected_savings_tokens',0):>8} "
                    f"{i.get('funded_credits',0):>7}  {i['title']}"
                )
        return 0
    if action == "suggest":
        suggestions = suggest_ideas()
        if args.json:
            print(json.dumps(suggestions, indent=2))
        else:
            for s in suggestions:
                extra = ""
                if s.get("roi_grade"):
                    extra = f" [ROI {s['roi_grade']} score={s.get('roi_score')}]"
                print(f"- {s['title']}{extra}: {s['body']}")
        return 0
    if action == "seed":
        created = seed_starter_ideas()
        n = rescore_all()
        print(f"seeded {len(created)} new; rescored {n} idea(s)")
        return 0
    if action == "complete":
        result = complete_idea(
            args.idea_id,
            actual_savings_tokens=args.actual_savings,
            note=args.note or "",
        )
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            idea = result["idea"]
            print(
                f"done {idea['id']}: actual={idea.get('actual_savings_tokens')} "
                f"actual_ROI={idea.get('actual_roi_ratio')}({idea.get('actual_roi_grade')}) "
                f"vs expected_ROI={idea.get('roi_ratio')}({idea.get('roi_grade')}) "
                f"delta={idea.get('roi_delta')}"
            )
        else:
            print(f"complete failed: {result.get('error')}", file=sys.stderr)
            return 1
        return 0 if result.get("ok") else 1
    if action == "score":
        result = update_idea_roi(
            args.idea_id,
            expected_savings_tokens=args.savings,
            cost_estimate_tokens=args.cost,
            confidence=args.confidence,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            idea = result["idea"]
            print(
                f"{idea['id']} ROI {idea.get('roi_grade')} score={idea.get('roi_score')} "
                f"ratio={idea.get('roi_ratio')} payback_weeks={idea.get('payback_weeks')}"
            )
        else:
            print(f"score failed: {result.get('error')}", file=sys.stderr)
            return 1
        return 0 if result.get("ok") else 1
    print("aegis idea: unknown action", file=sys.stderr)
    return 2


def _cmd_invest(args: argparse.Namespace) -> int:
    from aegis.kernel import syscall

    _ensure_seeded()
    result = syscall("invest", idea_id=args.idea_id, credits=args.credits)
    inner = result.get("result") if result.get("ok") else result
    payload = inner if isinstance(inner, dict) else result
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("ok") and payload.get("ok"):
            idea = payload["idea"]
            print(
                f"invested {payload['invested']} credits → {idea['id']} "
                f"[{idea['status']}] ROI {idea.get('roi_grade')} {idea['title']}"
            )
            print(f"remaining wish jar: {payload['available_credits']}")
        else:
            err = payload.get("error") or result.get("error") or "invest failed"
            print(f"invest failed: {err}", file=sys.stderr)
            return 1
    return 0 if result.get("ok") and payload.get("ok") else 1


def _cmd_sprint(args: argparse.Namespace) -> int:
    from aegis.sprints import (
        add_sprint,
        add_task,
        block_sprint,
        complete_sprint,
        complete_task,
        format_report_text,
        get_sprint,
        list_sprints,
        park_sprint,
        reconcile_known_history,
        report,
        unpark_sprint,
        seed_board,
        start_sprint,
        write_board,
    )

    _prepare_read()
    action = args.sprint_action
    if action == "seed":
        result = seed_board(force=bool(getattr(args, "force", False)))
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(
                f"seeded created={len(result['created'])} "
                f"refreshed={len(result['refreshed'])} total={result['total']}"
            )
        return 0
    if action == "add":
        row = add_sprint(args.title, goal=args.goal or "", status=args.status)
        if args.json:
            print(json.dumps(row, indent=2))
        else:
            print(f"added {row['id']}: {row['title']} [{row['status']}]")
        return 0
    if action == "list":
        rows = list_sprints(status=args.status or "")
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            if not rows:
                print("(no sprints — run: aegis sprint seed)")
            for row in rows:
                print(f"{row['id']:<8} {row['status']:<8} {row['title']}")
        return 0
    if action == "show":
        row = get_sprint(args.sprint_id)
        if row is None:
            print(f"unknown sprint {args.sprint_id}", file=sys.stderr)
            return 2
        print(json.dumps(row, indent=2))
        return 0
    if action == "start":
        result = start_sprint(args.sprint_id)
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            sprint = result["sprint"]
            print(f"active {sprint['id']}: {sprint['title']}")
        else:
            print(f"start failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    if action == "complete":
        result = complete_sprint(
            args.sprint_id, verified=args.verified, evidence=args.evidence or ""
        )
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            sprint = result["sprint"]
            print(f"done {sprint['id']}: {sprint['verified']}")
        else:
            print(f"complete failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    if action == "block":
        blocked = [item.strip() for item in (args.blocked_by or "").split(",") if item.strip()]
        result = block_sprint(args.sprint_id, reason=args.reason or "", blocked_by=blocked)
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            print(f"blocked {result['sprint']['id']}")
        else:
            print(f"block failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    if action == "unpark":
        result = unpark_sprint(args.sprint_id, reason=args.reason or "")
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            print(f"unparked {result['sprint']['id']} → {result['sprint']['status']}")
        else:
            print(f"unpark failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    if action == "park":
        result = park_sprint(args.sprint_id, reason=args.reason or "")
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            print(f"parked {result['sprint']['id']}")
        else:
            print(f"park failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    if action == "task":
        if args.task_action == "add":
            result = add_task(args.sprint_id, args.title)
        else:
            result = complete_task(args.sprint_id, args.task_id, evidence=args.evidence or "")
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            task = result["task"]
            print(f"{task['id']} [{task['status']}] {task['title']}")
        else:
            print(f"task failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    if action == "report":
        payload = report(repo=Path(args.repo) if args.repo else Path.cwd())
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(format_report_text(payload), end="")
        return 0
    if action == "board":
        dest = write_board(Path(args.write) if args.write else None)
        if args.json:
            print(json.dumps({"ok": True, "path": str(dest)}, indent=2))
        else:
            print(f"wrote {dest}")
        return 0
    if action == "reconcile":
        result = reconcile_known_history()
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            print(
                f"reconciled ids={','.join(result['ids'])} "
                f"audit={result['audit_path']}"
            )
        else:
            print(f"reconcile failed: {result.get('error')}", file=sys.stderr)
        return 0 if result.get("ok") else 2
    print(f"unknown sprint action {action}", file=sys.stderr)
    return 2


def _cmd_hermes(args: argparse.Namespace) -> int:
    _prepare_read()
    action = args.hermes_action
    if action == "search":
        from aegis.hermes_search import unified_search

        payload = unified_search(
            args.query,
            kind=args.kind or "",
            tag=args.tag or "",
            project=args.project or "",
            limit=int(args.limit),
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if action == "resolve":
        from aegis.hermes_notes import (
            load_verified_disk_graph,
            resolve_context,
            set_active_graph,
        )

        graph, err = load_verified_disk_graph()
        if graph is not None:
            set_active_graph(graph)
        result = resolve_context(
            args.query,
            project=args.project or "",
            max_notes=int(args.max_notes),
        )
        payload = result.as_dict()
        if err:
            payload["index_error"] = err
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"unknown hermes action {action}", file=sys.stderr)
    return 2


def _cmd_audit(args: argparse.Namespace) -> int:
    from aegis.audit import audit_portfolio, format_audit_text
    from aegis.ideas import rescore_all

    _prepare_read()
    report = audit_portfolio()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_audit_text(report))
    return 0


def _print_kernel(payload: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload.get("ok", True) else 1
    result = payload.get("result", payload)
    if payload.get("kid"):
        print(f"kid={payload.get('kid')} syscall={payload.get('syscall')} elapsed_ms={payload.get('elapsed_ms')}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _cmd_kernel(args: argparse.Namespace) -> int:
    from aegis.kernel import syscall

    _prepare_read()
    action = getattr(args, "kernel_action", "status") or "status"
    extra: Dict[str, Any] = {}
    if getattr(args, "path", None):
        extra["paths"] = list(args.path)
    if getattr(args, "task", None):
        extra["task"] = args.task
    if getattr(args, "limit", None):
        extra["limit"] = args.limit
    if getattr(args, "dest", None):
        extra["dest"] = args.dest
    if getattr(args, "archive", None):
        extra["archive"] = args.archive
    if getattr(args, "home", None):
        extra["home"] = args.home
    if getattr(args, "rounds", None):
        extra["rounds"] = args.rounds
    if getattr(args, "idea_id", None):
        extra["idea_id"] = args.idea_id
    name = action if action != "syscall" else (args.name or "status")
    payload = syscall(name, **extra)
    return _print_kernel(payload, bool(args.json))


def _cmd_os(args: argparse.Namespace) -> int:
    from aegis.kernel import syscall

    _prepare_read()
    action = getattr(args, "os_action", "score") or "score"
    extra: Dict[str, Any] = {}
    if action == "init":
        extra["home"] = getattr(args, "home", None)
        payload = syscall("init", **extra)
    elif action == "backup":
        payload = syscall("backup", dest=getattr(args, "out", None) or getattr(args, "dest", None))
    elif action == "restore":
        payload = syscall("restore", archive=args.archive, home=getattr(args, "home", None))
    elif action == "uninstall":
        from aegis.portable import uninstall_home

        payload = uninstall_home(yes=bool(getattr(args, "yes", False)), home=getattr(args, "home", None))
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    elif action == "bench":
        payload = syscall("bench", paths=list(getattr(args, "path", None) or []), rounds=getattr(args, "rounds", 12))
    elif action == "ready":
        from aegis.doctor import release_report

        payload = release_report()
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        else:
            print(
                f"Aegis release  v{payload.get('version')}  ok={payload.get('ok')}  "
                f"product_ready={payload.get('product_ready')}"
            )
            print(f"  decisions={payload.get('decisions_ok')}  modules={payload.get('modules_ok')}")
            print(f"  reuse: {payload.get('reuse')}")
            print("  savings_percent=null")
            repair = payload.get("repair") or {}
            for k, ids in repair.items():
                if ids:
                    print(f"  repair.{k}: {', '.join(ids)}")
        return 0 if payload.get("ok") else 1
    else:
        payload = syscall("score")
    return _print_kernel(payload, bool(args.json))


def _cmd_api(args: argparse.Namespace) -> int:
    from aegis.api_contract import check_payload, spec
    from aegis.kernel import syscall

    _prepare_read()
    action = getattr(args, "api_action", "spec") or "spec"
    if action == "check":
        payload = syscall("status")
        result = check_payload("GET /v1/aegis/kernel", {"ok": True, "kernel": payload.get("result"), "version": payload.get("version")})
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    body = spec()
    print(json.dumps(body, indent=2))
    return 0 if body.get("ok") else 1


def _cmd_yield(args: argparse.Namespace) -> int:
    from aegis.kernel import syscall

    _prepare_read()
    action = getattr(args, "yield_action", "report") or "report"
    if action == "prove":
        payload = syscall("yield_prove", paths=list(getattr(args, "path", None) or []), task=getattr(args, "task", None) or "yield-prove")
    else:
        payload = syscall("yield_prove")
    return _print_kernel(payload, True)


def _cmd_decisions(args: argparse.Namespace) -> int:
    from aegis.decisions import health, measure_naive_vs_pack

    _prepare_read()
    action = getattr(args, "decisions_action", "health") or "health"
    if action == "measure":
        payload = measure_naive_vs_pack(
            args.path,
            model=args.model,
            provider=args.provider,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload.get("ok") else 1
    report = health()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Aegis decisions  v{report.get('version')}  ok={report.get('ok')}")
        if report.get("repair"):
            print(f"  repair: {', '.join(report['repair'])}")
        for row in report.get("decisions") or []:
            mark = "OK" if row.get("aligned") else "FIX"
            print(
                f"  [{mark:3}] {row['id']:6} {row['verdict']:11} {row['evidence']}"
            )
            print(f"         → {row['action']}")
    return 0 if report.get("ok") else 1


def _cmd_modules(args: argparse.Namespace) -> int:
    from aegis.modules import health, measure_naive_vs_pack

    _prepare_read()
    action = getattr(args, "modules_action", "health") or "health"
    if action == "measure":
        payload = measure_naive_vs_pack(
            args.path,
            model=args.model,
            provider=args.provider,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload.get("ok") else 1
    report = health()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Aegis modules  v{report.get('version')}  ok={report.get('ok')}")
        if report.get("repair"):
            print(f"  repair: {', '.join(report['repair'])}")
        for row in report.get("modules") or []:
            mark = "OK" if row.get("aligned") else "FIX"
            print(
                f"  [{mark:3}] {row['id']:6} {row.get('name', ''):28} "
                f"{row['verdict']:11} {row['evidence']}"
            )
            print(f"         → {row['action']}")
    return 0 if report.get("ok") else 1


def _cmd_price(args: argparse.Namespace) -> int:
    from aegis.pricing import format_quote, quote

    _prepare_read()
    payload = quote()
    action = getattr(args, "price_action", "quote") or "quote"
    if getattr(args, "json", False):
        if action == "skus":
            payload = {
                "ok": True,
                "savings_percent": None,
                "skus": payload.get("skus"),
                "value_delta": payload.get("value_delta"),
            }
        elif action == "pitch":
            payload = {
                "ok": True,
                "savings_percent": None,
                "buyer": payload.get("buyer"),
                "sell": payload.get("sell"),
                "market": payload.get("market"),
            }
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if action == "skus":
        sk = payload["skus"]
        src = sk["source_nonexclusive"]["usd"]
        ex = sk["exclusive_lab_12mo"]["usd"]
        print("Aegis SKUs  (hosted=not offered)  savings_percent=null")
        print(f"  source      ${src['low']:,}–${src['high']:,}  mid ${src['mid']:,}  {sk['source_nonexclusive']['includes']}")
        print(f"  exclusive   ${ex['low']:,}–${ex['high']:,}  mid ${ex['mid']:,}  {sk['exclusive_lab_12mo']['includes']}")
        return 0
    if action == "pitch":
        print(f"buyer: {payload['buyer']['yes']}")
        print(f"not:   {payload['buyer']['no']}")
        print("sell:")
        for step in payload["sell"]:
            print(f"  - {step}")
        print("market:")
        for step in payload["market"]:
            print(f"  - {step}")
        return 0
    print(format_quote(payload))
    return 0



def _cmd_intake(args: argparse.Namespace) -> int:
    from aegis.intake import ingest_text, list_reports
    _prepare_read()
    action = getattr(args, 'intake_action', 'list') or 'list'
    if action == 'add':
        rec = ingest_text(args.text, sender=getattr(args, 'sender', 'local'), channel=getattr(args, 'channel', 'cli'))
        if getattr(args, 'json', False):
            print(json.dumps(rec, indent=2))
        else:
            print(f"[AEGIS:ACK] ID:{rec['id']} | Mod:{rec['module']} | Priority:{rec['priority']} | Queued")
        return 0
    elif action == 'list':
        reports = list_reports(limit=getattr(args, 'limit', 10))
        if getattr(args, 'json', False):
            print(json.dumps(reports, indent=2))
        else:
            if not reports:
                print('No ingested reports found.')
            for r in reports:
                print(f"{r.get('id')}  [{r.get('priority')}]  {r.get('module')}  -  {r.get('summary')}")
        return 0
    return 1

def _cmd_demo(args: argparse.Namespace) -> int:
    from aegis.demo import (
        format_run,
        format_status,
        name_buyer,
        run,
        spoken_script,
        start_clock,
        status,
    )

    _prepare_read()
    action = getattr(args, "demo_action", "status") or "status"
    as_json = bool(getattr(args, "json", False))
    if action == "start":
        payload = start_clock(reset=bool(getattr(args, "reset", False)))
        print(json.dumps(payload, indent=2, ensure_ascii=False) if as_json else format_status(payload))
        return 0 if payload.get("ok") else 1
    if action == "buyer":
        payload = name_buyer(getattr(args, "name", "") or "")
        print(json.dumps(payload, indent=2, ensure_ascii=False) if as_json else format_status(payload))
        return 0 if payload.get("ok") else 2
    if action == "script":
        payload = spoken_script()
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for beat in payload.get("beats") or []:
                print(beat)
        return 0
    if action == "run":
        paths = list(getattr(args, "path", None) or [])
        skip = bool(getattr(args, "skip_pack", False))
        if not skip and not paths:
            print("aegis demo run: need a file path (or --skip-pack)", file=sys.stderr)
            return 2
        payload = run(paths, skip_pack=skip)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str) if as_json else format_run(payload))
        return 0 if payload.get("ok") else 1
    payload = status()
    print(json.dumps(payload, indent=2, ensure_ascii=False) if as_json else format_status(payload))
    return 0 if payload.get("ok") else 1


def _parse_mode(value: str) -> str:
    from aegis.pack_cache import MODE_ALIASES, normalize_mode

    v = (value or "explore").strip().lower()
    if v in MODE_ALIASES or v in ("explore", "implement", "review"):
        return normalize_mode(v)
    raise argparse.ArgumentTypeError(
        f"invalid mode {value!r}; use explore|implement|review "
        f"or aliases read/search|edit/fix|pr/diff"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aegis",
        description="Aegis JIT token supply chain — piggy bank + reduce/reuse/recycle",
    )
    from aegis import __version__ as _aegis_version

    p.add_argument("--version", action="version", version=f"%(prog)s {_aegis_version}")
    sub = p.add_subparsers(dest="command", required=True)

    ver = sub.add_parser("version", help="Show Aegis version + compound engine")
    ver.add_argument("--json", action="store_true")
    ver.set_defaults(func=_cmd_version)

    lg = sub.add_parser("langs", help="Compound language matrix")
    lg.add_argument("--json", action="store_true")
    lg.set_defaults(func=_cmd_langs)

    wrap = sub.add_parser(
        "wrap",
        help="OpenAI / Anti-Gravity / Hermes wrappers through Aegis",
    )
    wrap.add_argument(
        "--provider",
        default="openai",
        help="openai|antigravity|hermes",
    )
    wrap.add_argument("--task", default="wrap")
    wrap.add_argument("--prompt", default="", help="user prompt (default: task)")
    wrap.add_argument("--model", default="")
    wrap.add_argument("--mode", type=_parse_mode, default="explore")
    wrap.add_argument("--target", action="append", default=[])
    wrap.add_argument(
        "--profile",
        choices=("brief", "diff", "json"),
        default="brief",
    )
    wrap.add_argument("--max-tokens", type=int, default=1024)
    wrap.add_argument(
        "--body-file",
        default=None,
        help="Post-hoc: shrink/store existing model output file",
    )
    wrap.add_argument("--skip-preflight", action="store_true")
    wrap.add_argument("--dry-run", action="store_true")
    wrap.add_argument("--json", action="store_true")
    wrap.add_argument("paths", nargs="*", help="optional pack paths")
    wrap.set_defaults(func=_cmd_wrap)

    d = sub.add_parser("doctor", help="Health and migration checks")
    d.add_argument("--json", action="store_true")
    d.add_argument("--product", action="store_true", help="Exit on product_ready (second-machine floor)")
    d.set_defaults(func=_cmd_doctor)

    s = sub.add_parser("scrub", help="QC scrub a file or stdin (-) — reduce + ledger")
    s.add_argument("path", help="File path or - for stdin")
    s.add_argument("--show", action="store_true", help="Print scrubbed text")
    s.add_argument("--json", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=_cmd_scrub)

    pk = sub.add_parser("pack", help="Assemble bento payload (E2 modes + reuse cache)")
    pk.add_argument("--task", required=True, help="Core task string")
    pk.add_argument(
        "--mode",
        type=_parse_mode,
        default="explore",
        help="explore|implement|review (aliases: read, edit/fix, pr/diff)",
    )
    pk.add_argument(
        "--target",
        action="append",
        default=[],
        help="Implement-mode symbol (repeatable): Foo, Foo.bar",
    )
    pk.add_argument("--budget", type=int, default=8192)
    pk.add_argument("--json", action="store_true")
    pk.add_argument("--no-cache", action="store_true", help="Skip pack cache")
    pk.add_argument("--refresh", action="store_true", help="Rebuild cache entry")
    pk.add_argument("--legacy", action="store_true", help="Force gen-1 line bento")
    pk.add_argument(
        "--strict",
        action="store_true",
        help="Exit 3 on quality gate fail (fidelity/empty)",
    )
    pk.add_argument(
        "--no-receipt",
        action="store_true",
        help="Do not auto-print pack receipt block",
    )
    pk.add_argument(
        "--task-in-cache",
        action="store_true",
        help="Include task string in cache key (legacy; lowers reuse)",
    )
    pk.add_argument(
        "--emit-output-profile",
        choices=("brief", "diff", "json"),
        default=None,
        help="Also activate output lane with this profile after pack",
    )
    pk.add_argument("--dry-run", action="store_true")
    pk.add_argument("paths", nargs="+", help="Source files")
    pk.set_defaults(func=_cmd_pack)

    pf = sub.add_parser(
        "preflight",
        help="Agent one-shot: pack + quality + receipt + budget + output lane",
    )
    pf.add_argument("--task", required=True)
    pf.add_argument(
        "--mode",
        type=_parse_mode,
        default="explore",
        help="explore|implement|review (+ aliases read/edit/pr)",
    )
    pf.add_argument("--target", action="append", default=[])
    pf.add_argument("--strict", action="store_true")
    pf.add_argument(
        "--output-profile",
        choices=("brief", "diff", "json"),
        default=None,
        help="Force output profile (default: mode-mapped)",
    )
    pf.add_argument("--no-output", action="store_true", help="Skip output lane")
    pf.add_argument("--no-recover", action="store_true", help="Disable explore recovery")
    pf.add_argument("--banner-only", action="store_true", help="Skip pack body dump")
    pf.add_argument("--json", action="store_true")
    pf.add_argument("--dry-run", action="store_true")
    pf.add_argument("paths", nargs="+")
    pf.set_defaults(func=_cmd_preflight)

    rc = sub.add_parser(
        "receipt",
        help="Last pack receipt block for agent turns (avoid re-reading paths)",
    )
    rc.add_argument("pack_id", nargs="?", default=None, help="Optional pack id")
    rc.add_argument("--json", action="store_true")
    rc.set_defaults(func=_cmd_receipt)

    b = sub.add_parser("budget", help="Weekly piggy bank snapshot")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=_cmd_budget)

    r = sub.add_parser("report", help="Full expense-style report (JSON)")
    r.set_defaults(func=_cmd_report)

    cx = sub.add_parser("context", help="Meter context or create a verified transfer capsule")
    cx.add_argument("--message", default="")
    cx.add_argument("--expected-output", type=int, default=800)
    cx.add_argument("--objective", default="")
    cx.add_argument("--constraint", action="append", default=[])
    cx.add_argument("--decision", action="append", default=[])
    cx.add_argument("--verified", action="append", default=[])
    cx.add_argument("--defect", default="")
    cx.add_argument("--next-action", default="")
    cx.add_argument("--json", action="store_true")
    cx.set_defaults(func=_cmd_context)

    ct = sub.add_parser("continuity", help="Default start/checkpoint path for long coding tasks")
    ct_sub = ct.add_subparsers(dest="continuity_action", required=True)
    ct_start = ct_sub.add_parser("start", help="Pack code and write a provisional continuity receipt")
    ct_start.add_argument("--task", required=True)
    ct_start.add_argument("--mode", type=_parse_mode, default="implement")
    ct_start.add_argument("--target", action="append", default=[])
    ct_start.add_argument("--source-manifest", default="", help="Validated JSON record of approved task inputs")
    ct_start.add_argument("--mission", default="", help="Original mission objective for drift calculation")
    ct_start.add_argument("--json", action="store_true")
    ct_start.add_argument("paths", nargs="+")
    ct_start.set_defaults(func=_cmd_continuity)
    ct_checkpoint = ct_sub.add_parser("checkpoint", help="Write verified state for a clean next task")
    ct_checkpoint.add_argument("--objective", required=True)
    ct_checkpoint.add_argument("--constraint", action="append", default=[])
    ct_checkpoint.add_argument("--decision", action="append", default=[])
    ct_checkpoint.add_argument("--verified", action="append", default=[])
    ct_checkpoint.add_argument("--defect", default="")
    ct_checkpoint.add_argument("--next-action", required=True)
    ct_checkpoint.add_argument("--mission", default="", help="Original mission objective (or carried over if omitted)")
    ct_checkpoint.add_argument("--owner", default="operator")
    ct_checkpoint.add_argument("--privacy-class", default="internal", dest="privacy_class",
                               choices=["public", "internal", "private", "sensitive", "restricted"])
    ct_checkpoint.add_argument("--open-risk", action="append", default=[], dest="open_risk")
    ct_checkpoint.add_argument("--evidence-ref", action="append", default=[], dest="evidence_ref")
    ct_checkpoint.add_argument("--deletion-path", default="", dest="deletion_path")
    ct_checkpoint.set_defaults(func=_cmd_continuity)
    ct_bench = ct_sub.add_parser("bench", help="A/B baseline vs governed handoff on continuity fixture")
    ct_bench.add_argument(
        "--cases",
        default=str(
            Path.home()
            / "Documents/ChatGPT/Memory utility Labs/experiments/continuity-assurance/cases.json"
        ),
    )
    ct_bench.add_argument("--json", action="store_true")
    ct_bench.set_defaults(func=_cmd_continuity)

    oc = sub.add_parser("outcome", help="Record or inspect matched workflow outcomes")
    oc_sub = oc.add_subparsers(dest="outcome_action", required=True)
    oc_add = oc_sub.add_parser("record", help="Append an observed baseline or governed task result")
    oc_add.add_argument("--task-id", required=True)
    oc_add.add_argument("--variant", required=True, choices=("baseline", "governed"))
    oc_add.add_argument("--workflow", default="production_code_change")
    oc_add.add_argument("--accepted", action=argparse.BooleanOptionalAction, default=True)
    oc_add.add_argument("--elapsed-seconds", type=float, required=True)
    oc_add.add_argument("--retries", type=int, default=0)
    oc_add.add_argument("--correction-minutes", type=float, default=0.0)
    oc_add.add_argument("--cost-usd", type=float, default=None)
    oc_add.add_argument(
        "--cost-status",
        choices=("unknown", "observed", "verified_zero", "legacy_unknown"),
        default=None,
    )
    oc_add.add_argument("--cost-source", default="")
    oc_add.add_argument("--notes", default="")
    oc_add.set_defaults(func=_cmd_outcome)
    oc_report = oc_sub.add_parser("report", help="Read-only matched baseline/governed report")
    oc_report.add_argument("--workflow", default="production_code_change")
    oc_report.set_defaults(func=_cmd_outcome)
    oc_verify = oc_sub.add_parser(
        "verify-cost",
        help="Audit recent cost provenance and classify gaps (never authorizes routing)",
    )
    oc_verify.add_argument("--limit", type=int, default=5)
    oc_verify.set_defaults(func=_cmd_outcome)
    oc_collect = oc_sub.add_parser(
        "collect-receipts",
        help="Probe or collect consecutive Nous/AGIS billed receipts (never authorizes routing)",
    )
    oc_collect.add_argument(
        "--execute",
        action="store_true",
        help="Bill the named model and append observed rows. Default is probe-only.",
    )
    oc_collect.add_argument("--count", type=int, default=5)
    oc_collect.add_argument(
        "--pairs",
        type=int,
        default=0,
        help="If >0 with --execute, bill this many baseline/governed pairs (not a routing trial)",
    )
    oc_collect.add_argument("--model", default="", help="Override AEGIS_RECEIPT_MODEL / deepseek-v4-pro")
    oc_collect.add_argument(
        "--governed-model",
        default="",
        help="Optional cheaper governed model id (same Nous/AGIS provider)",
    )
    oc_collect.set_defaults(func=_cmd_outcome)

    pilot = sub.add_parser("pilot", help="Create and time reproducible matched workflow pairs")
    pilot_sub = pilot.add_subparsers(dest="pilot_action", required=True)
    pilot_init = pilot_sub.add_parser("init", help="Create identical baseline and governed copies")
    pilot_init.add_argument("--task-id", required=True)
    pilot_init.add_argument("--source-dir", required=True)
    pilot_init.add_argument("--first", required=True, choices=("baseline", "governed"))
    pilot_init.add_argument("--workspace-root", default="")
    pilot_init.set_defaults(func=_cmd_pilot)
    pilot_start = pilot_sub.add_parser("start", help="Start the next frozen variant timer")
    pilot_start.add_argument("--task-id", required=True)
    pilot_start.add_argument("--variant", required=True, choices=("baseline", "governed"))
    pilot_start.set_defaults(func=_cmd_pilot)
    pilot_finish = pilot_sub.add_parser("finish", help="Stop the timer and record its outcome")
    pilot_finish.add_argument("--task-id", required=True)
    pilot_finish.add_argument("--accepted", action=argparse.BooleanOptionalAction, default=True)
    pilot_finish.add_argument("--retries", type=int, default=0)
    pilot_finish.add_argument("--correction-minutes", type=float, default=0.0)
    pilot_finish.add_argument("--notes", default="")
    pilot_finish.add_argument("--cost-usd", type=float)
    pilot_finish.add_argument("--cost-status")
    pilot_finish.add_argument("--cost-source", default="")
    pilot_finish.set_defaults(func=_cmd_pilot)
    pilot_status_parser = pilot_sub.add_parser("status", help="Read durable pilot-pair state")
    pilot_status_parser.add_argument("--task-id", required=True)
    pilot_status_parser.set_defaults(func=_cmd_pilot)

    o = sub.add_parser("output", help="Activate output lane (profile + ledger out meters)")
    o.add_argument(
        "--profile",
        choices=("diff", "json", "brief"),
        default="brief",
    )
    o.add_argument(
        "--mode",
        choices=("explore", "implement", "review"),
        default="explore",
        help="Hint for default profile when used with preflight mapping",
    )
    o.add_argument("--max", type=int, default=None, help="Max output tokens")
    o.add_argument("--json", action="store_true")
    o.add_argument("--dry-run", action="store_true")
    o.set_defaults(func=_cmd_output)

    ro = sub.add_parser("record-out", help="Book real output token savings (alias of land)")
    ro.add_argument("--raw", type=int, required=True, help="Tokens without quantization")
    ro.add_argument("--actual", type=int, required=True, help="Tokens actually used")
    ro.add_argument("--task", default="")
    ro.add_argument("--json", action="store_true")
    ro.set_defaults(func=_cmd_record_out)

    land = sub.add_parser(
        "land",
        help="Land completed work — shrink+store body, book ledger, close thought→ship",
    )
    land.add_argument(
        "--actual",
        type=int,
        default=None,
        help="Actual output tokens (default: shrunk size when --body given)",
    )
    land.add_argument(
        "--raw",
        type=int,
        default=None,
        help="Unconstrained estimate (default: body raw or last lane estimate)",
    )
    land.add_argument("--body", default=None, help="Final output text to shrink+store")
    land.add_argument(
        "--body-file",
        default=None,
        help="Read final output from file (shrink+store)",
    )
    land.add_argument(
        "--body-stdin",
        action="store_true",
        help="Read final output from stdin",
    )
    land.add_argument("--summary", default="", help="What landed")
    land.add_argument("--task", default="")
    land.add_argument("--file", action="append", default=[], help="Files touched")
    land.add_argument("--json", action="store_true")
    land.add_argument("--dry-run", action="store_true")
    land.set_defaults(func=_cmd_land)

    og = sub.add_parser("output-get", help="Print stored shrunk output by id")
    og.add_argument("output_id")
    og.add_argument("--json", action="store_true")
    og.set_defaults(func=_cmd_output_get)

    run = sub.add_parser(
        "run",
        help="Universal pipeline: preflight → model → shrink/store/reuse → ledger",
    )
    run.add_argument("--task", required=True)
    run.add_argument(
        "--model",
        default="mock",
        help="model id or provider/model (mock|ollama|grok|claude|openai)",
    )
    run.add_argument(
        "--provider",
        default="",
        help="force provider: ollama|grok|claude|openai|mock",
    )
    run.add_argument("--mode", type=_parse_mode, default="explore")
    run.add_argument("--target", action="append", default=[])
    run.add_argument("--prompt", default="", help="user prompt (default: task)")
    run.add_argument("--system", default="")
    run.add_argument(
        "--profile",
        choices=("brief", "diff", "json"),
        default=None,
    )
    run.add_argument("--max-tokens", type=int, default=1024)
    run.add_argument("--temperature", type=float, default=0.2)
    run.add_argument("--skip-preflight", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="Force mock model")
    run.add_argument(
        "--batch",
        default=None,
        help="JSON list of jobs or file with one model per line",
    )
    run.add_argument(
        "--workers",
        type=int,
        default=None,  # filled from DEFAULT_BATCH_WORKERS in _cmd_run
        help="Concurrent workers for --batch (default shared with router)",
    )
    run.add_argument("--json", action="store_true")
    run.add_argument("paths", nargs="*", help="optional files for preflight pack")
    run.set_defaults(func=_cmd_run)

    serve_p = sub.add_parser(
        "serve",
        help="Start universal router (foreground or --background)",
    )
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8787)
    serve_p.add_argument(
        "-d",
        "--background",
        "--daemon",
        action="store_true",
        dest="background",
        help="Run router in the background (PID under ~/.aegis/)",
    )
    serve_p.add_argument(
        "--foreground",
        action="store_true",
        help="Force foreground (used by background launcher)",
    )
    serve_p.add_argument("--stop", action="store_true", help="Stop background router")
    serve_p.add_argument("--status", action="store_true", help="Background router status")
    serve_p.add_argument("--force", action="store_true", help="Restart if already running")
    serve_p.add_argument("--json", action="store_true")
    serve_p.set_defaults(func=_cmd_serve)

    dmn = sub.add_parser(
        "daemon",
        help="Background router: start|stop|status|restart|install-login|uninstall-login",
    )
    dmn.add_argument(
        "daemon_action",
        choices=(
            "start",
            "stop",
            "status",
            "restart",
            "install-login",
            "uninstall-login",
        ),
    )
    dmn.add_argument("--host", default="127.0.0.1")
    dmn.add_argument("--port", type=int, default=8787)
    dmn.add_argument("--force", action="store_true")
    dmn.add_argument(
        "--keep-running",
        action="store_true",
        help="With uninstall-login: remove agent but leave router process up",
    )
    dmn.add_argument("--json", action="store_true")
    dmn.set_defaults(func=_cmd_daemon)

    intel_p = sub.add_parser(
        "intel",
        help="Intelligence Layer: status|tick|forecast|usage|report (autonomous compound)",
    )
    intel_p.add_argument(
        "intel_action",
        nargs="?",
        default="status",
        choices=(
            "status",
            "tick",
            "forecast",
            "usage",
            "membership",
            "report",
            "burn",
            "budget",
            "continuity",
        ),
    )
    intel_p.add_argument(
        "--force-report",
        action="store_true",
        help="With tick/report: always write weekly ROI report",
    )
    intel_p.add_argument(
        "--dry-run",
        action="store_true",
        help="With budget: plan without sticky state",
    )
    intel_p.add_argument(
        "--simulate",
        choices=("ok", "caution", "adaptive", "emergency"),
        default=None,
        help="With budget: simulate a band",
    )
    intel_p.add_argument(
        "--latest",
        action="store_true",
        help="With continuity: print latest bridge paths only",
    )
    intel_p.add_argument(
        "--membership-ceiling",
        type=int,
        default=None,
        help="With membership: local weekly token estimate; 0 returns to observation mode",
    )
    intel_p.add_argument(
        "--membership-reserve",
        type=float,
        default=None,
        help="With membership: reserve percentage before conservation mode (0-95)",
    )
    intel_p.add_argument("--json", action="store_true")
    intel_p.set_defaults(func=_cmd_intel)

    app_p = sub.add_parser(
        "app",
        help="macOS SwiftUI menu bar: build|open|path",
    )
    app_p.add_argument(
        "app_action",
        nargs="?",
        default="open",
        choices=("build", "open", "path", "status"),
    )
    app_p.add_argument("--json", action="store_true")
    app_p.set_defaults(func=_cmd_app)

    prov = sub.add_parser("providers", help="List router providers + status")
    prov.add_argument("--json", action="store_true")
    prov.set_defaults(func=_cmd_providers)

    cur = sub.add_parser(
        "cursor",
        help="Cursor composer bridge: pack context / run router / outputs / install rules",
    )
    cur.add_argument(
        "--install",
        action="store_true",
        help="Write .cursorrules + .cursorignore",
    )
    cur.add_argument(
        "--gate",
        default=None,
        help="Reuse-or-pack verdict for one path (exit 0=reuse, 1=pack)",
    )
    cur.add_argument("--status", action="store_true", help="Cursor integration status")
    cur.add_argument(
        "--outputs",
        action="store_true",
        help="List unified output index",
    )
    cur.add_argument(
        "--get",
        dest="output_id",
        default=None,
        help="Get shrunk output by id (out_…)",
    )
    cur.add_argument("--task", default="")
    cur.add_argument("--mode", type=_parse_mode, default="implement")
    cur.add_argument("--target", action="append", default=[])
    cur.add_argument(
        "--model",
        default="none",
        help="none=context only; mock|ollama|grok|claude|openai runs full router",
    )
    cur.add_argument("--provider", default="")
    cur.add_argument("--dir", default=None, help="install target dir")
    cur.add_argument("--home", action="store_true", help="install ~/.cursor/aegis.cursorrules")
    cur.add_argument("--limit", type=int, default=20)
    cur.add_argument("--dry-run", action="store_true")
    cur.add_argument("--json", action="store_true")
    cur.add_argument("paths", nargs="*", help="files for composer pack")
    cur.set_defaults(func=_cmd_cursor)

    su = sub.add_parser("surplus", help="Wish jar — investable surplus credits")
    su.add_argument("--json", action="store_true")
    su.set_defaults(func=_cmd_surplus)

    idea = sub.add_parser("idea", help="Improvement idea backlog (ROI-ranked)")
    idea_sub = idea.add_subparsers(dest="idea_action", required=True)
    ia = idea_sub.add_parser("add", help="Add an idea")
    ia.add_argument("title")
    ia.add_argument("--body", default="")
    ia.add_argument("--tags", default="aegis")
    ia.add_argument("--cost", type=int, default=5000, help="Effort (tokens/credits)")
    ia.add_argument(
        "--savings",
        type=int,
        default=None,
        help="Expected weekly token savings if shipped",
    )
    ia.add_argument(
        "--confidence",
        choices=("low", "medium", "high"),
        default="medium",
    )
    ia.add_argument("--json", action="store_true")
    ia.set_defaults(func=_cmd_idea)
    il = idea_sub.add_parser("list", help="List ideas ranked by ROI score")
    il.add_argument("--status", default=None)
    il.add_argument("--no-rank", action="store_true", help="Do not sort by ROI")
    il.add_argument("--json", action="store_true")
    il.set_defaults(func=_cmd_idea)
    ig = idea_sub.add_parser("suggest", help="Suggest ideas from ledger patterns")
    ig.add_argument("--json", action="store_true")
    ig.set_defaults(func=_cmd_idea)
    ise = idea_sub.add_parser("seed", help="Seed starter Aegis improvement ideas")
    ise.set_defaults(func=_cmd_idea)
    ic = idea_sub.add_parser("complete", help="Mark done + record actual savings")
    ic.add_argument("idea_id")
    ic.add_argument(
        "--actual-savings",
        type=int,
        required=True,
        help="Measured token savings after shipping",
    )
    ic.add_argument("--note", default="")
    ic.add_argument("--json", action="store_true")
    ic.set_defaults(func=_cmd_idea)
    isc = idea_sub.add_parser("score", help="Update ROI inputs and rescore")
    isc.add_argument("idea_id")
    isc.add_argument("--savings", type=int, default=None)
    isc.add_argument("--cost", type=int, default=None)
    isc.add_argument(
        "--confidence",
        choices=("low", "medium", "high"),
        default=None,
    )
    isc.add_argument("--json", action="store_true")
    isc.set_defaults(func=_cmd_idea)

    inv = sub.add_parser("invest", help="Spend surplus credits on an idea")
    inv.add_argument("idea_id")
    inv.add_argument("--credits", type=int, default=None)
    inv.add_argument("--json", action="store_true")
    inv.set_defaults(func=_cmd_invest)

    au = sub.add_parser(
        "audit",
        help="Review investments, actual vs expected ROI, lessons learned",
    )
    au.add_argument("--json", action="store_true")
    au.set_defaults(func=_cmd_audit)

    gd = sub.add_parser("guard", help="Inspect active AEGIS guard policy")
    gd_sub = gd.add_subparsers(dest="guard_action", required=True)
    gds = gd_sub.add_parser("status", help="Print static guard thresholds and rules")
    gds.add_argument("--json", action="store_true")
    gds.set_defaults(func=_cmd_guard)
    
    gdl = gd_sub.add_parser("log", help="Print recent guard decisions from live memory")
    gdl.add_argument("--json", action="store_true")
    gdl.set_defaults(func=_cmd_guard)

    gdr = gd_sub.add_parser("rotate", help="Rotate guard_log.jsonl to a timestamped archive with manifest")
    gdr.add_argument("--if-larger-mb", type=float, default=None,
                     help="Rotate only when the log is at least this many MB")
    gdr.add_argument("--json", action="store_true")
    gdr.set_defaults(func=_cmd_guard)

    gdsm = gd_sub.add_parser("set-mode", help="Set bounded agency mode (reflective|assistive|autonomous)")
    gdsm.add_argument("mode", choices=["reflective", "assistive", "autonomous"])
    gdsm.add_argument("--json", action="store_true")
    gdsm.set_defaults(func=_cmd_guard)

    mem = sub.add_parser("memory", help="Durable provenance memory (memory_records.jsonl)")
    mem_sub = mem.add_subparsers(dest="memory_action", required=True)
    mem_admit = mem_sub.add_parser("admit", help="Validate and admit a memory record")
    mem_admit.add_argument("--file", default="")
    mem_admit.add_argument("--stdin", action="store_true")
    mem_admit.add_argument("--replace", action="store_true")
    mem_admit.add_argument("--json", action="store_true")
    mem_admit.set_defaults(func=_cmd_memory)
    mem_list = mem_sub.add_parser("list", help="List admitted memory records")
    mem_list.add_argument("--type", default="")
    mem_list.add_argument("--privacy", default="")
    mem_list.add_argument("--status", default="")
    mem_list.add_argument("--limit", type=int, default=50)
    mem_list.add_argument("--json", action="store_true")
    mem_list.set_defaults(func=_cmd_memory)
    mem_conflict = mem_sub.add_parser("conflict", help="Link conflicting records")
    mem_conflict.add_argument("--id", required=True)
    mem_conflict.add_argument("--contradicts", required=True)
    mem_conflict.add_argument("--reason", default="")
    mem_conflict.add_argument("--json", action="store_true")
    mem_conflict.set_defaults(func=_cmd_memory)
    mem_delete = mem_sub.add_parser("delete", help="Delete a durable memory record")
    mem_delete.add_argument("--id", required=True)
    mem_delete.add_argument("--deletion-path", default="")
    mem_delete.add_argument("--json", action="store_true")
    mem_delete.set_defaults(func=_cmd_memory)
    mem_stats = mem_sub.add_parser("stats", help="Memory tier statistics")
    mem_stats.add_argument("--json", action="store_true")
    mem_stats.set_defaults(func=_cmd_memory)

    rl = sub.add_parser("relay", help="Observability relay over guard/continuity/ledger/outcomes")
    rl_sub = rl.add_subparsers(dest="relay_action", required=True)
    rl_tail = rl_sub.add_parser("tail", help="Tail recent relay events")
    rl_tail.add_argument("--source", default="all", choices=["all", "guard", "continuity", "ledger", "outcomes"])
    rl_tail.add_argument("--limit", type=int, default=50)
    rl_tail.add_argument("--json", action="store_true")
    rl_tail.set_defaults(func=_cmd_relay)
    rl_query = rl_sub.add_parser("query", help="Filter relay events")
    rl_query.add_argument("--source", default="all")
    rl_query.add_argument("--kind", default="")
    rl_query.add_argument("--request-id", default="")
    rl_query.add_argument("--since", default="")
    rl_query.add_argument("--limit", type=int, default=50)
    rl_query.add_argument("--json", action="store_true")
    rl_query.set_defaults(func=_cmd_relay)
    rl_corr = rl_sub.add_parser("correlate", help="Correlate events by request_id")
    rl_corr.add_argument("request_id")
    rl_corr.add_argument("--json", action="store_true")
    rl_corr.set_defaults(func=_cmd_relay)
    rl_export = rl_sub.add_parser("export", help="Export redacted relay snapshot")
    rl_export.add_argument("--output", default="")
    rl_export.add_argument("--source", default="all")
    rl_export.add_argument("--limit", type=int, default=200)
    rl_export.add_argument("--json", action="store_true")
    rl_export.set_defaults(func=_cmd_relay)

    sp = sub.add_parser("sprint", help="Sprint ledger — track Aegis work in iterations")
    sp_sub = sp.add_subparsers(dest="sprint_action", required=True)
    sp_seed = sp_sub.add_parser("seed", help="Insert the catalog (existing IDs kept)")
    sp_seed.add_argument("--force", action="store_true")
    sp_seed.add_argument("--json", action="store_true")
    sp_seed.set_defaults(func=_cmd_sprint)
    sp_add = sp_sub.add_parser("add", help="Add a sprint")
    sp_add.add_argument("--title", required=True)
    sp_add.add_argument("--goal", default="")
    sp_add.add_argument("--status", default="planned", choices=["planned", "active", "blocked", "parked"])
    sp_add.add_argument("--json", action="store_true")
    sp_add.set_defaults(func=_cmd_sprint)
    sp_list = sp_sub.add_parser("list", help="List sprints")
    sp_list.add_argument("--status", default="")
    sp_list.add_argument("--json", action="store_true")
    sp_list.set_defaults(func=_cmd_sprint)
    sp_show = sp_sub.add_parser("show", help="Print one sprint as JSON")
    sp_show.add_argument("sprint_id")
    sp_show.set_defaults(func=_cmd_sprint)
    sp_start = sp_sub.add_parser("start", help="Mark a sprint active")
    sp_start.add_argument("sprint_id")
    sp_start.add_argument("--json", action="store_true")
    sp_start.set_defaults(func=_cmd_sprint)
    sp_done = sp_sub.add_parser("complete", help="Close a sprint with verified evidence")
    sp_done.add_argument("sprint_id")
    sp_done.add_argument("--verified", required=True)
    sp_done.add_argument("--evidence", default="")
    sp_done.add_argument("--json", action="store_true")
    sp_done.set_defaults(func=_cmd_sprint)
    sp_block = sp_sub.add_parser("block", help="Block a sprint")
    sp_block.add_argument("sprint_id")
    sp_block.add_argument("--reason", default="")
    sp_block.add_argument("--blocked-by", default="")
    sp_block.add_argument("--json", action="store_true")
    sp_block.set_defaults(func=_cmd_sprint)
    sp_park = sp_sub.add_parser("park", help="Park a sprint")
    sp_park.add_argument("sprint_id")
    sp_park.add_argument("--reason", default="")
    sp_park.add_argument("--json", action="store_true")
    sp_park.set_defaults(func=_cmd_sprint)
    sp_unpark = sp_sub.add_parser("unpark", help="Move a parked/blocked sprint to planned")
    sp_unpark.add_argument("sprint_id")
    sp_unpark.add_argument("--reason", default="")
    sp_unpark.add_argument("--json", action="store_true")
    sp_unpark.set_defaults(func=_cmd_sprint)
    sp_task = sp_sub.add_parser("task", help="Add or complete a sprint task")
    sp_task_sub = sp_task.add_subparsers(dest="task_action", required=True)
    sp_task_add = sp_task_sub.add_parser("add")
    sp_task_add.add_argument("sprint_id")
    sp_task_add.add_argument("--title", required=True)
    sp_task_add.add_argument("--json", action="store_true")
    sp_task_add.set_defaults(func=_cmd_sprint)
    sp_task_done = sp_task_sub.add_parser("done")
    sp_task_done.add_argument("sprint_id")
    sp_task_done.add_argument("task_id")
    sp_task_done.add_argument("--evidence", default="")
    sp_task_done.add_argument("--json", action="store_true")
    sp_task_done.set_defaults(func=_cmd_sprint)
    sp_rep = sp_sub.add_parser("report", help="Roll up sprints + canonical register")
    sp_rep.add_argument("--repo", default="")
    sp_rep.add_argument("--json", action="store_true")
    sp_rep.set_defaults(func=_cmd_sprint)
    sp_board = sp_sub.add_parser("board", help="Write 05_SPRINT_BOARD.md")
    sp_board.add_argument("--write", default="")
    sp_board.add_argument("--json", action="store_true")
    sp_board.set_defaults(func=_cmd_sprint)
    sp_reconcile = sp_sub.add_parser(
        "reconcile",
        help="One-time SP-023/024/025 identity correction (idempotent)",
    )
    sp_reconcile.add_argument("--json", action="store_true")
    sp_reconcile.set_defaults(func=_cmd_sprint)

    hm = sub.add_parser("hermes", help="Read-only Hermes search/resolve")
    hm_sub = hm.add_subparsers(dest="hermes_action", required=True)
    hm_search = hm_sub.add_parser("search", help="Unified local index search")
    hm_search.add_argument("query")
    hm_search.add_argument("--kind", default="", help="file|note|project")
    hm_search.add_argument("--tag", default="")
    hm_search.add_argument("--project", default="")
    hm_search.add_argument("--limit", type=int, default=20)
    hm_search.set_defaults(func=_cmd_hermes)
    hm_resolve = hm_sub.add_parser("resolve", help="Bounded graph context packet")
    hm_resolve.add_argument("query")
    hm_resolve.add_argument("--project", default="")
    hm_resolve.add_argument("--max-notes", type=int, default=8)
    hm_resolve.set_defaults(func=_cmd_hermes)

    kn = sub.add_parser("kernel", help="Agent kernel: process, memory, drivers, syscalls")
    kn_sub = kn.add_subparsers(dest="kernel_action", required=True)
    for name, help_text in (
        ("status", "Kernel status"),
        ("ps", "Process table"),
        ("mem", "Memory RSS"),
        ("drivers", "Driver table"),
        ("score", "Product OS scorecard"),
        ("budget", "Budget via syscall"),
        ("api_spec", "Frozen API spec"),
    ):
        sp = kn_sub.add_parser(name, help=help_text)
        sp.add_argument("--json", action="store_true")
        if name == "ps":
            sp.add_argument("--limit", type=int, default=20)
        sp.set_defaults(func=_cmd_kernel)
    kn_pack = kn_sub.add_parser("pack", help="Pack via kernel syscall")
    kn_pack.add_argument("path", nargs="+")
    kn_pack.add_argument("--task", default="kernel-pack")
    kn_pack.add_argument("--json", action="store_true")
    kn_pack.set_defaults(func=_cmd_kernel)
    kn_sys = kn_sub.add_parser("syscall", help="Dispatch a named syscall")
    kn_sys.add_argument("name")
    kn_sys.add_argument("--json", action="store_true")
    kn_sys.set_defaults(func=_cmd_kernel)

    os_p = sub.add_parser("os", help="Master Aegis product OS (init/backup/score/bench)")
    os_sub = os_p.add_subparsers(dest="os_action", required=True)
    os_score = os_sub.add_parser("score", help="Layer scorecard")
    os_score.add_argument("--json", action="store_true")
    os_score.set_defaults(func=_cmd_os)
    os_init = os_sub.add_parser("init", help="Create portable AEGIS_HOME")
    os_init.add_argument("--home", default="")
    os_init.add_argument("--json", action="store_true")
    os_init.set_defaults(func=_cmd_os)
    os_bak = os_sub.add_parser("backup", help="Tar.gz the data plane")
    os_bak.add_argument("--out", dest="dest", default="")
    os_bak.add_argument("--json", action="store_true")
    os_bak.set_defaults(func=_cmd_os)
    os_res = os_sub.add_parser("restore", help="Restore a backup archive")
    os_res.add_argument("--from", dest="archive", required=True)
    os_res.add_argument("--home", default="")
    os_res.add_argument("--json", action="store_true")
    os_res.set_defaults(func=_cmd_os)
    os_un = os_sub.add_parser("uninstall", help="Delete data plane only")
    os_un.add_argument("--yes", action="store_true")
    os_un.add_argument("--home", default="")
    os_un.add_argument("--json", action="store_true")
    os_un.set_defaults(func=_cmd_os)
    os_bench = os_sub.add_parser("bench", help="Hash-cache + pack performance")
    os_bench.add_argument("path", nargs="+")
    os_bench.add_argument("--rounds", type=int, default=12)
    os_bench.add_argument("--json", action="store_true")
    os_bench.set_defaults(func=_cmd_os)
    os_ready = os_sub.add_parser("ready", help="Release gate: product + freeze + D/M health")
    os_ready.add_argument("--json", action="store_true")
    os_ready.set_defaults(func=_cmd_os)

    api_p = sub.add_parser("api", help="Frozen /v1 contract")
    api_sub = api_p.add_subparsers(dest="api_action", required=True)
    api_spec = api_sub.add_parser("spec", help="Print frozen OpenAPI-floor spec")
    api_spec.set_defaults(func=_cmd_api)
    api_chk = api_sub.add_parser("check", help="Validate kernel payload against spec")
    api_chk.set_defaults(func=_cmd_api)

    yld = sub.add_parser("yield", help="Honest yield proof (no fake savings_percent)")
    yld_sub = yld.add_subparsers(dest="yield_action", required=True)
    yld_rep = yld_sub.add_parser("report", help="Ledger counterfactual + admission flag")
    yld_rep.set_defaults(func=_cmd_yield)
    yld_pr = yld_sub.add_parser("prove", help="Naive vs pack on given files")
    yld_pr.add_argument("path", nargs="+")
    yld_pr.add_argument("--task", default="yield-prove")
    yld_pr.set_defaults(func=_cmd_yield)

    dec = sub.add_parser("decisions", help="Health of every D- in the canonical register")
    dec_sub = dec.add_subparsers(dest="decisions_action", required=True)
    dec_h = dec_sub.add_parser("health", help="Probe D-011..D-031")
    dec_h.add_argument("--json", action="store_true")
    dec_h.set_defaults(func=_cmd_decisions)
    dec_m = dec_sub.add_parser("measure", help="Authorized Hermes naive vs pack usage")
    dec_m.add_argument("path")
    dec_m.add_argument("--model", default="xiaomi/mimo-v2.5-pro")
    dec_m.add_argument("--provider", default="nous")
    dec_m.set_defaults(func=_cmd_decisions)

    mods = sub.add_parser("modules", help="Health of every budget-aware M- module")
    mods_sub = mods.add_subparsers(dest="modules_action", required=True)
    mods_h = mods_sub.add_parser("health", help="Probe M-001..M-014")
    mods_h.add_argument("--json", action="store_true")
    mods_h.set_defaults(func=_cmd_modules)
    mods_m = mods_sub.add_parser("measure", help="Authorized Hermes naive vs pack usage")
    mods_m.add_argument("path")
    mods_m.add_argument("--model", default="xiaomi/mimo-v2.5-pro")
    mods_m.add_argument("--provider", default="nous")
    mods_m.set_defaults(func=_cmd_modules)

    pr = sub.add_parser("price", help="Honest AGIS product quote (not token-bill valuation)")
    pr_sub = pr.add_subparsers(dest="price_action", required=True)
    pr_q = pr_sub.add_parser("quote", help="Then vs now bands + replacement cost")
    pr_q.add_argument("--json", action="store_true")
    pr_q.set_defaults(func=_cmd_price)
    pr_s = pr_sub.add_parser("skus", help="Source vs exclusive vs hosted-refused")
    pr_s.add_argument("--json", action="store_true")
    pr_s.set_defaults(func=_cmd_price)
    pr_p = pr_sub.add_parser("pitch", help="Who to sell, how to demo, what not to claim")
    pr_p.add_argument("--json", action="store_true")
    pr_p.set_defaults(func=_cmd_price)

    demo = sub.add_parser("demo", help="Path A four-beat rehearsal + 14-day buyer clock")
    demo_sub = demo.add_subparsers(dest="demo_action", required=True)
    demo_start = demo_sub.add_parser("start", help="Start 14-day operator-owner clock")
    demo_start.add_argument("--reset", action="store_true")
    demo_start.add_argument("--json", action="store_true")
    demo_start.set_defaults(func=_cmd_demo)
    demo_run = demo_sub.add_parser("run", help="Rehearse os ready → pack twice → quote → honesty")
    demo_run.add_argument("path", nargs="*")
    demo_run.add_argument("--skip-pack", action="store_true")
    demo_run.add_argument("--json", action="store_true")
    demo_run.set_defaults(func=_cmd_demo)
    demo_buyer = demo_sub.add_parser("buyer", help="Record one named operator-owner (no outreach)")
    demo_buyer.add_argument("name")
    demo_buyer.add_argument("--json", action="store_true")
    demo_buyer.set_defaults(func=_cmd_demo)
    demo_st = demo_sub.add_parser("status", help="Days left and whether a buyer is named")
    demo_st.add_argument("--json", action="store_true")
    demo_st.set_defaults(func=_cmd_demo)
    demo_sc = demo_sub.add_parser("script", help="Spoken four beats (no pack)")
    demo_sc.add_argument("--json", action="store_true")
    demo_sc.set_defaults(func=_cmd_demo)


    intake = sub.add_parser("intake", help="Ingest and triage issues/reports into AEGIS")
    intake_sub = intake.add_subparsers(dest="intake_action", required=True)
    intake_add = intake_sub.add_parser("add", help="Ingest an issue or report payload")
    intake_add.add_argument("text", help="Message text (e.g. '!BUG [mod] summary')")
    intake_add.add_argument("--sender", default="local", help="Sender identifier (e.g. phone/handle)")
    intake_add.add_argument("--channel", default="cli", help="Source channel")
    intake_add.add_argument("--json", action="store_true")
    intake_add.set_defaults(func=_cmd_intake)

    intake_list = intake_sub.add_parser("list", help="List recent ingested reports")
    intake_list.add_argument("--limit", type=int, default=10)
    intake_list.add_argument("--json", action="store_true")
    intake_list.set_defaults(func=_cmd_intake)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        print(f"aegis: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
