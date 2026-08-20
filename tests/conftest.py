import pytest
from aegis import guard
from aegis.guard import GUARD_LOG_PATH as _PROD_GUARD_LOG_PATH

@pytest.fixture(autouse=True, scope="session")
def isolate_guard_log(tmp_path_factory):
    """Keep test guard events out of the production ~/.aegis/guard_log.jsonl.

    Session default only: function-scoped monkeypatch.setattr on
    aegis.guard.GUARD_LOG_PATH still overrides per test.
    """
    guard.GUARD_LOG_PATH = tmp_path_factory.mktemp("guard") / "guard_log.jsonl"
    yield guard.GUARD_LOG_PATH
    guard.GUARD_LOG_PATH = _PROD_GUARD_LOG_PATH

@pytest.fixture(autouse=True)
def reset_active_guard():
    """Reset the global _ACTIVE_GUARD before and after every test."""
    guard._ACTIVE_GUARD = None
    yield
    guard._ACTIVE_GUARD = None
