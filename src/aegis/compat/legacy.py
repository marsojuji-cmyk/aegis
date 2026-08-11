"""Load gen-1 engines from the scratch pipeline without mutating them."""

from __future__ import annotations

import importlib.util
import os
import sys
from types import ModuleType
from typing import Any, Dict, Optional, Tuple

from aegis import DEFAULT_ENGINE, LEGACY_PIPELINE

_LEGACY_CACHE: Optional[Dict[str, Any]] = None


def get_engine_name() -> str:
    return os.environ.get("AEGIS_ENGINE", DEFAULT_ENGINE).strip().lower() or DEFAULT_ENGINE


def legacy_pipeline_path() -> str:
    return os.environ.get("AEGIS_LEGACY_PATH", LEGACY_PIPELINE)


def legacy_available() -> bool:
    root = legacy_pipeline_path()
    return os.path.isfile(os.path.join(root, "token_supply_chain.py")) and os.path.isfile(
        os.path.join(root, "token_ledger.py")
    )


def _load_module(name: str, path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    # Unique name avoids clobbering if both product and legacy define same symbols later
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_legacy_modules() -> Dict[str, Any]:
    """Return TokenSupplyChainInspector, JITContextAssembler, TokenLedger classes."""
    global _LEGACY_CACHE
    if _LEGACY_CACHE is not None:
        return _LEGACY_CACHE

    root = legacy_pipeline_path()
    if not legacy_available():
        raise FileNotFoundError(
            f"Legacy pipeline not found at {root}. Set AEGIS_LEGACY_PATH or restore scratch."
        )

    tsc = _load_module(
        "aegis_legacy_token_supply_chain",
        os.path.join(root, "token_supply_chain.py"),
    )
    tl = _load_module(
        "aegis_legacy_token_ledger",
        os.path.join(root, "token_ledger.py"),
    )

    _LEGACY_CACHE = {
        "TokenSupplyChainInspector": tsc.TokenSupplyChainInspector,
        "JITContextAssembler": tsc.JITContextAssembler,
        "TokenLedger": tl.TokenLedger,
        "root": root,
    }
    return _LEGACY_CACHE


def expense_report_path() -> str:
    return os.path.join(legacy_pipeline_path(), "expense_report_output.json")


def load_expense_report() -> Optional[Dict[str, Any]]:
    import json

    path = expense_report_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def skill_path() -> str:
    return os.path.expanduser("~/.agents/skills/aegis-tokenomics/SKILL.md")


def rules_path() -> str:
    return os.path.expanduser("~/.agents/rules/aegis_tokenomics.md")
