"""Portable product home: init, backup, restore, uninstall.

Schema 2 homes are relocatable. Manifest stores no host-absolute paths.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aegis import __version__
from aegis.paths import (
    aegis_home,
    backups_dir,
    ensure_home,
    manifest_path,
)

SCHEMA_VERSION = 2
SKIP_BACKUP_NAMES = frozenset({"router.pid"})


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_manifest(home: Optional[Path] = None) -> Dict[str, Any]:
    path = (home or aegis_home()) / "MANIFEST.json" if home else manifest_path()
    if home is not None:
        path = Path(home) / "MANIFEST.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_manifest(home: Optional[Path] = None, **extra: Any) -> Dict[str, Any]:
    root = Path(home) if home is not None else ensure_home()
    root.mkdir(parents=True, exist_ok=True)
    existing = read_manifest(root)
    body: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "product": "aegis",
        "kind": "local_program",
        "portable": True,
        "version": __version__,
        "created_at": existing.get("created_at") or utc_now(),
        "upgraded_at": utc_now(),
    }
    body.update(extra)
    path = root / "MANIFEST.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return body


def ensure_schema(home: Optional[Path] = None) -> Dict[str, Any]:
    """Create or upgrade MANIFEST. Never writes host-absolute paths."""
    root = Path(home) if home is not None else ensure_home()
    for name in ("packs", "outputs", "kernel", "backups"):
        (root / name).mkdir(parents=True, exist_ok=True)
    man = read_manifest(root)
    schema = int(man.get("schema") or 0)
    if schema >= SCHEMA_VERSION and man.get("portable") is True:
        return man
    return write_manifest(root)


def init_home(home: Optional[str] = None) -> Dict[str, Any]:
    """Second-machine product init. Isolated to AEGIS_HOME / given path."""
    import os

    if home:
        os.environ["AEGIS_HOME"] = str(Path(home).expanduser())
    root = ensure_home()
    from aegis.config import load_config

    load_config()
    man = ensure_schema(root)
    return {
        "ok": True,
        "home": str(root),
        "schema": man.get("schema"),
        "version": __version__,
        "portable": True,
        "manifest": man,
    }


def backup_home(dest: Optional[str] = None, home: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(home) if home is not None else ensure_home()
    ensure_schema(root)
    out_dir = Path(dest).expanduser() if dest else backups_dir()
    if dest:
        out_dir = Path(dest).expanduser()
        if out_dir.suffix in {".gz", ".tgz"} or str(out_dir).endswith(".tar.gz"):
            archive = out_dir
            archive.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            archive = out_dir / f"aegis-home-{stamp}.tar.gz"
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = out_dir / f"aegis-home-{stamp}.tar.gz"

    def _filter(info: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
        name = Path(info.name).name
        if name in SKIP_BACKUP_NAMES or name.endswith(".tmp"):
            return None
        return info

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(str(root), arcname="aegis-home", filter=_filter)
    size = archive.stat().st_size if archive.is_file() else 0
    return {
        "ok": True,
        "archive": str(archive.resolve()),
        "bytes": size,
        "home": str(root),
        "schema": SCHEMA_VERSION,
    }


def restore_home(archive: str, home: Optional[str] = None) -> Dict[str, Any]:
    src = Path(archive).expanduser().resolve()
    if not src.is_file():
        return {"ok": False, "error": f"archive not found: {src}"}
    target = Path(home).expanduser().resolve() if home else aegis_home()
    if target == Path("/") or target == Path.home():
        return {"ok": False, "error": "refuse restore into / or $HOME"}
    with tarfile.open(src, "r:gz") as tar:
        names = tar.getnames()
        if not names or not any(n == "aegis-home" or n.startswith("aegis-home/") for n in names):
            return {"ok": False, "error": "archive missing aegis-home prefix"}
        tmp = Path(tempfile.mkdtemp(prefix="aegis-restore-"))
        try:
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:
                tar.extractall(tmp)
            extracted = tmp / "aegis-home"
            if not extracted.is_dir():
                return {"ok": False, "error": "extracted tree missing"}
            man = read_manifest(extracted)
            if int(man.get("schema") or 0) < 1:
                return {"ok": False, "error": "archive has no MANIFEST schema"}
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(extracted), str(target))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    ensure_schema(target)
    return {
        "ok": True,
        "home": str(target),
        "archive": str(src),
        "schema": read_manifest(target).get("schema"),
    }


def uninstall_home(*, yes: bool, home: Optional[str] = None) -> Dict[str, Any]:
    """Delete the data plane only. Does not uninstall the Python package."""
    if not yes:
        return {"ok": False, "error": "refused: pass --yes"}
    target = Path(home).expanduser().resolve() if home else aegis_home()
    if target == Path("/") or target == Path.home():
        return {"ok": False, "error": "refuse uninstall of / or $HOME"}
    man = read_manifest(target)
    if not man and not (target / "packs").is_dir() and not (target / "ledger.jsonl").is_file():
        return {"ok": False, "error": f"not an Aegis home: {target}"}
    if target.exists():
        shutil.rmtree(target)
    return {"ok": True, "removed": str(target), "package_intact": True}
