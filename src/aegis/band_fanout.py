"""
Minimal fan-out adapter for BudgetDecisionEvents / band transitions.

Consumes the in-memory BandEventBus and (optionally) mirrors events to:
  - in-memory ring log (queryable)
  - stderr console (debug)
  - durable budget_aware_events.jsonl is already written by budget_aware.evaluate

Surfaces (menu bar / dashboard / weekly report) read live evaluate() state;
this adapter is for tests, CLI hooks, and future push subscribers.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

from aegis.budget_aware import BandEventBus, get_event_bus

_LOCK = threading.Lock()
_LOG: List[Dict[str, Any]] = []
_MAX = 100
_unsub: Optional[Callable[[], None]] = None
_console = False


def _on_event(event: Dict[str, Any]) -> None:
    with _LOCK:
        _LOG.append(dict(event))
        if len(_LOG) > _MAX:
            del _LOG[: len(_LOG) - _MAX]
    if _console:
        try:
            prev = event.get("from_band") or event.get("previousBand")
            cur = event.get("to_band") or event.get("currentBand")
            ratio = event.get("ratio") or event.get("usageRatio")
            print(
                f"[BAND] {prev} → {cur} ratio={ratio} "
                f"proj={event.get('projected_ratio') or event.get('projectedEndOfWindow')}",
                file=sys.stderr,
            )
        except Exception:  # noqa: BLE001
            pass


def attach_fanout(*, console: bool = False, bus: Optional[BandEventBus] = None) -> None:
    """Subscribe adapter once to the process bus."""
    global _unsub, _console
    _console = console
    b = bus or get_event_bus()
    if _unsub is not None:
        return
    _unsub = b.subscribe(_on_event)


def detach_fanout() -> None:
    global _unsub
    if _unsub is not None:
        try:
            _unsub()
        except Exception:  # noqa: BLE001
            pass
        _unsub = None


def fanout_log(limit: int = 20) -> List[Dict[str, Any]]:
    with _LOCK:
        return list(reversed(_LOG[-max(1, limit) :]))


def fanout_clear() -> None:
    with _LOCK:
        _LOG.clear()


def format_menu_line(event: Dict[str, Any]) -> str:
    """Same-message-everywhere short line for UI."""
    band = event.get("to_band") or event.get("currentBand") or "?"
    ratio = event.get("ratio") or event.get("usageRatio")
    try:
        pct = f"{float(ratio) * 100:.0f}%"
    except (TypeError, ValueError):
        pct = "?"
    return f"Budget: {str(band).capitalize()} · {pct} of safe"
