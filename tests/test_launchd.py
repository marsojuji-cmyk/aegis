"""launchd plist build + install helpers (no live bootstrap required for unit bits)."""

import plistlib
import sys

import pytest

from aegis.launchd import (
    LABEL,
    build_plist,
    is_installed,
    launchd_status,
    plist_path,
    write_plist,
)


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_build_plist_shape(aegis_tmp):
    pl = build_plist("127.0.0.1", 8787)
    assert pl["Label"] == LABEL
    assert pl["RunAtLoad"] is True
    assert pl["KeepAlive"] is True
    args = pl["ProgramArguments"]
    assert "-m" in args
    assert "aegis" in args
    assert "serve" in args
    assert "--foreground" in args
    assert "--port" in args
    assert "8787" in args
    assert pl["EnvironmentVariables"]["AEGIS_MANAGED_BY"] == "launchd"
    assert "PYTHONPATH" in pl["EnvironmentVariables"]


def test_write_plist_roundtrip(aegis_tmp, tmp_path, monkeypatch):
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    monkeypatch.setattr("aegis.launchd.launch_agents_dir", lambda: agents)
    path = write_plist("127.0.0.1", 9999)
    assert path.is_file()
    with path.open("rb") as f:
        pl = plistlib.load(f)
    assert pl["Label"] == LABEL
    assert "9999" in pl["ProgramArguments"]
    assert is_installed()
    st = launchd_status()
    assert st["installed"] is True
    assert st["label"] == LABEL


def test_cli_install_login_help():
    from aegis.cli import main

    # status still works when not installed
    code = main(["daemon", "status", "--json"])
    assert code in (0, 1)


@pytest.mark.skipif(sys.platform != "darwin", reason="launchd is macOS-only")
def test_launchd_status_fields(aegis_tmp):
    st = launchd_status()
    assert st["platform"] == "darwin"
    assert st["label"] == LABEL
    assert "plist" in st
