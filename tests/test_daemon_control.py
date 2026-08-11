"""Background daemon start/stop/status."""

import time

import pytest

from aegis.cli import main
from aegis.daemon_control import daemon_status, start_daemon, stop_daemon


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_start_stop_status(aegis_tmp):
    # use high port to avoid collisions
    port = 18799
    stop_daemon()  # clean
    st0 = daemon_status()
    assert st0["running"] is False

    res = start_daemon("127.0.0.1", port)
    assert res.get("ok") is True
    assert res.get("pid")
    # poll until healthy
    ok = False
    for _ in range(30):
        st = daemon_status()
        if st.get("running"):
            ok = True
            break
        time.sleep(0.1)
    assert ok, f"daemon not healthy: {daemon_status()}"

    stop = stop_daemon()
    assert stop.get("ok") is True
    time.sleep(0.2)
    st2 = daemon_status()
    assert st2["running"] is False


def test_cli_daemon_status_when_stopped(aegis_tmp):
    stop_daemon()
    # exit 1 when not running is ok
    code = main(["daemon", "status", "--json"])
    assert code in (0, 1)
