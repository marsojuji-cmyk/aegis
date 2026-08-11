"""Legacy engine shims (E0 strangler)."""

from aegis.compat.legacy import (
    get_engine_name,
    load_legacy_modules,
    legacy_available,
)

__all__ = [
    "get_engine_name",
    "load_legacy_modules",
    "legacy_available",
]
