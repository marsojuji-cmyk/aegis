"""
macOS launchd integration — start Aegis router at login.

  aegis daemon install-login
  aegis daemon uninstall-login

Plist: ~/Library/LaunchAgents/com.aegis.router.plist
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

LABEL = "com.aegis.router"


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist_path() -> Path:
    return launch_agents_dir() / f"{LABEL}.plist"


def launchd_log_out() -> Path:
    from aegis.paths import aegis_home

    return aegis_home() / "router.launchd.out.log"


def launchd_log_err() -> Path:
    from aegis.paths import aegis_home

    return aegis_home() / "router.launchd.err.log"


def _uid() -> int:
    return os.getuid()


def _domain() -> str:
    return f"gui/{_uid()}"


def _service_target() -> str:
    return f"{_domain()}/{LABEL}"


def _python_executable() -> str:
    """
    Prefer system Python for LaunchAgents.

    Xcode's python3 (…/Developer/usr/bin/python3) often hangs in xpcproxy
    when launched by launchd; /usr/bin/python3 is reliable for login agents.
    """
    candidates = []
    if sys.platform == "darwin":
        candidates.append("/usr/bin/python3")
    # only use sys.executable if it isn't the Xcode stub path
    exe = sys.executable or ""
    if exe and "Xcode.app" not in exe and "CommandLineTools" not in exe:
        candidates.append(exe)
    elif exe:
        candidates.append(exe)  # last resort
    candidates.append("/usr/bin/python3")
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return "/usr/bin/python3"


def _src_root() -> str:
    # .../src/aegis/launchd.py → .../src
    return str(Path(__file__).resolve().parents[1])


def build_plist(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    python: Optional[str] = None,
) -> Dict[str, Any]:
    """Build LaunchAgent dict (RunAtLoad + KeepAlive)."""
    from aegis.paths import ensure_home

    ensure_home()
    py = python or _python_executable()
    src = _src_root()
    home = Path.home()
    path_env = os.environ.get(
        "PATH",
        f"/usr/local/bin:/usr/bin:/bin:{home / '.local' / 'bin'}:{home / 'homebrew' / 'bin'}",
    )
    # Prefer a stable PATH for login sessions
    for extra in (
        str(home / ".local" / "bin"),
        str(home / "homebrew" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ):
        if extra not in path_env:
            path_env = extra + ":" + path_env

    env: Dict[str, str] = {
        "PATH": path_env,
        "PYTHONPATH": src,
        "AEGIS_MANAGED_BY": "launchd",
    }
    home = os.environ.get("AEGIS_HOME")
    if home:
        env["AEGIS_HOME"] = home

    return {
        "Label": LABEL,
        "ProgramArguments": [
            py,
            "-m",
            "aegis",
            "serve",
            "--host",
            host,
            "--port",
            str(port),
            "--foreground",
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(launchd_log_out()),
        "StandardErrorPath": str(launchd_log_err()),
        "EnvironmentVariables": env,
        "WorkingDirectory": str(Path.home()),
    }


def write_plist(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    python: Optional[str] = None,
) -> Path:
    launch_agents_dir().mkdir(parents=True, exist_ok=True)
    path = plist_path()
    data = build_plist(host, port, python=python)
    with path.open("wb") as f:
        plistlib.dump(data, f, sort_keys=False)
    return path


def is_installed() -> bool:
    return plist_path().is_file()


def is_loaded() -> bool:
    """True if launchd knows about the service (loaded into the GUI domain)."""
    if sys.platform != "darwin":
        return False
    # Prefer modern print
    r = subprocess.run(
        ["launchctl", "print", _service_target()],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return True
    # Fallback list
    r2 = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True,
    )
    if r2.returncode == 0 and LABEL in (r2.stdout or ""):
        return True
    return False


def _run_launchctl(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        text=True,
    )


def bootstrap() -> Dict[str, Any]:
    """Load the agent into the current user's GUI domain."""
    if sys.platform != "darwin":
        return {"ok": False, "message": "launchd only on macOS"}
    path = plist_path()
    if not path.is_file():
        return {"ok": False, "message": f"plist missing: {path}"}

    # Modern: bootstrap gui/$UID /path/to.plist
    r = _run_launchctl(["bootstrap", _domain(), str(path)])
    if r.returncode == 0:
        return {"ok": True, "message": "bootstrapped", "method": "bootstrap"}

    err = (r.stderr or r.stdout or "").strip()
    # Already loaded is fine
    if "already bootstrapped" in err.lower() or "service already loaded" in err.lower():
        return {"ok": True, "message": "already loaded", "method": "bootstrap"}

    # Legacy fallback
    r2 = _run_launchctl(["load", "-w", str(path)])
    if r2.returncode == 0:
        return {"ok": True, "message": "loaded", "method": "load"}
    err2 = (r2.stderr or r2.stdout or err).strip()
    if "already loaded" in err2.lower():
        return {"ok": True, "message": "already loaded", "method": "load"}
    return {
        "ok": False,
        "message": err2 or err or "bootstrap failed",
        "stderr": err2 or err,
    }


def bootout() -> Dict[str, Any]:
    """Unload the agent (keeps plist on disk)."""
    if sys.platform != "darwin":
        return {"ok": False, "message": "launchd only on macOS"}
    if not is_loaded() and not is_installed():
        return {"ok": True, "message": "not loaded"}

    r = _run_launchctl(["bootout", _service_target()])
    if r.returncode == 0:
        return {"ok": True, "message": "bootout", "method": "bootout"}

    err = (r.stderr or r.stdout or "").strip()
    if "No such process" in err or "Could not find" in err or "not found" in err.lower():
        # try unload by path
        path = plist_path()
        if path.is_file():
            r2 = _run_launchctl(["unload", "-w", str(path)])
            if r2.returncode == 0 or "not loaded" in (r2.stderr or "").lower():
                return {"ok": True, "message": "unloaded", "method": "unload"}
        return {"ok": True, "message": "not loaded"}

    # legacy unload
    path = plist_path()
    if path.is_file():
        r2 = _run_launchctl(["unload", "-w", str(path)])
        if r2.returncode == 0:
            return {"ok": True, "message": "unloaded", "method": "unload"}
        err2 = (r2.stderr or "").strip()
        if "not loaded" in err2.lower():
            return {"ok": True, "message": "not loaded"}
        return {"ok": False, "message": err2 or err}

    return {"ok": False, "message": err or "bootout failed"}


def install_login(host: str = "127.0.0.1", port: int = 8787) -> Dict[str, Any]:
    """
    Write LaunchAgent plist and load it (starts now + every login).
    Stops any non-launchd daemon first so the port is free.
    """
    if sys.platform != "darwin":
        return {"ok": False, "message": "launchd only on macOS", "platform": sys.platform}

    from aegis.daemon_control import daemon_status, stop_daemon

    # If a manual background daemon holds the port, free it
    st = daemon_status()
    if st.get("alive_process") and not is_loaded():
        stop_daemon()

    # If already loaded, reload with new plist
    if is_loaded():
        bootout()

    path = write_plist(host, port)
    boot = bootstrap()
    if not boot.get("ok"):
        return {
            "ok": False,
            "message": boot.get("message"),
            "plist": str(path),
            "label": LABEL,
        }

    # Wait briefly for health
    import time

    running = False
    for _ in range(25):
        time.sleep(0.2)
        st = daemon_status()
        if st.get("running"):
            running = True
            break

    return {
        "ok": True,
        "message": "login agent installed",
        "plist": str(path),
        "label": LABEL,
        "loaded": is_loaded(),
        "running": running,
        "url": f"http://{host}:{port}/v1",
        "host": host,
        "port": port,
        "bootstrap": boot,
        "log_out": str(launchd_log_out()),
        "log_err": str(launchd_log_err()),
    }


def uninstall_login(*, stop: bool = True) -> Dict[str, Any]:
    """Unload launchd agent and remove plist. Optionally stop router."""
    if sys.platform != "darwin":
        return {"ok": False, "message": "launchd only on macOS"}

    from aegis.daemon_control import stop_daemon

    bo = bootout()
    path = plist_path()
    removed = False
    if path.is_file():
        try:
            path.unlink()
            removed = True
        except OSError as exc:
            return {
                "ok": False,
                "message": f"could not remove plist: {exc}",
                "bootout": bo,
            }

    stopped = None
    if stop:
        stopped = stop_daemon()

    return {
        "ok": True,
        "message": "login agent removed",
        "plist_removed": removed,
        "bootout": bo,
        "stop": stopped,
        "label": LABEL,
    }


def launchd_status() -> Dict[str, Any]:
    """Report install/load state (and merge daemon health if available)."""
    installed = is_installed()
    loaded = is_loaded() if installed or sys.platform == "darwin" else False
    info: Dict[str, Any] = {
        "platform": sys.platform,
        "label": LABEL,
        "plist": str(plist_path()),
        "installed": installed,
        "loaded": loaded,
        "domain": _domain() if sys.platform == "darwin" else None,
    }
    if installed:
        try:
            with plist_path().open("rb") as f:
                pl = plistlib.load(f)
            args = pl.get("ProgramArguments") or []
            info["program_arguments"] = args
            # extract host/port if present
            if "--host" in args:
                i = args.index("--host")
                if i + 1 < len(args):
                    info["host"] = args[i + 1]
            if "--port" in args:
                i = args.index("--port")
                if i + 1 < len(args):
                    info["port"] = int(args[i + 1])
        except (OSError, plistlib.InvalidFileException, ValueError):
            pass
    return info
