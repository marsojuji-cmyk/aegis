"""
Budget-Aware Mode — proactive control loop on top of burn bands.

Bands (same ratios as burn.py):
  ok / caution (0.80) / adaptive(warn 1.00) / emergency(critical 1.25)

When budget_aware_mode is on, the Intelligence Layer:
  - sticky band state machine with recovery hysteresis
  - ranks intel modules by cost × ROI × priority
  - scales frequency and sheds low-priority work
  - prefers cheap sources (cache/reuse/mock) under pressure
  - emits structured decisions for menu bar / dashboard / weekly report

Never-shed modules always run (surplus, usage, forecast, burn, weekly report).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from aegis.burn import LEVEL_ORDER, burn_status, level_for_ratio
from aegis.config import AegisConfig, load_config
from aegis.paths import budget_events_path, budget_state_path, ensure_home

_LOCK = threading.RLock()

# Map burn levels → budget band names (product language)
BAND_FROM_LEVEL = {
    "ok": "ok",
    "caution": "caution",
    "warn": "adaptive",
    "critical": "emergency",
}
LEVEL_FROM_BAND = {v: k for k, v in BAND_FROM_LEVEL.items()}


@dataclass
class ModuleSpec:
    """Static ranking for an intel module."""

    name: str
    cost: float = 1.0  # relative cost units
    signal_quality: float = 0.5  # 0–1 historical value
    freshness_need: float = 0.5  # 0–1 how bad stale is
    consumer_priority: float = 0.5  # 0–1 weekly report / dashboard weight
    never_shed: bool = False
    tags: List[str] = field(default_factory=list)

    def score(self) -> float:
        """Higher = keep longer. Cheap high-signal high-priority wins."""
        cost = max(0.05, float(self.cost))
        return round(
            (
                float(self.signal_quality) * 0.35
                + float(self.consumer_priority) * 0.35
                + float(self.freshness_need) * 0.15
                + (1.0 / cost) * 0.15
            )
            * 100.0,
            2,
        )


# Default catalog — tick steps + router-adjacent work
DEFAULT_MODULES: List[ModuleSpec] = [
    ModuleSpec("surplus_sync", cost=0.2, signal_quality=0.9, freshness_need=0.9, consumer_priority=1.0, never_shed=True, tags=["critical", "economy"]),
    ModuleSpec("usage_intel", cost=0.5, signal_quality=0.95, freshness_need=0.9, consumer_priority=1.0, never_shed=True, tags=["critical", "usage"]),
    ModuleSpec("forecast", cost=0.3, signal_quality=0.9, freshness_need=0.85, consumer_priority=1.0, never_shed=True, tags=["critical", "forecast"]),
    ModuleSpec("burn_status", cost=0.2, signal_quality=0.95, freshness_need=1.0, consumer_priority=1.0, never_shed=True, tags=["critical", "burn"]),
    ModuleSpec("weekly_report", cost=1.0, signal_quality=0.85, freshness_need=0.4, consumer_priority=1.0, never_shed=True, tags=["critical", "report"]),
    ModuleSpec("policy_nudges", cost=0.4, signal_quality=0.7, freshness_need=0.5, consumer_priority=0.7, never_shed=False, tags=["policy"]),
    ModuleSpec("cache_optimize", cost=1.2, signal_quality=0.75, freshness_need=0.4, consumer_priority=0.6, never_shed=False, tags=["cache"]),
    ModuleSpec("auto_invest", cost=0.8, signal_quality=0.8, freshness_need=0.5, consumer_priority=0.75, never_shed=False, tags=["economy", "invest"]),
    ModuleSpec("auto_queue_ideas", cost=1.0, signal_quality=0.55, freshness_need=0.3, consumer_priority=0.4, never_shed=False, tags=["ideas", "enrichment"]),
    ModuleSpec("seed_ideas", cost=0.6, signal_quality=0.4, freshness_need=0.1, consumer_priority=0.2, never_shed=False, tags=["ideas", "bootstrap"]),
    ModuleSpec("memory_capture", cost=0.7, signal_quality=0.6, freshness_need=0.5, consumer_priority=0.5, never_shed=False, tags=["memory"]),
    ModuleSpec("cross_model_memory_inject", cost=0.5, signal_quality=0.65, freshness_need=0.6, consumer_priority=0.55, never_shed=False, tags=["memory"]),
    ModuleSpec("exploratory_enrichment", cost=2.0, signal_quality=0.35, freshness_need=0.2, consumer_priority=0.15, never_shed=False, tags=["enrichment", "optional"]),
    ModuleSpec(
        "continuity_bridge",
        cost=0.5,
        signal_quality=1.0,
        freshness_need=1.0,
        consumer_priority=1.0,
        never_shed=True,
        tags=["critical", "handoff", "emergency"],
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_state() -> Dict[str, Any]:
    ensure_home()
    path = budget_state_path()
    if not path.is_file():
        return {
            "sticky_band": "ok",
            "sticky_level": "ok",
            "updated_ts": None,
            "decisions_lifetime": 0,
            "last_plan": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"sticky_band": "ok"}
    except (OSError, json.JSONDecodeError):
        return {"sticky_band": "ok", "sticky_level": "ok"}


def _save_state(state: Dict[str, Any]) -> None:
    ensure_home()
    budget_state_path().write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _append_event(event: Dict[str, Any]) -> None:
    ensure_home()
    with budget_events_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def module_catalog() -> List[Dict[str, Any]]:
    rows = []
    for m in DEFAULT_MODULES:
        d = asdict(m)
        d["score"] = m.score()
        rows.append(d)
    rows.sort(key=lambda r: (-float(r["score"]), r["name"]))
    return rows


def ranked_modules() -> List[ModuleSpec]:
    return sorted(DEFAULT_MODULES, key=lambda m: (-m.score(), m.name))


def frequency_multiplier(band: str, *, never_shed: bool) -> float:
    """Dynamic frequency scaling: critical path degrades slower."""
    if never_shed:
        return {"ok": 1.0, "caution": 1.0, "adaptive": 1.0, "emergency": 0.75}.get(band, 1.0)
    return {"ok": 1.0, "caution": 0.75, "adaptive": 0.5, "emergency": 0.0}.get(band, 1.0)


def source_preference(band: str) -> List[str]:
    """Preferential source order under budget pressure."""
    if band == "ok":
        return ["live", "cache", "reuse", "mock"]
    if band == "caution":
        return ["cache", "reuse", "live", "mock"]
    if band == "adaptive":
        return ["reuse", "cache", "mock", "live"]
    # emergency
    return ["reuse", "cache", "mock"]


def apply_hysteresis(
    instantaneous_level: str,
    sticky_level: str,
    ratio: float,
    cfg: AegisConfig,
) -> str:
    """
    Sticky band: can always escalate; demote only when ratio falls
    hysteresis below the sticky band's entry threshold.
    """
    hyst = float(getattr(cfg, "budget_recovery_hysteresis", 0.10) or 0.10)
    caution = float(getattr(cfg, "burn_caution_multiplier", 0.80) or 0.80)
    warn = float(getattr(cfg, "burn_warn_multiplier", 1.00) or 1.00)
    critical = float(getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25)

    entry = {"ok": 0.0, "caution": caution, "warn": warn, "critical": critical}
    inst_ord = LEVEL_ORDER.get(instantaneous_level, 0)
    stick_ord = LEVEL_ORDER.get(sticky_level, 0)

    if inst_ord > stick_ord:
        return instantaneous_level  # escalate immediately
    if inst_ord == stick_ord:
        return sticky_level
    # demote only if below sticky entry - hysteresis
    threshold = entry.get(sticky_level, 0.0) - hyst
    if ratio < threshold:
        return instantaneous_level
    return sticky_level


def project_usage(
    current_ratio: float,
    previous_ratio: float,
    elapsed_sec: float,
    horizon_sec: float,
) -> float:
    """
    Linear projection of usage ratio at horizon.
    Pure function — matches docs/personas/bandStateMachine.ts projectUsage.
    """
    if elapsed_sec <= 0:
        return float(current_ratio)
    rate = (float(current_ratio) - float(previous_ratio)) / float(elapsed_sec)
    return float(current_ratio) + rate * float(horizon_sec)


def level_from_effective_ratio(effective_ratio: float, cfg: AegisConfig) -> str:
    """Map a (possibly projected) ratio to a burn level — enter paths only."""
    return level_for_ratio(effective_ratio, cfg)


def instantaneous_with_projection(
    ratio: float,
    *,
    previous_ratio: Optional[float],
    previous_ts: Optional[str],
    cfg: AegisConfig,
    now_ts: Optional[str] = None,
) -> Tuple[str, Optional[float]]:
    """
    Compute instantaneous level using max(current, projected) for enter paths.
    Returns (level, projected_ratio|None).
    """
    if not getattr(cfg, "budget_use_projection", True):
        return level_for_ratio(ratio, cfg), None
    if previous_ratio is None or not previous_ts:
        return level_for_ratio(ratio, cfg), None

    try:
        prev_dt = datetime.fromisoformat(previous_ts.replace("Z", "+00:00"))
        now_dt = (
            datetime.fromisoformat((now_ts or _now()).replace("Z", "+00:00"))
            if now_ts or True
            else datetime.now(timezone.utc)
        )
        elapsed = max(0.0, (now_dt - prev_dt).total_seconds())
    except (ValueError, TypeError):
        return level_for_ratio(ratio, cfg), None

    # Default horizon: 60s (matches TS default); clamp to [1s, 1h]
    horizon = 60.0
    projected = project_usage(ratio, float(previous_ratio), elapsed, horizon)
    # never project negative
    projected = max(0.0, projected)
    effective = max(float(ratio), projected)
    return level_for_ratio(effective, cfg), round(projected, 4)


class BandEventBus:
    """
    Minimal in-memory event bus (sync, ordered, fail-soft).
    Fan-out adapters subscribe; persistence still goes to budget_aware_events.jsonl.
    """

    def __init__(self) -> None:
        self._handlers: List[Any] = []
        self._log: List[Dict[str, Any]] = []

    def subscribe(self, handler: Any) -> Any:
        self._handlers.append(handler)

        def _unsub() -> None:
            self._handlers = [h for h in self._handlers if h is not handler]

        return _unsub

    def publish(self, event: Dict[str, Any]) -> None:
        self._log.append(dict(event))
        # cap memory log
        if len(self._log) > 200:
            self._log = self._log[-200:]
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:  # noqa: BLE001
                pass

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(reversed(self._log[-max(1, limit) :]))


# Process-wide bus for adapters (CLI / tests / future UI bridges)
_GLOBAL_BUS = BandEventBus()


def get_event_bus() -> BandEventBus:
    return _GLOBAL_BUS


def plan_for_band(
    band: str,
    *,
    modules: Optional[Sequence[ModuleSpec]] = None,
) -> Dict[str, Any]:
    """Decide run / throttle / shed per module for a band."""
    mods = list(modules or ranked_modules())
    decisions: List[Dict[str, Any]] = []
    run: List[str] = []
    throttle: List[str] = []
    shed: List[str] = []
    stale_ok: List[str] = []

    for m in mods:
        mult = frequency_multiplier(band, never_shed=m.never_shed)
        action = "run"
        if m.never_shed:
            if mult < 1.0:
                action = "throttle"
                throttle.append(m.name)
            else:
                run.append(m.name)
        else:
            if mult <= 0.0 or (band == "emergency" and m.score() < 50):
                action = "shed"
                shed.append(m.name)
                stale_ok.append(m.name)
            elif mult < 1.0:
                action = "throttle"
                throttle.append(m.name)
            else:
                # caution: still run but prefer cheap sources — mark prefer
                if band == "caution" and m.cost >= 1.0:
                    action = "prefer_cheap"
                    throttle.append(m.name)
                else:
                    run.append(m.name)

        decisions.append(
            {
                "module": m.name,
                "action": action,
                "frequency": mult,
                "score": m.score(),
                "cost": m.cost,
                "never_shed": m.never_shed,
                "stale_ok": action == "shed",
                "tags": list(m.tags),
            }
        )

    return {
        "band": band,
        "run": run,
        "throttle": throttle,
        "shed": shed,
        "stale_ok": stale_ok,
        "source_preference": source_preference(band),
        "decisions": decisions,
        "summary": (
            f"Budget: {band} — "
            f"{len(run)} full, {len(throttle)} reduced, {len(shed)} shed"
        ),
    }


def should_run_module(plan: Dict[str, Any], name: str) -> bool:
    """False if shed (skip work; caller may serve stale)."""
    shed: Set[str] = set(plan.get("shed") or [])
    return name not in shed


def module_frequency(plan: Dict[str, Any], name: str) -> float:
    for d in plan.get("decisions") or []:
        if d.get("module") == name:
            return float(d.get("frequency") or 1.0)
    return 1.0


def evaluate(
    cfg: Optional[AegisConfig] = None,
    *,
    burn: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    force_band: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full budget-aware evaluation: sticky band + plan + audit event.

    dry_run: compute plan without persisting state/events.
    force_band: simulation override (ok|caution|adaptive|emergency).
    """
    cfg = cfg or load_config()
    enabled = bool(getattr(cfg, "budget_aware_mode", True))

    if burn is None:
        burn = burn_status(cfg, record_events=not dry_run)

    ratio = float(burn.get("ratio") or 0.0)
    base_level = str(burn.get("level") or "ok")
    projected_ratio: Optional[float] = None

    with _LOCK:
        state = _load_state()
        sticky = str(state.get("sticky_level") or "ok")
        prev_ratio = state.get("last_ratio")
        prev_ts = state.get("last_ratio_ts")

        # Rate-based projection (enter paths) + week-end forecast signal
        if force_band:
            band = force_band if force_band in BAND_FROM_LEVEL.values() else "ok"
            sticky_level = LEVEL_FROM_BAND.get(band, "ok")
            instant_level = sticky_level
        elif not enabled:
            sticky_level = "ok"
            band = "ok"
            instant_level = "ok"
        else:
            instant_level, projected_ratio = instantaneous_with_projection(
                ratio,
                previous_ratio=float(prev_ratio) if prev_ratio is not None else None,
                previous_ts=str(prev_ts) if prev_ts else None,
                cfg=cfg,
            )
            # Also honor week-end forecast hard signals
            if getattr(cfg, "budget_use_projection", True):
                try:
                    from aegis.forecast import predict_budget

                    fc = predict_budget(cfg)
                    proj_sig = str(fc.get("projected_signal") or "ok")
                    if proj_sig == "hard_stop" and LEVEL_ORDER.get(instant_level, 0) < 3:
                        instant_level = "critical"
                    elif proj_sig == "throttle" and LEVEL_ORDER.get(instant_level, 0) < 2:
                        instant_level = "warn"
                except Exception:  # noqa: BLE001
                    pass
            # fall back to burn level if projection yielded lower (shouldn't)
            if LEVEL_ORDER.get(base_level, 0) > LEVEL_ORDER.get(instant_level, 0):
                instant_level = base_level

            sticky_level = apply_hysteresis(instant_level, sticky, ratio, cfg)
            band = BAND_FROM_LEVEL.get(sticky_level, "ok")

        plan = plan_for_band(band)
        transition = None
        if sticky_level != sticky and not dry_run and enabled:
            transition = {
                "ts": _now(),
                "kind": "band_change",
                "from_level": sticky,
                "to_level": sticky_level,
                "from_band": BAND_FROM_LEVEL.get(sticky, "ok"),
                "to_band": band,
                "ratio": ratio,
                "projected_ratio": projected_ratio,
                "plan_summary": plan["summary"],
                "reason": (
                    f"Threshold crossed (current or projected). "
                    f"projected={projected_ratio}"
                    if projected_ratio is not None
                    else "Threshold crossed under config"
                ),
            }
            _append_event(transition)
            try:
                _GLOBAL_BUS.publish(transition)
            except Exception:  # noqa: BLE001
                pass

        if not dry_run and enabled:
            state["sticky_band"] = band
            state["sticky_level"] = sticky_level
            state["updated_ts"] = _now()
            state["last_ratio"] = ratio
            state["last_ratio_ts"] = _now()
            state["last_projected_ratio"] = projected_ratio
            state["last_plan"] = {
                "band": band,
                "run": plan["run"],
                "throttle": plan["throttle"],
                "shed": plan["shed"],
                "summary": plan["summary"],
            }
            state["decisions_lifetime"] = int(state.get("decisions_lifetime") or 0) + 1
            if transition:
                state["last_transition"] = transition
            _save_state(state)

    # workers soft-cap still via burn helpers
    from aegis.burn import budget_aware_workers

    workers = budget_aware_workers(cfg=cfg, level=sticky_level if enabled else "ok")

    return {
        "ok": True,
        "enabled": enabled,
        "dry_run": dry_run,
        "ts": _now(),
        "band": band,
        "level": sticky_level if enabled else "ok",
        "instant_level": instant_level,
        "ratio": ratio,
        "ratio_pct": round(ratio * 100.0, 1),
        "projected_ratio": projected_ratio,
        "hysteresis": float(getattr(cfg, "budget_recovery_hysteresis", 0.10) or 0.10),
        "plan": plan,
        "modules_reduced": len(plan.get("throttle") or []) + len(plan.get("shed") or []),
        "modules_shed": plan.get("shed") or [],
        "modules_throttled": plan.get("throttle") or [],
        "source_preference": plan.get("source_preference"),
        "recommended_workers": workers,
        "menu_summary": (
            f"Budget: {band.capitalize()}"
            + (
                f" – {len(plan.get('shed') or [])} shed, "
                f"{len(plan.get('throttle') or [])} reduced"
                if (plan.get("shed") or plan.get("throttle"))
                else " – full capacity"
            )
        ),
        "transition": transition,
        "burn": {
            "avg_daily_burn": burn.get("avg_daily_burn"),
            "safe_daily": burn.get("safe_daily"),
            "message": burn.get("message"),
        },
        "catalog": module_catalog()[:8],
        "state": {
            "sticky_band": band,
            "sticky_level": sticky_level if enabled else "ok",
            "updated_ts": _now() if not dry_run else state.get("updated_ts"),
        },
    }


def simulate(band: str = "adaptive") -> Dict[str, Any]:
    """Dry-run: what would happen if we entered this band now."""
    return evaluate(dry_run=True, force_band=band)


def recent_budget_events(limit: int = 20) -> List[Dict[str, Any]]:
    path = budget_events_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return list(reversed(rows[-max(1, limit) :]))


def tick_gate(cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    """
    Called at start of intelligence.tick().
    Returns evaluate() plan used to skip/throttle steps.
    """
    return evaluate(cfg, dry_run=False)
