"""
Aegis Intelligence Layer — autonomous infinite compound loop.

tick() is production-hardened:
  - global lock, partial-failure isolation per step
  - surplus sync → usage → forecast → cache → queue → policy → invest → report
  - Absolute Form: reserve healthy before auto-invest
  - weekly policy-nudge idempotency
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from aegis.cache_optimizer import hit_rate, load_stats, optimize_cache
from aegis.config import AegisConfig, load_config, opt_in
from aegis.forecast import predict_budget
from aegis.fund import surplus_snapshot, sync_from_ledger
from aegis.ideas import (
    add_idea,
    invest_in_idea,
    list_ideas,
    seed_starter_ideas,
    suggest_ideas,
)
from aegis.ledger import record
from aegis.memory import memory_stats
from aegis.paths import ensure_home, intel_state_path, reports_dir
from aegis.policy_nudges import apply_policy_nudges, nudge_summary
from aegis.usage_intel import analyze_usage, waste_signals

_GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}

_tick_lock = threading.RLock()
_bg_thread: Optional[threading.Thread] = None
_bg_stop = threading.Event()
_bg_lock = threading.Lock()

INTEL_LAYER_VERSION = "1.1.1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "ticks": 0,
        "last_tick_ts": None,
        "last_report_week": None,
        "actions_lifetime": 0,
        "auto_invests": 0,
        "fixes_applied": 0,
        "compound_cycles": 0,
        "applied_fixes_week": None,
        "applied_fix_ids": [],
        "last_errors": [],
        "layer_version": INTEL_LAYER_VERSION,
    }


def load_intel_state() -> Dict[str, Any]:
    ensure_home()
    path = intel_state_path()
    base = _default_state()
    if not path.is_file():
        return dict(base)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(base)
        base.update(data)
    except (OSError, json.JSONDecodeError):
        pass
    return base


def save_intel_state(state: Dict[str, Any]) -> None:
    ensure_home()
    path = intel_state_path()
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(state, indent=2, default=str)
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except OSError:
        path.write_text(payload, encoding="utf-8")


def _grade_ok(grade: str, min_grade: str) -> bool:
    return _GRADE_ORDER.get(str(grade).upper(), 0) >= _GRADE_ORDER.get(
        str(min_grade).upper(), 3
    )


def _week_fix_set(state: Dict[str, Any], week: str) -> Set[str]:
    if state.get("applied_fixes_week") != week:
        return set()
    raw = state.get("applied_fix_ids") or []
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw}


def _auto_queue_ideas(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    created: List[Dict[str, Any]] = []
    try:
        existing_titles = {i.get("title") for i in list_ideas(by_roi=False)}
    except Exception:  # noqa: BLE001
        existing_titles = set()

    for sig in signals or []:
        title = f"[auto] {sig.get('title')}"
        if title in existing_titles:
            continue
        try:
            idea = add_idea(
                title,
                body=str(sig.get("detail") or ""),
                tags=["aegis", "auto", "intel", str(sig.get("id") or "fix")],
                cost_estimate_tokens=2000,
                expected_savings_tokens=int(sig.get("expected_savings_tokens") or 5000),
                confidence="high"
                if sig.get("severity") in ("high", "critical")
                else "medium",
                source="intel_auto",
            )
            created.append(idea)
            existing_titles.add(title)
        except Exception:  # noqa: BLE001
            continue

    try:
        suggestions = suggest_ideas()
    except Exception:  # noqa: BLE001
        suggestions = []

    for s in suggestions:
        if s.get("source") != "surplus_suggest":
            continue
        if not s.get("expected_savings_tokens"):
            continue
        title = str(s.get("title") or "")
        if not title or title in existing_titles:
            continue
        try:
            idea = add_idea(
                title,
                body=str(s.get("body") or ""),
                tags=list(s.get("tags") or ["aegis"]),
                cost_estimate_tokens=int(s.get("cost_estimate_tokens") or 2000),
                expected_savings_tokens=int(s.get("expected_savings_tokens") or 5000),
                confidence=str(s.get("confidence") or "medium"),
                source="intel_suggest",
            )
            created.append(idea)
            existing_titles.add(title)
        except Exception:  # noqa: BLE001
            continue
    return created


def _auto_invest(cfg: AegisConfig, forecast: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not opt_in(cfg, "auto_invest"):
        return []
    # Absolute Form: freeze invest under projected hard_stop or unhealthy reserve
    if forecast.get("projected_signal") == "hard_stop":
        return [{"ok": False, "reason": "projected hard_stop — invest frozen"}]
    try:
        snap = surplus_snapshot(cfg)
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "reason": f"surplus error: {exc}"}]

    if snap.get("reserve_signal") != "ok":
        return [
            {
                "ok": False,
                "reason": "cannot invest",
                "signal": snap.get("reserve_signal"),
            }
        ]
    if not snap.get("can_invest"):
        return [{"ok": False, "reason": "no investable credits"}]

    min_grade = getattr(cfg, "min_roi_grade_auto", None) or "B"
    try:
        queued = list_ideas(status="queued", by_roi=True)
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "reason": f"ideas error: {exc}"}]

    candidates = [
        i for i in queued if _grade_ok(str(i.get("roi_grade") or "C"), min_grade)
    ]
    if not candidates:
        return [{"ok": False, "reason": f"no queued ideas grade≥{min_grade}"}]

    top = candidates[0]
    need = max(
        0,
        int(top.get("cost_estimate_tokens") or 0) - int(top.get("funded_credits") or 0),
    )
    budget = int(snap.get("available_credits") or 0)
    if need <= 0:
        need = min(1000, budget)
    amount = min(need, budget)
    if amount <= 0:
        return [{"ok": False, "reason": "no credits"}]

    try:
        result = invest_in_idea(str(top["id"]), credits=amount)
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "reason": f"invest failed: {exc}"}]
    result["idea_title"] = top.get("title")
    result["roi_grade"] = top.get("roi_grade")
    return [result]


def write_weekly_report(
    *,
    usage: Dict[str, Any],
    forecast: Dict[str, Any],
    surplus: Dict[str, Any],
    tick_actions: List[str],
    budget: Optional[Dict[str, Any]] = None,
) -> str:
    ensure_home()
    rdir = reports_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    week = str(usage.get("week") or "unknown")
    path = rdir / f"weekly_{week}.json"
    burn_block: Dict[str, Any] = {}
    try:
        from aegis.burn import burn_status, burn_summary_table

        burn_block = burn_summary_table(
            burn_status(usage=usage, forecast=forecast, record_events=True)
        )
    except Exception:  # noqa: BLE001
        burn_block = {}

    report = {
        "kind": "aegis_weekly_roi",
        "layer_version": INTEL_LAYER_VERSION,
        "week": week,
        "generated_ts": _now(),
        "usage": usage,
        "forecast": forecast,
        "burn": burn_block,
        "budget_aware": budget or {},
        "surplus": surplus,
        "cache": {
            "hit_rate_percent": hit_rate(),
            "stats": load_stats(),
        },
        "memory": memory_stats(),
        "ideas": list_ideas(by_roi=True)[:15],
        "tick_actions": tick_actions,
        "compound_message": (
            "Savings → surplus credits → highest-ROI ideas → more savings. "
            "Loop is autonomous when auto_tick/auto_invest are on. "
            "Budget-Aware Mode sheds low-ROI work before hitting hard burn stops."
        ),
        "absolute_form": {
            "reserve_floor": surplus.get("reserve_floor"),
            "reserve_signal": surplus.get("reserve_signal"),
            "sustain_first": True,
        },
    }
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = rdir / f"weekly_{week}.md"
    md.write_text(_format_weekly_md(report), encoding="utf-8")
    return str(path)


def _fmt_num(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v if v is not None else "—")


def _format_weekly_md(report: Dict[str, Any]) -> str:
    u = report.get("usage") or {}
    f = report.get("forecast") or {}
    s = report.get("surplus") or {}
    lines = [
        f"# Aegis Weekly ROI — {report.get('week')}",
        "",
        f"Generated: {report.get('generated_ts')} · layer {report.get('layer_version')}",
        "",
        "## Budget shield",
        f"- Reserve: **{u.get('reserve_signal')}** ({u.get('remaining_pct')}% remaining)",
        f"- Saved: **{_fmt_num(u.get('tokens_saved'))}** tokens · reduction **{u.get('reduction_percent')}%**",
        f"- Cache hit rate: **{u.get('cache_hit_rate_percent')}%**",
        f"- Projected week-end signal: **{f.get('projected_signal')}** "
        f"({f.get('projected_remaining_pct')}% left)",
        f"- Avg daily burn: **{_fmt_num(f.get('avg_daily_burn'))}** · "
        f"safe daily: **{_fmt_num(f.get('recommended_daily_budget'))}**",
        "",
        "## Burn health",
    ]
    # Prefer live burn_status summary (SSOT)
    bs = f.get("burn_status") if isinstance(f.get("burn_status"), dict) else None
    bw = f.get("burn_warning") if isinstance(f.get("burn_warning"), dict) else None
    if not bs:
        try:
            from aegis.burn import burn_summary_table

            bs = burn_summary_table()
        except Exception:  # noqa: BLE001
            bs = {}
    if bs:
        lines.extend(
            [
                f"- Level: **{bs.get('level', '—')}** · ratio **{bs.get('ratio_pct', '—')}%** of safe daily",
                f"- Usage: **{_fmt_num(bs.get('avg_daily_burn'))}** / safe **{_fmt_num(bs.get('safe_daily'))}** tok/day",
                f"- Bands: caution≥{(bs.get('bands') or {}).get('caution_at', 0.8):.0%} · "
                f"warn≥{(bs.get('bands') or {}).get('warn_at', 1.0):.0%} · "
                f"critical≥{(bs.get('bands') or {}).get('critical_at', 1.25):.0%}",
                f"- Message: {bs.get('message') or '—'}",
                f"- Action: {bs.get('fix_detail') or '—'}",
                f"- Budget-aware workers: **{bs.get('recommended_workers', '—')}**",
                "",
                "### Top consumers (week)",
            ]
        )
        for c in (bs.get("top_consumers") or [])[:8]:
            lines.append(
                f"- {c.get('dimension')}:{c.get('name')} · "
                f"count={c.get('count')} · share={c.get('share_pct')}%"
            )
        lines.append("")
    elif bw and bw.get("active"):
        lines.extend(
            [
                f"- **CRITICAL:** {bw.get('message')}",
                f"- Fix: {bw.get('fix_detail')}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- Burn within safe band.",
                "- Keep fan-out modest so parallel tasks stay inside the allowance.",
                "",
            ]
        )
    ba = report.get("budget_aware") or {}
    lines.extend(["## Budget-Aware Mode", ""])
    if ba:
        lines.extend(
            [
                f"- Band: **{ba.get('band', 'ok')}** (level={ba.get('level', 'ok')})",
                f"- Summary: {ba.get('menu_summary') or 'full capacity'}",
                f"- Shed: {', '.join(ba.get('modules_shed') or []) or 'none'}",
                f"- Throttled: {', '.join(ba.get('modules_throttled') or []) or 'none'}",
                f"- Workers: **{ba.get('recommended_workers', '—')}**",
                f"- Source preference: {', '.join(ba.get('source_preference') or [])}",
                "",
            ]
        )
        if ba.get("transition"):
            tr = ba["transition"]
            lines.append(
                f"- Transition: {tr.get('from_band')}→{tr.get('to_band')} "
                f"@ ratio={tr.get('ratio')}"
            )
            lines.append("")
    else:
        lines.extend(["- Full capacity (budget-aware inactive or not recorded).", ""])

    lines.extend(
        [
            "## Compound economy",
            f"- Available credits: **{_fmt_num(s.get('available_credits'))}**",
            f"- Lifetime saved: **{_fmt_num(s.get('lifetime_saved'))}**",
            f"- Lifetime invested: **{_fmt_num(s.get('lifetime_invested'))}**",
            f"- Can invest: {s.get('can_invest')}",
            "",
            "## Forecast advice",
        ]
    )
    for a in f.get("advice") or []:
        lines.append(f"- {a}")
    lines.extend(["", "## Actions this cycle"])
    for a in report.get("tick_actions") or []:
        lines.append(f"- {a}")
    lines.extend(["", "## Top ideas (ROI)"])
    for idea in (report.get("ideas") or [])[:8]:
        lines.append(
            f"- [{idea.get('roi_grade')}] {idea.get('title')} "
            f"(score={idea.get('roi_score')}, status={idea.get('status')})"
        )
    lines.append("")
    lines.append(str(report.get("compound_message") or ""))
    lines.append("")
    return "\n".join(lines)


def tick(
    cfg: Optional[AegisConfig] = None,
    *,
    force_report: bool = False,
) -> Dict[str, Any]:
    """One autonomous compound cycle. Safe to call frequently (locked). Never raises."""
    with _tick_lock:
        errors: List[str] = []
        actions: List[str] = []
        fixes: List[Dict[str, Any]] = []
        invests: List[Dict[str, Any]] = []
        opt: Dict[str, Any] = {"hit_rate_percent": 0.0, "learned_fallbacks": {}, "actions": []}
        usage: Dict[str, Any] = {}
        forecast: Dict[str, Any] = {}
        surplus: Dict[str, Any] = {}
        signals: List[Dict[str, Any]] = []
        report_path = None

        try:
            cfg = cfg or load_config()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"config: {exc}", "actions": []}

        state = load_intel_state()
        budget_plan: Dict[str, Any] = {}

        def _allowed(module: str) -> bool:
            if not budget_plan:
                return True
            try:
                from aegis.budget_aware import should_run_module

                return should_run_module(budget_plan.get("plan") or {}, module)
            except Exception:  # noqa: BLE001
                return True

        # 1) surplus sync — sustain first (never shed)
        try:
            fund = sync_from_ledger(cfg)
            actions.append(
                f"surplus_sync credits={fund.get('available_credits')} "
                f"headroom={fund.get('headroom')} signal={fund.get('status')}"
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"surplus_sync: {exc}")
            actions.append(f"surplus_sync failed: {exc}")

        # 2) usage + forecast (never shed) — required for budget band
        try:
            usage = analyze_usage()
            signals = waste_signals(usage)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"usage: {exc}")
            usage = {"week": "unknown", "reserve_signal": "ok", "remaining_pct": 100.0}

        try:
            forecast = predict_budget(cfg, usage=usage)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"forecast: {exc}")
            forecast = {"projected_signal": "ok", "projected_remaining_pct": 100.0}

        # 2b) Budget-Aware Mode — sticky band + shed/throttle plan
        try:
            from aegis.budget_aware import evaluate as budget_evaluate

            burn_snap = forecast.get("burn_status") or {}
            # burn_status subset may lack full fields — burn_status() fills in
            from aegis.burn import burn_status as _burn_full

            burn_full = _burn_full(
                cfg, usage=usage, forecast=forecast, record_events=False
            )
            budget_plan = budget_evaluate(cfg, burn=burn_full, dry_run=False)
            actions.append(str(budget_plan.get("menu_summary") or "Budget: ok"))
            if budget_plan.get("modules_shed"):
                actions.append(
                    f"budget_shed: {', '.join(budget_plan['modules_shed'][:8])}"
                )
            if budget_plan.get("transition"):
                tr = budget_plan["transition"]
                actions.append(
                    f"budget_band {tr.get('from_band')}→{tr.get('to_band')} "
                    f"(ratio={tr.get('ratio')})"
                )
            # Privileged Continuity Bridge on emergency band
            try:
                from aegis.continuity import maybe_auto_bridge

                bridge = maybe_auto_bridge(cfg, band=budget_plan.get("band"))
                if bridge and bridge.get("ok"):
                    actions.append(
                        f"continuity_bridge: {bridge.get('paths', {}).get('markdown')}"
                    )
                    budget_plan["continuity_bridge"] = bridge.get("paths")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"continuity: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"budget_aware: {exc}")
            budget_plan = {}

        try:
            surplus = surplus_snapshot(cfg)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"surplus_snap: {exc}")
            surplus = {}

        # 3) seed ideas (sheddable)
        if _allowed("seed_ideas"):
            try:
                seeded = seed_starter_ideas()
                if seeded:
                    actions.append(f"seeded {len(seeded)} starter ideas")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"seed: {exc}")
        else:
            actions.append("seed_ideas: shed (stale ok) — budget-aware")

        # 4) cache optimize (sheddable / throttle)
        if _allowed("cache_optimize"):
            try:
                opt = optimize_cache()
                for a in opt.get("actions") or []:
                    actions.append(f"cache: {a}")
                if not opt.get("actions"):
                    actions.append(
                        f"cache: hit_rate={opt.get('hit_rate_percent')}% (stable)"
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"cache: {exc}")
                actions.append(f"cache failed: {exc}")
        else:
            actions.append("cache_optimize: shed (stale ok) — budget-aware")

        # 5) queue ideas (sheddable)
        if _allowed("auto_queue_ideas") and (
            opt_in(cfg, "auto_apply_fixes") or opt_in(cfg, "auto_invest")
        ):
            try:
                created = _auto_queue_ideas(signals)
                if created:
                    actions.append(f"queued {len(created)} auto ideas from signals")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"queue: {exc}")
        elif not _allowed("auto_queue_ideas"):
            actions.append("auto_queue_ideas: shed — budget-aware")

        # 6) policy nudges
        week = str(usage.get("week") or "unknown")
        already = _week_fix_set(state, week)
        if _allowed("policy_nudges"):
            try:
                cfg, fixes = apply_policy_nudges(
                    signals, cfg, already_applied=already, persist=True
                )
                if fixes:
                    state["fixes_applied"] = int(state.get("fixes_applied") or 0) + sum(
                        1 for f in fixes if not f.get("skipped")
                    )
                    actions.append(nudge_summary(fixes))
                    new_ids = {
                        str(f.get("fix"))
                        for f in fixes
                        if f.get("fix") and not f.get("skipped")
                    }
                    state["applied_fixes_week"] = week
                    state["applied_fix_ids"] = sorted(already | new_ids)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"policy: {exc}")
                actions.append(f"policy failed: {exc}")
        else:
            actions.append("policy_nudges: shed — budget-aware")

        try:
            cfg = load_config()
        except Exception:  # noqa: BLE001
            pass

        # 7) auto-invest
        if _allowed("auto_invest"):
            try:
                invests = _auto_invest(cfg, forecast)
                for inv in invests:
                    if inv.get("ok"):
                        state["auto_invests"] = int(state.get("auto_invests") or 0) + 1
                        actions.append(
                            f"auto_invest {inv.get('invested')} → {inv.get('idea_title')} "
                            f"[{inv.get('roi_grade')}]"
                        )
                    elif inv.get("reason"):
                        actions.append(f"invest_skip: {inv.get('reason')}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"invest: {exc}")
        else:
            actions.append("auto_invest: shed — budget-aware")

        # 8) weekly report (never shed)
        try:
            if force_report or state.get("last_report_week") != week:
                report_path = write_weekly_report(
                    usage=usage,
                    forecast=forecast,
                    surplus=surplus,
                    tick_actions=actions,
                    budget=budget_plan,
                )
                state["last_report_week"] = week
                actions.append(f"weekly_report {report_path}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"report: {exc}")

        # 9) ledger breadcrumb
        try:
            record(
                kind="intel_tick",
                task="intelligence:compound_tick",
                mode="intel",
                raw_in=0,
                processed_in=0,
                meta={
                    "layer": INTEL_LAYER_VERSION,
                    "actions": len(actions),
                    "signals": [s.get("id") for s in signals],
                    "cache_hit_rate": opt.get("hit_rate_percent"),
                    "projected_signal": forecast.get("projected_signal"),
                    "budget_band": budget_plan.get("band"),
                    "budget_shed": budget_plan.get("modules_shed"),
                    "errors": errors[:5],
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ledger: {exc}")

        state["ticks"] = int(state.get("ticks") or 0) + 1
        state["compound_cycles"] = int(state.get("compound_cycles") or 0) + 1
        state["actions_lifetime"] = int(state.get("actions_lifetime") or 0) + len(actions)
        state["last_tick_ts"] = _now()
        state["last_actions"] = actions[-20:]
        state["last_errors"] = errors[-10:]
        state["layer_version"] = INTEL_LAYER_VERSION
        try:
            save_intel_state(state)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"state: {exc}")

        return {
            "ok": len(errors) == 0 or bool(actions),
            "ts": state.get("last_tick_ts"),
            "layer_version": INTEL_LAYER_VERSION,
            "actions": actions,
            "signals": signals,
            "usage": usage,
            "forecast": forecast,
            "surplus": surplus,
            "budget_aware": {
                "band": budget_plan.get("band"),
                "level": budget_plan.get("level"),
                "menu_summary": budget_plan.get("menu_summary"),
                "modules_shed": budget_plan.get("modules_shed"),
                "modules_throttled": budget_plan.get("modules_throttled"),
                "recommended_workers": budget_plan.get("recommended_workers"),
                "source_preference": budget_plan.get("source_preference"),
            },
            "cache": {
                "hit_rate_percent": opt.get("hit_rate_percent"),
                "learned_fallbacks": opt.get("learned_fallbacks"),
            },
            "memory": memory_stats(),
            "fixes": fixes,
            "invests": invests,
            "report_path": report_path,
            "state": state,
            "errors": errors,
            "autonomous": bool(
                opt_in(cfg, "auto_tick") and opt_in(cfg, "auto_invest")
            ),
            "reserve_healthy": str(surplus.get("reserve_signal") or usage.get("reserve_signal"))
            == "ok",
            "message": (
                "compound cycle complete — savings reinvest into higher-ROI moves"
                if not errors
                else f"compound cycle partial ({len(errors)} error(s))"
            ),
        }


def intel_status(cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    try:
        cfg = cfg or load_config()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "layer_version": INTEL_LAYER_VERSION}

    try:
        usage = analyze_usage()
    except Exception:  # noqa: BLE001
        usage = {}

    try:
        fc = predict_budget(cfg, usage=usage)
    except Exception:  # noqa: BLE001
        fc = {}

    try:
        snap = surplus_snapshot(cfg)
    except Exception:  # noqa: BLE001
        snap = {}

    return {
        "ok": True,
        "version_layer": "intelligence",
        "layer_version": INTEL_LAYER_VERSION,
        "config": {
            "auto_tick": opt_in(cfg, "auto_tick"),
            "auto_invest": opt_in(cfg, "auto_invest"),
            "auto_apply_fixes": opt_in(cfg, "auto_apply_fixes"),
            "auto_memory": opt_in(cfg, "auto_memory"),
            "intel_tick_seconds": getattr(cfg, "intel_tick_seconds", 300),
            "min_roi_grade_auto": getattr(cfg, "min_roi_grade_auto", "B"),
            "reinvest_rate": cfg.reinvest_rate,
            "reserve_floor": cfg.reserve_floor,
        },
        "state": load_intel_state(),
        "usage": usage,
        "forecast": fc,
        "surplus": snap,
        "cache_hit_rate_percent": hit_rate(),
        "memory": memory_stats(),
        "signals": waste_signals(usage),
        "top_ideas": list_ideas(status="queued", by_roi=True)[:5],
        "bg_tick_running": bool(_bg_thread and _bg_thread.is_alive()),
        "reserve_healthy": str(snap.get("reserve_signal") or "ok") == "ok",
        "burn": (fc.get("burn_status") if isinstance(fc, dict) else None)
        or {},
        "budget_aware": _budget_status_safe(cfg),
    }


def _budget_status_safe(cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    try:
        from aegis.budget_aware import evaluate

        ev = evaluate(cfg, dry_run=True)
        return {
            "band": ev.get("band"),
            "level": ev.get("level"),
            "menu_summary": ev.get("menu_summary"),
            "modules_shed": ev.get("modules_shed"),
            "modules_throttled": ev.get("modules_throttled"),
            "recommended_workers": ev.get("recommended_workers"),
            "enabled": ev.get("enabled"),
        }
    except Exception:  # noqa: BLE001
        return {}


def start_background_ticks(cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    """Daemon helper: run tick on interval while process lives."""
    global _bg_thread
    with _bg_lock:
        try:
            cfg = cfg or load_config()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"config: {exc}"}

        if not opt_in(cfg, "auto_tick"):
            return {"ok": False, "message": "auto_tick disabled in config"}
        if _bg_thread and _bg_thread.is_alive():
            return {"ok": True, "message": "already running"}

        _bg_stop.clear()
        interval = max(60, int(getattr(cfg, "intel_tick_seconds", 300) or 300))

        def _loop() -> None:
            if _bg_stop.wait(5):
                return
            while not _bg_stop.is_set():
                try:
                    tick()
                except Exception:  # noqa: BLE001
                    pass
                if _bg_stop.wait(interval):
                    break

        _bg_thread = threading.Thread(
            target=_loop, name="aegis-intel-tick", daemon=True
        )
        _bg_thread.start()
        return {
            "ok": True,
            "message": "started",
            "interval_seconds": interval,
            "layer_version": INTEL_LAYER_VERSION,
        }


def stop_background_ticks() -> Dict[str, Any]:
    _bg_stop.set()
    return {"ok": True, "message": "stop signaled"}
