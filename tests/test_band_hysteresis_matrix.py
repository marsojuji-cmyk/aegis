"""
Band boundary matrix — Continuity Architect v1.1.0 quality gate.

Drives usage ratios across every enter/exit edge with hysteresis.
Product bands: ok / caution / adaptive(warn) / emergency(critical).
"""

import pytest

from aegis.budget_aware import apply_hysteresis
from aegis.burn import level_for_ratio
from aegis.config import AegisConfig


@pytest.fixture()
def cfg():
    return AegisConfig(
        burn_caution_multiplier=0.80,
        burn_warn_multiplier=1.00,
        burn_warning_multiplier=1.25,
        budget_recovery_hysteresis=0.10,
    )


def test_instantaneous_levels(cfg):
    cases = [
        (0.0, "ok"),
        (0.79, "ok"),
        (0.80, "caution"),
        (0.99, "caution"),
        (1.00, "warn"),
        (1.24, "warn"),
        (1.25, "critical"),
        (2.0, "critical"),
    ]
    for ratio, expect in cases:
        assert level_for_ratio(ratio, cfg) == expect, (ratio, expect)


def test_escalate_immediately(cfg):
    assert apply_hysteresis("critical", "ok", 1.5, cfg) == "critical"
    assert apply_hysteresis("warn", "caution", 1.1, cfg) == "warn"
    assert apply_hysteresis("caution", "ok", 0.85, cfg) == "caution"


def test_hysteresis_holds_near_boundary(cfg):
    # sticky warn (entry 1.0); ratio 0.95 is above 1.0 - 0.10 = 0.90 → hold warn
    assert apply_hysteresis("caution", "warn", 0.95, cfg) == "warn"
    # sticky critical; ratio 1.20 above 1.25 - 0.10 = 1.15 → hold critical
    assert apply_hysteresis("warn", "critical", 1.20, cfg) == "critical"
    # sticky caution; ratio 0.75 above 0.80 - 0.10 = 0.70 → hold caution
    assert apply_hysteresis("ok", "caution", 0.75, cfg) == "caution"


def test_hysteresis_demotes_when_clear(cfg):
    # below warn exit 0.90
    assert apply_hysteresis("caution", "warn", 0.85, cfg) == "caution"
    # below caution exit 0.70
    assert apply_hysteresis("ok", "caution", 0.65, cfg) == "ok"
    # below critical exit 1.15 → demote to instantaneous
    assert apply_hysteresis("warn", "critical", 1.10, cfg) == "warn"
    assert apply_hysteresis("ok", "critical", 0.5, cfg) == "ok"


def test_full_climb_and_descent(cfg):
    sticky = "ok"
    path = []
    for ratio in [0.5, 0.85, 1.05, 1.3, 1.2, 0.95, 0.85, 0.6]:
        instant = level_for_ratio(ratio, cfg)
        sticky = apply_hysteresis(instant, sticky, ratio, cfg)
        path.append((ratio, instant, sticky))
    # climb
    assert path[0][2] == "ok"
    assert path[1][2] == "caution"
    assert path[2][2] == "warn"
    assert path[3][2] == "critical"
    # 1.2 still sticky critical
    assert path[4][2] == "critical"
    # 0.95 < 1.15 exit → demote to instantaneous caution
    assert path[5][2] == "caution"
    assert path[-1][2] == "ok"
