"""
Background control for the Aegis router daemon.

  aegis serve --background
  aegis daemon start|stop|status|restart

PID/log/meta live under ~/.aegis/
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aegis import __version__
from aegis.paths import (
    daemon_log_path,
    daemon_meta_path,
    daemon_pid_path,
    ensure_home,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_pid() -> Optional[int]:
    path = daemon_pid_path()
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        return pid
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_runtime_meta(host: str, port: int, pid: int, **extra: Any) -> None:
    """Register live process (called by serve --foreground and start_daemon)."""
    ensure_home()
    meta: Dict[str, Any] = {
        "pid": pid,
        "host": host,
        "port": port,
        "version": __version__,
        "started_ts": _now(),
        "url": f"http://{host}:{port}/v1",
        "log": str(daemon_log_path()),
        "managed_by": os.environ.get("AEGIS_MANAGED_BY") or "process",
    }
    meta.update(extra)
    daemon_meta_path().write_text(json.dumps(meta, indent=2), encoding="utf-8")
    daemon_pid_path().write_text(str(pid) + "\n", encoding="utf-8")


# Back-compat alias
_write_meta = write_runtime_meta


def _clear_meta() -> None:
    for p in (daemon_pid_path(), daemon_meta_path()):
        try:
            p.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            # py3.9 may not have missing_ok on older? 3.8+ has it on Path.unlink in 3.8+
            if p.is_file():
                p.unlink()
        except OSError:
            pass


def clear_meta_if_pid(pid: int) -> None:
    """Clear pid/meta only if they still point at this process."""
    current = _read_pid()
    if current is None or current == pid:
        _clear_meta()


def load_meta() -> Dict[str, Any]:
    path = daemon_meta_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def daemon_status() -> Dict[str, Any]:
    """Return running state + health probe."""
    pid = _read_pid()
    meta = load_meta()
    host = meta.get("host") or "127.0.0.1"
    port = int(meta.get("port") or 8787)
    alive = bool(pid and _pid_alive(pid))
    if pid and not alive:
        # stale pid file
        _clear_meta()
        pid = None
        alive = False
    health: Dict[str, Any] = {"reachable": False}
    if alive:
        try:
            url = f"http://{host}:{port}/healthz"
            with urllib.request.urlopen(url, timeout=2) as resp:
                health = json.loads(resp.read().decode("utf-8"))
                health["reachable"] = True
                health["http_status"] = resp.status
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            health = {"reachable": False, "error": str(exc)}
    return {
        "running": alive and health.get("reachable", False),
        "pid": pid,
        "alive_process": alive,
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}/v1",
        "version": meta.get("version") or __version__,
        "log": str(daemon_log_path()),
        "health": health,
        "meta": meta,
    }


def start_daemon(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Spawn `python -m aegis serve --host … --port …` detached in background.
    If a login LaunchAgent is installed, bootstrap it instead.
    Returns status dict.
    """
    ensure_home()
    # Prefer launchd when login agent is installed — but not under a temp
    # AEGIS_HOME (tests / alternate data planes still use Popen).
    use_launchd = (
        sys.platform == "darwin"
        and not os.environ.get("AEGIS_HOME")
    )
    if use_launchd:
        try:
            from aegis.launchd import bootstrap, is_installed, is_loaded, write_plist

            if is_installed():
                st = daemon_status()
                if st["running"] and not force:
                    return {
                        "ok": True,
                        "started": False,
                        "message": "already running (launchd)",
                        "managed_by": "launchd",
                        **st,
                    }
                if force or st.get("alive_process"):
                    stop_daemon(respect_launchd=True)
                write_plist(host, port)
                boot = bootstrap()
                for _ in range(20):
                    time.sleep(0.15)
                    st = daemon_status()
                    if st.get("running"):
                        return {
                            "ok": True,
                            "started": True,
                            "message": "started via launchd",
                            "managed_by": "launchd",
                            "bootstrap": boot,
                            **st,
                        }
                st = daemon_status()
                return {
                    "ok": bool(st.get("alive_process")),
                    "started": True,
                    "message": "launchd bootstrapped (health pending)"
                    if st.get("alive_process")
                    else "launchd start failed",
                    "managed_by": "launchd",
                    "bootstrap": boot,
                    **st,
                }
        except Exception:  # noqa: BLE001
            pass

    st = daemon_status()
    if st["running"] and not force:
        return {
            "ok": True,
            "started": False,
            "message": "already running",
            **st,
        }
    if st.get("alive_process") and force:
        stop_daemon(respect_launchd=False)

    log_path = daemon_log_path()
    # Detached child: foreground serve writes to log
    cmd = [
        sys.executable,
        "-m",
        "aegis",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
        "--foreground",
    ]
    env = os.environ.copy()
    # Ensure editable/src install is visible to the child
    src_root = str(Path(__file__).resolve().parents[1])  # .../src
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_root + (os.pathsep + prev if prev else "")

    log_f = open(log_path, "a", encoding="utf-8")
    log_f.write(f"\n--- start {_now()} v{__version__} {host}:{port} ---\n")
    log_f.write(f"cmd: {' '.join(cmd)}\n")
    log_f.flush()
    popen_kwargs: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_f,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
        "env": env,
    }
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    proc = subprocess.Popen(cmd, **popen_kwargs)
    # parent closes its copy; child retains the open log fd
    try:
        log_f.close()
    except OSError:
        pass
    _write_meta(host, port, proc.pid)

    # wait briefly for health
    for _ in range(20):
        time.sleep(0.15)
        st = daemon_status()
        if st.get("running"):
            return {
                "ok": True,
                "started": True,
                "message": "started",
                **st,
            }
    # process may still be starting
    st = daemon_status()
    return {
        "ok": bool(st.get("alive_process")),
        "started": True,
        "message": "started (health pending)" if st.get("alive_process") else "failed",
        **st,
    }


def stop_daemon(timeout: float = 5.0, *, respect_launchd: bool = True) -> Dict[str, Any]:
    """
    Stop the router process.

    If the login LaunchAgent is loaded and respect_launchd=True, bootout first
    so KeepAlive does not immediately respawn the process.
    """
    launchd_note = None
    # Never bootout the login agent from alternate AEGIS_HOME (tests).
    if respect_launchd and sys.platform == "darwin" and not os.environ.get("AEGIS_HOME"):
        try:
            from aegis.launchd import bootout, is_loaded

            if is_loaded():
                launchd_note = bootout()
        except Exception as exc:  # noqa: BLE001
            launchd_note = {"ok": False, "message": str(exc)}

    pid = _read_pid()
    if not pid:
        _clear_meta()
        return {
            "ok": True,
            "stopped": False,
            "message": "not running",
            "launchd": launchd_note,
        }
    if not _pid_alive(pid):
        _clear_meta()
        return {
            "ok": True,
            "stopped": False,
            "message": "stale pid cleared",
            "launchd": launchd_note,
        }

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        _clear_meta()
        return {
            "ok": False,
            "stopped": False,
            "message": str(exc),
            "pid": pid,
            "launchd": launchd_note,
        }

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            _clear_meta()
            return {
                "ok": True,
                "stopped": True,
                "message": "stopped",
                "pid": pid,
                "launchd": launchd_note,
            }
        time.sleep(0.1)

    # force
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    _clear_meta()
    return {
        "ok": True,
        "stopped": True,
        "message": "killed",
        "pid": pid,
        "launchd": launchd_note,
    }


def restart_daemon(host: str = "127.0.0.1", port: int = 8787) -> Dict[str, Any]:
    """Restart router; prefer re-bootstrap if login agent is installed."""
    if sys.platform == "darwin" and not os.environ.get("AEGIS_HOME"):
        try:
            from aegis.launchd import bootstrap, is_installed, is_loaded, write_plist

            if is_installed():
                stop = stop_daemon(respect_launchd=True)
                write_plist(host, port)  # refresh host/port
                boot = bootstrap()
                # wait for health
                for _ in range(20):
                    time.sleep(0.15)
                    st = daemon_status()
                    if st.get("running"):
                        return {
                            "stop": stop,
                            "start": {"ok": True, "started": True, "message": "launchd", **st},
                            "bootstrap": boot,
                            "ok": True,
                        }
                st = daemon_status()
                return {
                    "stop": stop,
                    "start": {"ok": bool(st.get("alive_process")), **st},
                    "bootstrap": boot,
                    "ok": bool(st.get("running") or st.get("alive_process")),
                }
        except Exception:  # noqa: BLE001
            pass
    stop = stop_daemon()
    start = start_daemon(host, port, force=False)
    return {"stop": stop, "start": start, "ok": start.get("ok", False)}
