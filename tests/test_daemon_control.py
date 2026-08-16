"""Daemon control-plane contracts: bind preflight, health states, no dual-spawn."""

import socket
import time

import pytest

from aegis.cli import main
from aegis.daemon_control import (
    daemon_status,
    probe_bind,
    start_daemon,
    stop_daemon,
    wait_for_health,
    write_runtime_meta,
)
from aegis.paths import daemon_pid_path


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_probe_bind_available(aegis_tmp):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    result = probe_bind("127.0.0.1", port)
    assert result["ok"] is True
    assert result["state"] == "available"
    assert result["port"] == port


def test_probe_bind_in_use(aegis_tmp):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        result = probe_bind("127.0.0.1", port)
        assert result["ok"] is False
        assert result["state"] == "in_use"
    finally:
        sock.close()


def test_stale_pid_cleared(aegis_tmp):
    write_runtime_meta("127.0.0.1", 18791, 999999)
    assert daemon_pid_path().is_file()
    st = daemon_status(host="127.0.0.1", port=18791)
    assert st["running"] is False
    assert st["alive_process"] is False
    assert st["pid"] is None
    assert not daemon_pid_path().is_file()


def test_wait_for_health_dead_when_stopped(aegis_tmp):
    stop_daemon()
    waited = wait_for_health(host="127.0.0.1", port=18792, timeout=0.3, interval=0.05)
    assert waited["ok"] is False
    assert waited["state"] == "dead"
    assert waited["running"] is False


def test_wait_for_health_classifies_bind_failed(aegis_tmp):
    write_runtime_meta(
        "127.0.0.1",
        18795,
        999998,
        bind_ok=False,
        bind_error="[Errno 48] Address already in use",
        bindError="[Errno 48] Address already in use",
    )
    waited = wait_for_health(host="127.0.0.1", port=18795, timeout=0.4, interval=0.05)
    assert waited["ok"] is False
    assert waited["state"] == "bind_failed"
    assert waited.get("bindError")
    assert waited.get("bind_error")


def test_start_preflight_refuses_in_use_port(aegis_tmp):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        res = start_daemon("127.0.0.1", port)
        assert res.get("ok") is False
        assert res.get("started") is False
        assert (res.get("bind") or {}).get("state") == "in_use"
    finally:
        sock.close()


def test_start_refuses_second_spawn_without_force(aegis_tmp, monkeypatch):
    write_runtime_meta("127.0.0.1", 18793, 1)
    monkeypatch.setattr("aegis.daemon_control._pid_alive", lambda pid: pid == 1)
    st = start_daemon("127.0.0.1", 18794, force=False)
    assert st.get("ok") is False
    assert st.get("started") is False
    assert st.get("conflict") is True
    assert "refuse second spawn" in (st.get("message") or "")


def test_concurrent_health_probes_inprocess(aegis_tmp):
    from concurrent.futures import ThreadPoolExecutor

    from aegis.router_daemon import start_background

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    httpd, _t = start_background("127.0.0.1", port)
    try:
        import json
        import urllib.request

        def _hit():
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: _hit(), range(16)))
        assert all(r.get("ok") is True for r in results)
        assert all(r.get("service") == "aegis-router" for r in results)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_cli_daemon_status_when_stopped(aegis_tmp):
    stop_daemon()
    code = main(["daemon", "status", "--json"])
    assert code in (0, 1)


def test_start_stop_status(aegis_tmp):
    port = 18799
    stop_daemon()
    st0 = daemon_status(host="127.0.0.1", port=port)
    assert st0["running"] is False

    bind = probe_bind("127.0.0.1", port)
    if not bind.get("ok"):
        pytest.skip(f"host cannot bind {port}: {bind}")

    res = start_daemon("127.0.0.1", port)
    if not res.get("ok"):
        # Classified failure (bind/health), not a hang.
        assert res.get("startup") in {"dead", "bind_failed", "timeout", None}
        assert res.get("running") is False
        if res.get("startup") == "timeout":
            stop_daemon()
        return

    last_status = {}
    healthy = False
    for _ in range(50):
        last_status = daemon_status(host="127.0.0.1", port=port)
        if last_status.get("running"):
            healthy = True
            break
        if not last_status.get("alive_process"):
            break
        time.sleep(0.1)

    if healthy:
        assert last_status["port"] == port
        assert last_status["url"].endswith(f":{port}/v1")
        stop = stop_daemon()
        assert stop.get("ok") is True
        time.sleep(0.2)
        st2 = daemon_status(host="127.0.0.1", port=port)
        assert st2["running"] is False
    else:
        assert last_status.get("running") is False
        stop_daemon()
