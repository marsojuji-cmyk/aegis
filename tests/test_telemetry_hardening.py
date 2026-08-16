import os
import sys
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch
from aegis.router_pipeline import resolve_environment, AegisConfigurationError
from aegis.router_pipeline import run_pipeline

def test_resolve_environment_pytest_fallback():
    # Outside pytest it fails, but since this IS pytest, if AEGIS_ENV is absent, it should return 'test'
    with patch.dict(os.environ, clear=True):
        assert resolve_environment() == "test"

def test_resolve_environment_explicit_invalid():
    with patch.dict(os.environ, {"AEGIS_ENV": "production_fake"}):
        with pytest.raises(AegisConfigurationError, match="Unsupported AEGIS_ENV: production_fake"):
            resolve_environment()

def test_resolve_environment_explicit_valid():
    with patch.dict(os.environ, {"AEGIS_ENV": "staging"}):
        assert resolve_environment() == "staging"

def test_resolve_environment_missing_outside_pytest():
    with patch.dict(os.environ, clear=True):
        with patch.dict(sys.modules, clear=True):  # remove pytest from modules
            with pytest.raises(AegisConfigurationError, match="AEGIS_ENV must be explicitly set outside pytest"):
                resolve_environment()

def test_pipeline_fails_closed_invalid_env():
    # run_pipeline should return an error if AEGIS_ENV is invalid
    with patch.dict(os.environ, {"AEGIS_ENV": "invalid_env"}):
        res = run_pipeline(task="foo", model="mock", paths=[], prompt="hello")
        assert not res.ok
        assert "Unsupported AEGIS_ENV: invalid_env" in res.error

def test_pipeline_preserves_explicit_run_id():
    custom_id = str(uuid.uuid4())
    with patch.dict(os.environ, {"AEGIS_ENV": "test", "AEGIS_RUN_ID": custom_id}):
        # Mock the AegisGuardContext to inspect it
        with patch('aegis.router_pipeline.AegisGuardContext') as mock_ctx:
            mock_ctx.return_value = None
            try:
                run_pipeline(task="foo", model="mock", paths=[], prompt="hello")
            except Exception:
                pass
            args, kwargs = mock_ctx.call_args
            assert kwargs["run_id"] == custom_id

def test_pipeline_generates_stable_run_id():
    with patch.dict(os.environ, {"AEGIS_ENV": "test"}):
        if "AEGIS_RUN_ID" in os.environ:
            del os.environ["AEGIS_RUN_ID"]
            
        with patch('aegis.router_pipeline.AegisGuardContext') as mock_ctx:
            mock_ctx.return_value = None
            try:
                run_pipeline(task="foo", model="mock", paths=[], prompt="hello")
            except Exception:
                pass
            args1, kwargs1 = mock_ctx.call_args
            run1 = kwargs1["run_id"]
            
            try:
                run_pipeline(task="foo2", model="mock", paths=[], prompt="hello2")
            except Exception:
                pass
            args2, kwargs2 = mock_ctx.call_args
            run2 = kwargs2["run_id"]
            
            assert run1 == run2
            assert run1 != "default-run"
            assert len(run1) > 8
