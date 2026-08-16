"""
Background control for the Aegis router daemon.

  aegis serve --background
  aegis daemon start|stop|status|restart

PID/log/meta live under ~/.aegis/
"""

from __future__ import annotations

import errno
import json
import os
import signal
import socket
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


def probe_bind(host: str, port: int) -> Dict[str, Any]:
    """Preflight: can this process bind host:port? Does not leave a listener."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, int(port)))
        return {"ok": True, "state": "available", "host": host, "port": int(port)}
    except OSError as exc:
        err = getattr(exc, "errno", None)
        if err == errno.EADDRINUSE:
            state = "in_use"
        elif err in (errno.EACCES, errno.EPERM):
            state = "denied"
        else:
            state = "error"
        return {
            "ok": False,
            "state": state,
            "error": str(exc),
            "errno": err,
            "host": host,
            "port": int(port),
        }
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _bind_error_of(status: Dict[str, Any]) -> Optional[str]:
    if not isinstance(status, dict):
        return None
    raw = status.get("bind_error") or status.get("bindError")
    if raw:
        return str(raw)
    meta = status.get("meta") or {}
    raw = meta.get("bind_error") or meta.get("bindError")
    return str(raw) if raw else None


def wait_for_health(
    host: Optional[str] = None,
    port: Optional[int] = None,
    timeout: float = 5.0,
    interval: float = 0.05,
) -> Dict[str, Any]:
    """Poll until healthy | bind_failed | dead | timeout."""
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    probe_timeout = min(0.4, max(0.1, interval * 4))
    while time.time() < deadline:
        last = daemon_status(host=host, port=port, health_timeout=probe_timeout)
        if last.get("running"):
            return {"state": "healthy", "ok": True, **last}
        bind_error = _bind_error_of(last)
        if bind_error:
            return {
                "state": "bind_failed",
                "ok": False,
                "bind_error": bind_error,
                "bindError": bind_error,
                **last,
            }
        if last.get("pid") and not last.get("alive_process"):
            return {"state": "dead", "ok": False, **last}
        if not last.get("pid") and not last.get("alive_process") and last.get("meta") == {}:
            # No process registered yet — keep polling until timeout, then dead.
            pass
        time.sleep(interval)
    if last.get("alive_process"):
        return {"state": "timeout", "ok": False, **last}
    return {"state": "dead", "ok": False, **last}


def daemon_status(
    host: Optional[str] = None,
    port: Optional[int] = None,
    health_timeout: float = 2.0,
) -> Dict[str, Any]:
    """Return running state + health probe."""
    pid = _read_pid()
    meta = load_meta()
    bind_error = meta.get("bind_error") or meta.get("bindError")
    use_host = host or meta.get("host") or "127.0.0.1"
    use_port = port if port is not None else int(meta.get("port") or 8787)
    alive = bool(pid and _pid_alive(pid))
    if pid and not alive:
        # stale pid file — keep bindError for classification before wipe
        _clear_meta()
        pid = None
        alive = False
        meta = {"bind_error": bind_error, "bindError": bind_error} if bind_error else {}
    health: Dict[str, Any] = {"reachable": False}
    if alive:
        try:
            url = f"http://{use_host}:{use_port}/healthz"
            with urllib.request.urlopen(url, timeout=health_timeout) as resp:
                health = json.loads(resp.read().decode("utf-8"))
                health["reachable"] = True
                health["http_status"] = resp.status
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            health = {"reachable": False, "error": str(exc)}
    return {
        "running": alive and health.get("reachable", False),
        "pid": pid,
        "alive_process": alive,
        "host": use_host,
        "port": use_port,
        "url": f"http://{use_host}:{use_port}/v1",
        "version": meta.get("version") or __version__,
        "log": str(daemon_log_path()),
        "health": health,
        "bind_error": bind_error,
        "bindError": bind_error,
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
                st = daemon_status(host=host, port=port)
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
                waited = wait_for_health(host=host, port=port, timeout=4.0, interval=0.05)
                if waited.get("state") == "healthy":
                    return {
                        "ok": True,
                        "started": True,
                        "message": "started via launchd",
                        "managed_by": "launchd",
                        "bootstrap": boot,
                        **waited,
                    }
                return {
                    "ok": False,
                    "started": bool(waited.get("alive_process")),
                    "message": f"launchd {waited.get('state')}",
                    "startup": waited.get("state"),
                    "managed_by": "launchd",
                    "bootstrap": boot,
                    **{k: v for k, v in waited.items() if k not in {"ok", "state"}},
                }
        except Exception:  # noqa: BLE001
            pass

    st = daemon_status(host=host, port=port)
    if st["running"] and not force:
        return {
            "ok": True,
            "started": False,
            "message": "already running",
            **st,
        }
    if st.get("alive_process"):
        meta_port = int((st.get("meta") or {}).get("port") or st.get("port") or 0)
        if not force:
            return {
                "ok": False,
                "started": False,
                "message": (
                    "alive process holds control files; refuse second spawn "
                    f"(pid={st.get('pid')} port={meta_port})"
                ),
                "conflict": True,
                **st,
            }
        stop_daemon(respect_launchd=False)

    bind = probe_bind(host, port)
    if not bind.get("ok"):
        return {
            "ok": False,
            "started": False,
            "message": f"bind preflight {bind.get('state')}",
            "bind": bind,
            **st,
        }

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

    waited = wait_for_health(host=host, port=port, timeout=4.0, interval=0.05)
    if waited.get("state") == "healthy":
        return {
            "ok": True,
            "started": True,
            "message": "started",
            **waited,
        }
    if waited.get("alive_process"):
        stop_daemon(respect_launchd=False)
        waited["reaped"] = True
    return {
        "ok": False,
        "started": False,
        "message": f"start {waited.get('state')}",
        "startup": waited.get("state"),
        **{k: v for k, v in waited.items() if k not in {"ok", "state"}},
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
                waited = wait_for_health(host=host, port=port, timeout=4.0, interval=0.05)
                start = {
                    "ok": waited.get("state") == "healthy",
                    "started": waited.get("state") == "healthy",
                    "message": "launchd" if waited.get("state") == "healthy" else f"launchd {waited.get('state')}",
                    **waited,
                }
                return {
                    "stop": stop,
                    "start": start,
                    "bootstrap": boot,
                    "ok": bool(start.get("ok")),
                }
        except Exception:  # noqa: BLE001
            pass
    stop = stop_daemon()
    start = start_daemon(host, port, force=False)
    return {"stop": stop, "start": start, "ok": start.get("ok", False)}
