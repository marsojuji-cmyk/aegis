"""Hermes plugin glue. Policy lives in aegis.wrappers.hermes_wrapper.

Hermes launches with PYTHONPATH unset (its own venv). Insert the Aegis
src tree before importing the gate so register() can load.
"""

from __future__ import annotations

import sys
from pathlib import Path

_AEGIS_SRC = Path(__file__).resolve().parents[2] / "src"
if _AEGIS_SRC.is_dir() and str(_AEGIS_SRC) not in sys.path:
    sys.path.insert(0, str(_AEGIS_SRC))

from aegis.wrappers.hermes_wrapper import (  # noqa: E402
    hermes_tool_execution,
    hermes_tool_request,
    register,
)

__all__ = ["register", "hermes_tool_execution", "hermes_tool_request"]
