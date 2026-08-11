"""
Agent preflight — one shot: pack → quality → receipt → budget → output lane.

Auto-recovery: if implement pack fails quality (strict), retry explore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class PreflightResult:
    ok: bool
    exit_code: int
    mode_requested: str
    mode_used: str
    recovered: bool
    errors: List[str] = field(default_factory=list)
    pack_exit: int = 0
    quality_grade: str = "pass"
    reserve_signal: str = "ok"
    pack_id: Optional[str] = None
    output_profile: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "mode_requested": self.mode_requested,
            "mode_used": self.mode_used,
            "recovered": self.recovered,
            "errors": self.errors,
            "pack_exit": self.pack_exit,
            "quality_grade": self.quality_grade,
            "reserve_signal": self.reserve_signal,
            "pack_id": self.pack_id,
            "output_profile": self.output_profile,
            "summary": self.summary,
        }


def _do_pack(
    *,
    paths: Sequence[str],
    task: str,
    mode: str,
    targets: Sequence[str],
    strict: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    """Run product pack path; return payload + gate + exit semantics."""
    from aegis.bento import assemble
    from aegis.ledger import record
    from aegis.pack_cache import get_or_none, pack_key, save_pack
    from aegis.quality import evaluate_pack
    from aegis.receipt import write_last_receipt

    path_list = list(paths)
    snippets = []
    sources: Dict[str, str] = {}
    for p in path_list:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        snippets.append({"path": p, "content": content})
        sources[p] = content

    targets = list(targets)
    pack_id, cached, _cache_meta = get_or_none(
        mode, path_list, task, targets=targets, include_task=False
    )
    reuse = False
    if cached:
        payload = dict(cached)
        payload["reuse"] = True
        payload["core_task"] = task
        payload["pack_id"] = pack_id
        reuse = True
        raw = int(payload.get("total_raw_tokens", 0))
        if not dry_run:
            entry = record(
                kind="reuse_hit",
                task=f"preflight:{mode}:{task[:40]}",
                mode=mode,
                raw_in=raw,
                processed_in=0,
                pack_id=pack_id,
                reuse=True,
                meta={"paths": path_list, "targets": targets, "preflight": True},
            )
            payload["ledger_entry"] = entry
            write_last_receipt(entry, payload)
    else:
        payload = assemble(
            core_task=task,
            code_snippets=snippets,
            mode=mode,
            targets=targets,
        )
        if pack_id is None:
            pack_id = pack_key(mode, path_list, task, targets=targets)
        payload["pack_id"] = pack_id
        payload["reuse"] = False
        payload["cache_policy"] = "mode_paths_targets"
        if not dry_run:
            entry = record(
                kind="pack",
                task=f"preflight:{mode}:{task[:40]}",
                mode=mode,
                raw_in=int(payload["total_raw_tokens"]),
                processed_in=int(payload["total_compressed_tokens"]),
                pack_id=pack_id,
                reuse=False,
                meta={
                    "paths": path_list,
                    "targets": targets,
                    "engine": payload.get("engine"),
                    "preflight": True,
                    "token_accounting": payload.get("token_accounting"),
                },
            )
            payload["ledger_entry"] = entry
            write_last_receipt(entry, payload)

    gate = evaluate_pack(payload, mode=mode, targets=targets, sources=sources)
    payload["quality"] = gate.as_dict()
    if not dry_run and not reuse and not (strict and gate.strict_fail):
        save_pack(pack_id, payload)

    exit_code = 3 if (strict and gate.strict_fail) else 0
    return {
        "payload": payload,
        "gate": gate,
        "pack_id": pack_id,
        "exit_code": exit_code,
        "reuse": reuse,
    }


def run_preflight(
    *,
    paths: Sequence[str],
    task: str,
    mode: str = "explore",
    targets: Optional[Sequence[str]] = None,
    strict: bool = False,
    output_profile: Optional[str] = None,
    no_output: bool = False,
    dry_run: bool = False,
    recover: bool = True,
) -> PreflightResult:
    from aegis.fund import surplus_snapshot
    from aegis.ledger import generate_report
    from aegis.output_lane import activate_output, mode_default_profile
    from aegis.receipt import load_last_receipt

    mode_req = (mode or "explore").lower()
    mode_used = mode_req
    errors: List[str] = []
    recovered = False
    targets = list(targets or [])

    try:
        result = _do_pack(
            paths=paths,
            task=task,
            mode=mode_used,
            targets=targets,
            strict=strict or mode_used == "implement",
            dry_run=dry_run,
        )
    except FileNotFoundError as exc:
        return PreflightResult(
            ok=False,
            exit_code=1,
            mode_requested=mode_req,
            mode_used=mode_used,
            recovered=False,
            errors=[str(exc)],
            pack_exit=1,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pack exception: {exc}")
        result = {"exit_code": 1, "gate": None, "pack_id": None, "payload": {}}

    pack_exit = int(result.get("exit_code", 1))
    gate = result.get("gate")

    if pack_exit == 3 and recover and mode_used == "implement":
        errors.append("implement quality fail → recover explore")
        mode_used = "explore"
        recovered = True
        try:
            result = _do_pack(
                paths=paths,
                task=task,
                mode="explore",
                targets=[],
                strict=False,
                dry_run=dry_run,
            )
            pack_exit = int(result.get("exit_code", 0))
            gate = result.get("gate")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"recover failed: {exc}")
            pack_exit = 1

    pack_id = result.get("pack_id") or (load_last_receipt() or {}).get("pack_id")
    quality_grade = "pass"
    if gate is not None:
        quality_grade = gate.grade
    elif result.get("payload"):
        quality_grade = (result["payload"].get("quality") or {}).get("grade", "pass")

    report = generate_report()
    surplus = surplus_snapshot()
    reserve = report.get("reserve_signal", "ok")

    out_prof = None
    out_receipt = None
    if not no_output and pack_exit == 0:
        out_prof = output_profile or mode_default_profile(mode_used)
        try:
            out_receipt = activate_output(
                profile=out_prof,
                mode=mode_used,
                task=f"preflight:{task[:40]}",
                dry_run=dry_run,
                pack_id=pack_id,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"output lane: {exc}")

    ok = pack_exit == 0 and reserve != "hard_stop"
    exit_code = 0 if ok else (3 if pack_exit == 3 else 1)
    if reserve == "hard_stop":
        errors.append("reserve hard_stop — throttle agent fan-out")
        exit_code = 4

    receipt = load_last_receipt()
    return PreflightResult(
        ok=ok,
        exit_code=exit_code,
        mode_requested=mode_req,
        mode_used=mode_used,
        recovered=recovered,
        errors=errors,
        pack_exit=pack_exit,
        quality_grade=str(quality_grade),
        reserve_signal=str(reserve),
        pack_id=pack_id,
        output_profile=out_prof,
        summary={
            "remaining_pct": report.get("remaining_weekly_capacity_percent"),
            "reuse_hit_rate_percent": report.get("reuse_hit_rate_percent"),
            "tokens_saved_week": report.get("total_tokens_saved"),
            "raw_out_week": report.get("raw_out"),
            "processed_out_week": report.get("processed_out"),
            "wish_jar": surplus.get("available_credits"),
            "raw_out_est": (out_receipt or {}).get("raw_out"),
            "processed_out_est": (out_receipt or {}).get("processed_out"),
            "output_saved_est": (out_receipt or {}).get("tokens_saved_est"),
            "token_accounting": "code_only",
            "pack_reduction": (result.get("payload") or {}).get(
                "overall_reduction_percent"
            ),
            "receipt": receipt,
            "output": out_receipt,
            "payload": result.get("payload") if not dry_run else None,
        },
    )


def format_preflight_banner(result: PreflightResult) -> str:
    lines = [
        "[AEGIS PREFLIGHT]",
        f"ok={result.ok} exit={result.exit_code} "
        f"mode={result.mode_requested}→{result.mode_used} "
        f"recovered={result.recovered}",
        f"quality={result.quality_grade} reserve={result.reserve_signal} "
        f"pack_id={result.pack_id}",
        f"output_profile={result.output_profile} "
        f"out_save_est={result.summary.get('output_saved_est')}",
        f"remaining={result.summary.get('remaining_pct')}% "
        f"reuse={result.summary.get('reuse_hit_rate_percent')}% "
        f"wish_jar={result.summary.get('wish_jar')}",
        f"token_accounting={result.summary.get('token_accounting')} "
        f"pack_cut={result.summary.get('pack_reduction')}%",
    ]
    for e in result.errors:
        lines.append(f"error: {e}")
    return "\n".join(lines)
