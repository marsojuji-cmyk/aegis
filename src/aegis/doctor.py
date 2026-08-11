"""Health / migration checks for frictionless evolution."""

from __future__ import annotations

import os
import sys
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
from aegis.paths import (
    aegis_home,
    fund_path,
    ideas_path,
    ledger_path,
    packs_dir,
)


Check = Tuple[str, bool, str]


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

    exp = expense_report_path()
    checks.append(
        (
            "legacy_expense_report",
            os.path.isfile(exp),
            exp if os.path.isfile(exp) else "none (ok if never ran demo)",
        )
    )

    sk = skill_path()
    checks.append(("skill_aegis_tokenomics", os.path.isfile(sk), sk))
    ru = rules_path()
    checks.append(("rules_aegis_tokenomics", os.path.isfile(ru), ru))

    checks.append(
        (
            "cli_entry",
            True,
            f"python -m aegis (argv0={os.path.basename(sys.argv[0])})",
        )
    )

    if engine == "legacy" and legacy_ok:
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
        checks.append(("compat_mode", legacy_ok, "see engine + legacy checks"))

    return checks


def doctor_report() -> Dict[str, Any]:
    checks = run_checks()
    failed = [c for c in checks if not c[1]]
    try:
        from aegis.compound import compound_status

        compound = compound_status()
    except Exception:
        compound = {}
    return {
        "ok": len(failed) == 0,
        "epoch": "1.1",
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
        f"  epoch:   {report['epoch']} (v1.1 Intelligence Layer)",
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
