"""Aegis policy config (TOML-ish simple parser, no extra deps)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from aegis.paths import config_path, ensure_home


@dataclass
class AegisConfig:
    weekly_token_cap: int = 1_000_000
    reserve_floor: float = 0.80
    reinvest_rate: float = 0.20
    cost_per_1k_input: float = 0.00125
    cost_per_1k_output: float = 0.005
    default_pack_mode: str = "explore"
    output_default_profile: str = "brief"
    output_default_max: int = 800
    # Enforced before dispatch; profile instructions alone cannot cap a model.
    output_hard_max: int = 800
    context_window_tokens: int = 258_000
    context_checkpoint_percent: float = 60.0
    context_transfer_percent: float = 85.0
    openai_use_responses: bool = True
    openai_service_tier: str = "auto"
    throttle_floor: float = 0.50  # below this remaining % → hard_stop
    # Intelligence Layer — autonomous compound economy
    # Background loops create ledger noise and prompt growth unless their yield
    # is measured. Operators may enable them explicitly after a benchmark.
    auto_tick: bool = False
    # Autonomous mutation is opt-in. Observation must never create work.
    auto_invest: bool = False
    auto_apply_fixes: bool = False
    auto_memory: bool = False
    intel_tick_seconds: int = 300
    min_roi_grade_auto: str = "B"  # only auto-invest A/B ideas
    forecast_horizon_days: int = 7
    # Forecast advice thresholds (no magic numbers in forecast._advice)
    cache_hit_threshold: float = 30.0  # % — warn below this
    # Progressive burn bands: ratio = avg_daily_burn / safe_daily
    burn_caution_multiplier: float = 0.80  # subtle indicator
    burn_warn_multiplier: float = 1.00  # at/over safe allowance
    burn_warning_multiplier: float = 1.25  # critical — ≥25% over safe
    budget_aware_mode: bool = True  # proactive control loop (shed/throttle)
    # Hysteresis: only exit a stickier band after ratio falls this far below entry
    budget_recovery_hysteresis: float = 0.10
    # Projected burn: enter adaptive early if projected EOD ratio exceeds warn
    budget_use_projection: bool = True
    # Continuity Bridge — privileged handoff near hard stop / emergency band
    continuity_bridge_enabled: bool = True
    continuity_default_enabled: bool = True
    continuity_auto_on_emergency: bool = True
    continuity_include_embeddings: bool = True  # canonical texts + hash; vectors optional
    membership_guard_enabled: bool = True
    membership_shadow_weekly_tokens: int = 0
    membership_reserve_percent: float = 0.20
    # Middleware Guard (AEGIS Pillars)
    guard_max_tool_calls: int = 20
    guard_max_velocity_calls_per_min: int = 5
    guard_max_output_length: int = 4000
    guard_allowed_domains: str = ""  # comma-separated string for TOML
    guard_min_signal_score: float = 0.5
    guard_trim_strategy: str = "truncate"
    guard_signal_preserve_keywords: str = ""
    guard_audit_limit: int = 50
    guard_shadow_mode: bool = True
    guard_signal_shadow_mode: bool = True
    # v1 Hermes notes pin. Empty = unset. Never fall through to DEFAULT_ROOT.
    hermes_notes_root: str = ""

    def __post_init__(self) -> None:
        checkpoint = self.context_checkpoint_percent
        transfer = self.context_transfer_percent
        numeric = (int, float)
        if (
            isinstance(checkpoint, bool)
            or isinstance(transfer, bool)
            or not isinstance(checkpoint, numeric)
            or not isinstance(transfer, numeric)
            or not 0 < checkpoint < transfer <= 100
        ):
            raise ValueError(
                "context thresholds must satisfy "
                "0 < context_checkpoint_percent < context_transfer_percent <= 100"
            )


DEFAULTS = AegisConfig()


def opt_in(cfg: Any, name: str) -> bool:
    """Autonomy flags fail closed. Missing attribute means off."""
    return bool(getattr(cfg, name, False))


def _parse_simple_toml(text: str) -> Dict[str, Any]:
    """Minimal key = value parser (no tables). Values: int/float/str/bool."""
    out: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            out[key] = val[1:-1]
        elif val.lower() in ("true", "false"):
            out[key] = val.lower() == "true"
        elif "." in val:
            try:
                out[key] = float(val)
            except ValueError:
                out[key] = val
        else:
            try:
                out[key] = int(val)
            except ValueError:
                out[key] = val
    return out


def _format_toml(cfg: AegisConfig) -> str:
    lines = [
        "# Aegis policy — piggy bank + 3R + surplus reinvest",
        f"weekly_token_cap = {cfg.weekly_token_cap}",
        f"reserve_floor = {cfg.reserve_floor}",
        f"reinvest_rate = {cfg.reinvest_rate}",
        f"cost_per_1k_input = {cfg.cost_per_1k_input}",
        f"cost_per_1k_output = {cfg.cost_per_1k_output}",
        f'default_pack_mode = "{cfg.default_pack_mode}"',
        f'output_default_profile = "{cfg.output_default_profile}"',
        f"output_default_max = {cfg.output_default_max}",
        f"output_hard_max = {cfg.output_hard_max}",
        f"context_window_tokens = {cfg.context_window_tokens}",
        f"context_checkpoint_percent = {cfg.context_checkpoint_percent}",
        f"context_transfer_percent = {cfg.context_transfer_percent}",
        f"openai_use_responses = {str(cfg.openai_use_responses).lower()}",
        f'openai_service_tier = "{cfg.openai_service_tier}"',
        f"throttle_floor = {cfg.throttle_floor}",
        f"auto_tick = {str(cfg.auto_tick).lower()}",
        f"auto_invest = {str(cfg.auto_invest).lower()}",
        f"auto_apply_fixes = {str(cfg.auto_apply_fixes).lower()}",
        f"auto_memory = {str(cfg.auto_memory).lower()}",
        f"intel_tick_seconds = {cfg.intel_tick_seconds}",
        f'min_roi_grade_auto = "{cfg.min_roi_grade_auto}"',
        f"forecast_horizon_days = {cfg.forecast_horizon_days}",
        f"cache_hit_threshold = {cfg.cache_hit_threshold}",
        f"burn_caution_multiplier = {cfg.burn_caution_multiplier}",
        f"burn_warn_multiplier = {cfg.burn_warn_multiplier}",
        f"burn_warning_multiplier = {cfg.burn_warning_multiplier}",
        f"budget_aware_mode = {str(cfg.budget_aware_mode).lower()}",
        f"budget_recovery_hysteresis = {cfg.budget_recovery_hysteresis}",
        f"budget_use_projection = {str(cfg.budget_use_projection).lower()}",
        f"continuity_bridge_enabled = {str(cfg.continuity_bridge_enabled).lower()}",
        f"continuity_default_enabled = {str(cfg.continuity_default_enabled).lower()}",
        f"continuity_auto_on_emergency = {str(cfg.continuity_auto_on_emergency).lower()}",
        f"continuity_include_embeddings = {str(cfg.continuity_include_embeddings).lower()}",
        f"membership_guard_enabled = {str(cfg.membership_guard_enabled).lower()}",
        f"membership_shadow_weekly_tokens = {cfg.membership_shadow_weekly_tokens}",
        f"membership_reserve_percent = {cfg.membership_reserve_percent}",
        f"guard_max_tool_calls = {cfg.guard_max_tool_calls}",
        f"guard_max_velocity_calls_per_min = {cfg.guard_max_velocity_calls_per_min}",
        f"guard_max_output_length = {cfg.guard_max_output_length}",
        f'guard_allowed_domains = "{cfg.guard_allowed_domains}"',
        f"guard_min_signal_score = {cfg.guard_min_signal_score}",
        f'guard_trim_strategy = "{cfg.guard_trim_strategy}"',
        f'guard_signal_preserve_keywords = "{cfg.guard_signal_preserve_keywords}"',
        f"guard_audit_limit = {cfg.guard_audit_limit}",
        f"guard_shadow_mode = {str(cfg.guard_shadow_mode).lower()}",
        f'hermes_notes_root = "{cfg.hermes_notes_root}"',
        "",
    ]
    return "\n".join(lines)


def resolve_hermes_notes_root(cfg: Optional[AegisConfig] = None) -> str:
    """Env overrides config. Unset is empty — not DEFAULT_ROOT. Does not write config."""
    env = (os.environ.get("AEGIS_HERMES_NOTES_ROOT") or "").strip()
    if env:
        return env
    if cfg is not None:
        return str(cfg.hermes_notes_root or "").strip()
    path = config_path()
    if not path.is_file():
        return ""
    try:
        data = _parse_simple_toml(path.read_text(encoding="utf-8"))
    except OSError:
        return ""
    return str(data.get("hermes_notes_root") or "").strip()


def load_config() -> AegisConfig:
    ensure_home()
    path = config_path()
    if not path.is_file():
        save_config(DEFAULTS)
        return AegisConfig(**asdict(DEFAULTS))

    data = _parse_simple_toml(path.read_text(encoding="utf-8"))
    base = asdict(DEFAULTS)
    for k, v in data.items():
        if k in base:
            # coerce types from defaults
            t = type(base[k])
            try:
                base[k] = t(v) if t is not bool else bool(v)
            except (TypeError, ValueError):
                base[k] = v
    return AegisConfig(**base)


def save_config(cfg: AegisConfig) -> Path:
    ensure_home()
    path = config_path()
    path.write_text(_format_toml(cfg), encoding="utf-8")
    return path
