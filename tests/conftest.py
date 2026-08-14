import pytest
from aegis import guard

@pytest.fixture(autouse=True)
def reset_active_guard():
    """Reset the global _ACTIVE_GUARD before and after every test."""
    guard._ACTIVE_GUARD = None
    yield
    guard._ACTIVE_GUARD = None
