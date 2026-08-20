"""Health / migration checks for frictionless evolution."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aegis import __version__
from aegis.compat.legacy import (
    expense_report_path,
    get_engine_name,
    legacy_available,
    legacy_pipeline_path,
    load_legacy_modules,
    rules_path,
    skill_path,
)
from aegis.config import resolve_hermes_notes_root
from aegis.hermes_index import DEFAULT_ROOT
from aegis.paths import (
    aegis_home,
    fund_path,
    hermes_index_files_path,
    hermes_index_notes_path,
    ideas_path,
    ledger_path,
    packs_dir,
)


Check = Tuple[str, bool, str]

# FIRST_RELEASE.md path table. Classification only — not a config override.
CANONICAL_HERMES_CORPUS = Path(
    "/Users/a100/Library/Mobile Documents/iCloud~md~obsidian/Documents/AGIS"
    "/AEGIS/05-Memory-Utility-Labs"
)
COMPLEMENTARY_LABS = Path("/Users/a100/Documents/Memory Utility Labs")


def _resolve_existing(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _under_or_equal(resolved: Path, anchor: Path) -> bool:
    return resolved == anchor or anchor in resolved.parents


def classify_hermes_root(root: str, pin: str = "") -> str:
    """Label a root as canonical, complementary, empty_default_not_product, missing, or unknown."""
    if not str(root or "").strip():
        return "missing"
    try:
        resolved = Path(root).expanduser().resolve()
    except OSError:
        return "unknown"
    labs = _resolve_existing(COMPLEMENTARY_LABS)
    empty = _resolve_existing(Path(DEFAULT_ROOT))
    if _under_or_equal(resolved, labs):
        return "complementary"
    if _under_or_equal(resolved, empty):
        return "empty_default_not_product"
    pin = str(pin or "").strip()
    if pin:
        if _under_or_equal(resolved, _resolve_existing(Path(pin))):
            return "canonical"
        return "unknown"
    fallback = _resolve_existing(CANONICAL_HERMES_CORPUS)
    if _under_or_equal(resolved, fallback):
        return "canonical"
    return "unknown"


def _index_locator(path: Path, pin: str = "") -> Dict[str, Any]:
    if not path.is_file():
        return {"root": "", "count": 0, "role": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"root": "", "count": 0, "role": "unknown"}
    root = str(payload.get("root") or "")
    count = payload.get("note_count")
    if count is None:
        count = payload.get("file_count") or 0
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 0
    return {"root": root, "count": n, "role": classify_hermes_root(root, pin=pin)}


def _path_presence(path: Path) -> str:
    return "exists" if path.is_dir() else "missing"


def hermes_rebuild_root_decision(root: str) -> Dict[str, Any]:
    """Allow rebuild only for a pinned or FIRST_RELEASE-fallback canonical directory."""
    pin = resolve_hermes_notes_root()
    raw = str(root or "").strip() or DEFAULT_ROOT
    role = classify_hermes_root(raw, pin=pin)
    try:
        resolved = str(Path(raw).expanduser().resolve())
    except OSError:
        return {
            "allowed": False,
            "role": "unknown",
            "resolved": raw,
            "reason": "root is not a usable path",
        }
    if role == "canonical" and Path(resolved).is_dir():
        return {"allowed": True, "role": role, "resolved": resolved, "reason": ""}
    reasons = {
        "complementary": "Documents Labs is not the Hermes product corpus",
        "empty_default_not_product": "empty default root is not a v1 rebuild target",
        "missing": "rebuild root is missing",
        "unknown": "rebuild root is not the pinned or canonical Hermes corpus",
        "canonical": "rebuild root does not exist",
    }
    return {
        "allowed": False,
        "role": role,
        "resolved": resolved,
        "reason": reasons.get(role, "rebuild root is not allowed"),
    }


def hermes_v1_ready(pin: str, notes_root: str, notes_role: str) -> bool:
    pin = str(pin or "").strip()
    if not pin:
        return False
    if classify_hermes_root(pin, pin=pin) != "canonical":
        return False
    if not Path(pin).expanduser().is_dir():
        return False
    if notes_role != "canonical":
        return False
    try:
        return _under_or_equal(
            Path(notes_root).expanduser().resolve(),
            _resolve_existing(Path(pin)),
        )
    except OSError:
        return False


def hermes_corpus_check() -> Check:
    """Classify FIRST_RELEASE roots and on-disk index roles. Does not rebuild."""
    pin = resolve_hermes_notes_root()
    notes = _index_locator(hermes_index_notes_path(), pin=pin)
    files = _index_locator(hermes_index_files_path(), pin=pin)
    notes_role = str(notes["role"])
    ok = notes_role in ("missing", "canonical")
    ready = "yes" if hermes_v1_ready(pin, str(notes["root"]), notes_role) else "no"
    pin_state = "set" if pin else "unset"
    detail = (
        f"canonical={_path_presence(CANONICAL_HERMES_CORPUS)} "
        f"complementary={_path_presence(COMPLEMENTARY_LABS)} "
        f"empty_default={_path_presence(Path(DEFAULT_ROOT))} "
        f"notes={notes_role}:{notes['count']} "
        f"files={files['role']}:{files['count']} "
        f"pin={pin_state} v1_ready={ready}"
    )
    return ("hermes_corpus", ok, detail)


def _product_os_checks() -> List[Check]:
    """Second-machine product floor. Does not require this-host AGIS paths."""
    from aegis.api_contract import spec
    from aegis.kernel import drivers
    from aegis.portable import SCHEMA_VERSION, ensure_schema

    try:
        man = ensure_schema()
    except OSError as exc:
        return [
            ("product_schema", False, f"home not writable ({exc})"),
            ("agent_kernel", False, "skipped"),
            ("api_contract", False, "skipped"),
            ("portable_home", False, str(aegis_home())),
        ]
    schema_ok = int(man.get("schema") or 0) >= SCHEMA_VERSION and man.get("portable") is True
    drv = drivers()
    present = sum(1 for d in drv if d.get("present") == "yes")
    spec_body = spec()
    spec_ok = spec_body.get("ok") is True and spec_body.get("stability") == "frozen"
    return [
        (
            "product_schema",
            schema_ok,
            f"schema={man.get('schema')} portable={man.get('portable')}",
        ),
        ("agent_kernel", present == len(drv), f"{present}/{len(drv)} drivers"),
        (
            "api_contract",
            spec_ok,
            f"{len(spec_body.get('endpoints') or [])} frozen /v1 endpoints",
        ),
        ("portable_home", True, str(aegis_home())),
    ]


def _release_program_checks() -> List[Check]:
    """Release floor: autonomy off, no fake savings. Reuse rate is a cue, not a fail."""
    try:
        from aegis.config import load_config, opt_in
        from aegis.ledger import generate_report
        from aegis.yield_proof import yield_report

        cfg = load_config()
        flags = ("auto_tick", "auto_invest", "auto_apply_fixes", "auto_memory")
        armed = [n for n in flags if opt_in(cfg, n)]
        yld = yield_report()
        honest = yld.get("savings_percent") is None
        try:
            rate = float((generate_report() or {}).get("reuse_hit_rate_percent") or 0)
        except Exception:  # noqa: BLE001
            rate = 0.0
        return [
            (
                "freeze_autonomy",
                not armed,
                "off" if not armed else "armed=" + ",".join(armed),
            ),
            (
                "yield_honest",
                honest,
                (
                    f"savings_percent={yld.get('savings_percent')} "
                    f"ledger_saved={yld.get('ledger_tokens_saved_local')} "
                    f"billed_Δusd={(yld.get('billed_pairs') or {}).get('total_cost_usd_saved')} "
                    f"admitted={yld.get('admitted_pair')}"
                ),
            ),
            (
                "reuse_cue",
                True,
                f"week={rate}% target≥50 — covering reuse only when file hashes match",
            ),
        ]
    except OSError as exc:
        return [
            ("freeze_autonomy", False, f"home not writable ({exc})"),
            ("yield_honest", False, "skipped"),
            ("reuse_cue", True, "skipped"),
        ]


def run_checks() -> List[Check]:
    checks: List[Check] = []
    engine = get_engine_name()

    checks.append(("product_version", True, f"aegis {__version__}"))
    checks.append(("engine", engine in ("legacy", "product"), f"AEGIS_ENGINE={engine}"))

    legacy_ok = legacy_available()
    checks.append(
        (
            "legacy_pipeline",
            True,
            legacy_pipeline_path() if legacy_ok else "not installed (native product engine active)",
        )
    )

    if legacy_ok:
        try:
            mods = load_legacy_modules()
            ok = all(
                k in mods
                for k in (
                    "TokenSupplyChainInspector",
                    "JITContextAssembler",
                    "TokenLedger",
                )
            )
            checks.append(("legacy_import", ok, "token_supply_chain + token_ledger"))
        except Exception as exc:  # noqa: BLE001
            checks.append(("legacy_import", False, str(exc)))
    else:
        checks.append(("legacy_import", True, "skipped — native product engine"))

    product_engines = False
    try:
        from aegis import bento as _bento  # noqa: F401
        from aegis import ast_slice as _ast  # noqa: F401

        product_engines = True
    except Exception as exc:  # noqa: BLE001
        product_engines = False
        _engine_err = str(exc)
    else:
        _engine_err = ""
    checks.append(
        (
            "product_engines",
            product_engines if engine == "product" else True,
            (
                "E3 multi-lang bento ready"
                if product_engines
                else f"missing ({_engine_err})"
            ),
        )
    )
    try:
        from aegis.treesitter_backend import treesitter_available, tsx_status

        ts_ok = treesitter_available()
        tsx = tsx_status() if ts_ok else {"validated": False, "detail": {}}
    except Exception:
        ts_ok = False
        tsx = {"validated": False, "detail": {"reason": "import_error"}}
    checks.append(
        (
            "treesitter_optional",
            True,  # optional — never fail doctor
            "active for py/js/ts" if ts_ok else "not installed (regex/stdlib fallback)",
        )
    )
    tsx_detail = (tsx.get("detail") or {}).get("reason", "")
    checks.append(
        (
            "tsx_grammar",
            True,
            (
                f"validated ({tsx_detail})"
                if tsx.get("validated")
                else f"not enabled — fallback TS/regex ({tsx_detail})"
            ),
        )
    )
    try:
        from aegis.output_store import store_stats

        st = store_stats()
        checks.append(
            (
                "output_store",
                True,
                f"{st['entries']} entries · tok saved {st['tokens_saved']} · "
                f"bytes saved {st.get('bytes_saved', 0)}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("output_store", True, f"unavailable ({exc})"))
    try:
        from aegis.providers import list_providers
        from aegis.router_pipeline import router_status

        providers = list_providers()
        n = len(providers)
        remote = [p for p in providers if p["kind"] not in ("mock", "ollama")]
        configured = sum(1 for p in remote if p["credentials"])
        st = router_status()
        checks.append(
            (
                "universal_router",
                True,
                f"{n} providers · concurrent≤{st.get('max_concurrent_default')} · "
                f"remote credentials={configured}/{len(remote)} · "
                f"outputs={st.get('unified_output_dir')}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("universal_router", True, f"import deferred ({exc})"))
    try:
        from aegis.cursor_bridge import cursor_status

        cs = cursor_status()
        checks.append(
            (
                "cursor_bridge",
                True,
                f"rules_product={cs['cursorrules_product']} "
                f"rules_cwd={cs['cursorrules_cwd']} · "
                f"outputs={cs['outputs_dir']}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("cursor_bridge", True, f"import deferred ({exc})"))
    try:
        from aegis.wrappers import AntiGravityWrapper, OpenAIWrapper

        _ = OpenAIWrapper(dry_run=True)
        _ = AntiGravityWrapper(dry_run=True)
        checks.append(
            (
                "wrappers",
                True,
                "openai + antigravity intercept → full pipeline",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("wrappers", False, str(exc)))
    try:
        from aegis.daemon_control import daemon_status

        ds = daemon_status()
        checks.append(
            (
                "background_daemon",
                True,
                (
                    f"running pid={ds.get('pid')} {ds.get('url')}"
                    if ds.get("running")
                    else "stopped (aegis serve --background | aegis daemon start)"
                ),
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("background_daemon", True, f"status unavailable ({exc})"))
    try:
        from aegis.launchd import launchd_status

        ld = launchd_status()
        if ld.get("platform") == "darwin":
            if ld.get("installed") and ld.get("loaded"):
                msg = f"login agent loaded ({ld.get('label')})"
            elif ld.get("installed"):
                msg = f"plist present but not loaded — aegis daemon install-login"
            else:
                msg = "not installed (aegis daemon install-login for start-at-login)"
            checks.append(("launchd_login", True, msg))
        else:
            checks.append(("launchd_login", True, f"n/a on {ld.get('platform')}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("launchd_login", True, f"status unavailable ({exc})"))
    try:
        from aegis.intelligence import intel_status

        ist = intel_status()
        cfg = ist.get("config") or {}
        state = ist.get("state") or {}
        checks.append(
            (
                "intelligence_layer",
                True,
                (
                    f"ticks={state.get('ticks')} auto_tick={cfg.get('auto_tick')} "
                    f"auto_invest={cfg.get('auto_invest')} "
                    f"cache_hit={ist.get('cache_hit_rate_percent')}% "
                    f"signals={len(ist.get('signals') or [])}"
                ),
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("intelligence_layer", False, str(exc)))
    try:
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        app_bundle = repo / "apps" / "AegisMenu" / "dist" / "AegisMenu.app"
        app_src = repo / "apps" / "AegisMenu" / "Sources" / "AegisMenu"
        if app_bundle.is_dir():
            checks.append(("swiftui_app", True, f"built {app_bundle}"))
        elif app_src.is_dir():
            checks.append(
                (
                    "swiftui_app",
                    True,
                    "sources present (aegis app build | aegis app open)",
                )
            )
        else:
            checks.append(("swiftui_app", True, "not present"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("swiftui_app", True, f"status unavailable ({exc})"))

    home = aegis_home()
    probe = home
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    home_ok = (
        home.is_dir() and os.access(home, os.W_OK)
    ) or (probe.is_dir() and os.access(probe, os.W_OK))
    checks.append(
        (
            "aegis_home",
            home_ok,
            f"{home} ({'writable' if home_ok else 'will create on first command'})",
        )
    )
    checks.append(
        (
            "ledger",
            True,
            str(ledger_path())
            + (f" ({ledger_path().stat().st_size} B)" if ledger_path().is_file() else " (empty)"),
        )
    )
    checks.append(
        (
            "fund",
            True,
            str(fund_path()) + (" exists" if fund_path().is_file() else " (will create)"),
        )
    )
    checks.append(
        (
            "ideas",
            True,
            str(ideas_path()) + (" exists" if ideas_path().is_file() else " (will seed)"),
        )
    )
    checks.append(("packs_dir", True, str(packs_dir())))
    checks.extend(_product_os_checks())
    checks.extend(_release_program_checks())
    checks.append(hermes_corpus_check())

    exp = expense_report_path()
    checks.append(
        (
            "legacy_expense_report",
            True,
            exp if os.path.isfile(exp) else "none (optional; not required for product)",
        )
    )

    sk = skill_path()
    checks.append(
        (
            "skill_aegis_tokenomics",
            True,
            sk if os.path.isfile(sk) else "optional (aegis cursor --install)",
        )
    )
    ru = rules_path()
    checks.append(
        (
            "rules_aegis_tokenomics",
            True,
            ru if os.path.isfile(ru) else "optional (not required for product)",
        )
    )

    checks.append(
        (
            "cli_entry",
            True,
            f"python -m aegis (argv0={os.path.basename(sys.argv[0])})",
        )
    )

    if engine == "product" and product_engines:
        checks.append(("compat_mode", True, "native product engine"))
    elif engine == "legacy" and legacy_ok:
        checks.append(("compat_mode", True, "strangler + durable piggy bank (E1+)"))
    elif engine == "product" and not product_engines:
        checks.append(
            (
                "compat_mode",
                False,
                "product selected but engines missing — set AEGIS_ENGINE=legacy",
            )
        )
    else:
        checks.append(("compat_mode", True, "native product; legacy pipeline optional"))

    return checks


def doctor_report() -> Dict[str, Any]:
    checks = run_checks()
    failed = [c for c in checks if not c[1]]
    try:
        from aegis.compound import compound_status

        compound = compound_status()
    except Exception:
        compound = {}
    product_names = {
        "product_schema",
        "agent_kernel",
        "api_contract",
        "portable_home",
        "aegis_home",
        "product_engines",
        "cli_entry",
        "freeze_autonomy",
        "yield_honest",
    }
    product_failed = [
        c for c in checks if c[0] in product_names and not c[1]
    ]
    return {
        "ok": len(failed) == 0,
        "product_ready": len(product_failed) == 0,
        "epoch": "1.2",
        "version": __version__,
        "summary": (
            f"v{__version__} ready" if not failed else f"{len(failed)} check(s) failed"
        ),
        "checks": [{"name": n, "pass": p, "detail": d} for n, p, d in checks],
        "compound": compound,
    }


def format_doctor_text(report: Dict[str, Any]) -> str:
    lines = [
        "Aegis doctor",
        f"  epoch:   {report['epoch']} (v1.2 Master Aegis product OS)",
        f"  version: {report.get('version', __version__)}",
        f"  status:  {report['summary']}",
        "",
    ]
    for c in report["checks"]:
        mark = "OK" if c["pass"] else "FAIL"
        lines.append(f"  [{mark:4}] {c['name']}: {c['detail']}")
    compound = report.get("compound") or {}
    if compound:
        lines.append("")
        lines.append(
            f"  compound: structured={compound.get('structured_count')} "
            f"treesitter={compound.get('treesitter_active')} "
            f"tsx={compound.get('tsx_validated')}"
        )
        lines.append(
            f"  pipeline: {' → '.join(compound.get('pipeline') or [])}"
        )
    lines.append("")
    if report["ok"]:
        lines.append(
            "Loop: preflight → pack → quality → model/router → shrink/store/reuse → ledger."
        )
    else:
        lines.append(
            "Fix FAIL items, or export AEGIS_ENGINE=legacy and restore scratch path."
        )
    return "\n".join(lines)


def release_report() -> Dict[str, Any]:
    """Buyer/operator gate for the local program. Does not thaw freezes."""
    from aegis.decisions import health as decisions_health
    from aegis.modules import health as modules_health

    doctor = doctor_report()
    decisions = decisions_health()
    modules = modules_health()
    product = bool(doctor.get("product_ready"))
    ok = product and bool(decisions.get("ok")) and bool(modules.get("ok"))
    reuse = next(
        (c for c in doctor.get("checks") or [] if c.get("name") == "reuse_cue"),
        {},
    )
    return {
        "ok": ok,
        "product_ready": product,
        "decisions_ok": bool(decisions.get("ok")),
        "modules_ok": bool(modules.get("ok")),
        "repair": {
            "doctor": [
                c["name"]
                for c in doctor.get("checks") or []
                if c.get("name") in {"freeze_autonomy", "yield_honest"} and not c.get("pass")
            ],
            "decisions": list(decisions.get("repair") or []),
            "modules": list(modules.get("repair") or []),
        },
        "reuse": reuse.get("detail"),
        "savings_percent": None,
        "version": doctor.get("version"),
        "doctor": doctor,
    }
