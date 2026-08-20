"""Path A four-beat demo and 14-day operator-owner clock.

Local only. Does not scrape Artificial Analysis, email buyers, or authorize routing.
`savings_percent` stays null.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aegis.paths import close_clock_path, ensure_home

CLOCK_DAYS = 14
AA_AS_OF = "2026-08-18"
AA_INDEX_VERSION = "4.1.1"

# Frozen snapshot from AA model pages on AA_AS_OF. Not live. Not a SKU.
AA_MODELS: List[Dict[str, Any]] = [
    {"model": "Claude Opus 5 (max)", "index": 63, "role": "frontier IQ — not the SKU"},
    {"model": "Grok 4.6 (high)", "index": 61, "role": "this-host Cursor — not a billed pair"},
    {"model": "DeepSeek V4 Pro (max)", "index": 53, "role": "implement baseline"},
    {"model": "MiMo-V2.5-Pro", "index": 43, "role": "health-run default — not admitted"},
    {"model": "GPT-5.4 nano (xhigh)", "index": 40, "role": "tiny-chat only"},
]

BILLED_IMPLEMENT: Dict[str, Any] = {
    "decision": "D-039",
    "pro_usd": 0.00005,
    "nano_usd": 0.00085,
    "note": "Mean implement pack ~13k tok, 5 pairs, same Nous bill. Routing off.",
}

SPOKEN = [
    "Beat 1. os ready. This is a local control plane, not a hosted SKU.",
    "Beat 2. Pack the same files twice. Second call is a covering hit if bytes did not change.",
    "Beat 3. price quote. Source mid is the close. Token dollars are a demo. savings_percent is null.",
    "Beat 4. We do not compete with Opus at 63. AA ranks models. Aegis 9.7 is the OS. Nano is 40 and also ~17x more expensive on packed implement. Routing stays off.",
]


def _today() -> date:
    return date.today()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load() -> Optional[Dict[str, Any]]:
    path = close_clock_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _save(body: Dict[str, Any]) -> Dict[str, Any]:
    ensure_home()
    path = close_clock_path()
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return body


def _deadline_date(started_iso: str) -> date:
    started = date.fromisoformat(str(started_iso)[:10])
    return started + timedelta(days=CLOCK_DAYS)


def start_clock(*, reset: bool = False) -> Dict[str, Any]:
    """Start a 14-day clock. Refuses to reset unless reset=True."""
    existing = _load()
    if existing and not reset:
        return {**status(), "created": False, "ok": True}
    started = _today().isoformat()
    body = {
        "ok": True,
        "created": True,
        "started": started,
        "deadline": _deadline_date(started).isoformat(),
        "days": CLOCK_DAYS,
        "buyer_name": None,
        "buyer_named_at": None,
        "last_rehearsal": None,
        "last_covering_hit": None,
        "savings_percent": None,
        "routing_authorized": False,
    }
    _save(body)
    return {**status(), "created": True}


def name_buyer(name: str) -> Dict[str, Any]:
    """Record one operator-owner. Does not contact them."""
    label = " ".join(str(name or "").split()).strip()
    if not label or len(label) > 120:
        return {"ok": False, "error": "buyer name required (1–120 chars)", "savings_percent": None}
    clock = _load()
    if not clock:
        start_clock()
        clock = _load() or {}
    clock["buyer_name"] = label
    clock["buyer_named_at"] = _now_iso()
    clock["savings_percent"] = None
    clock["routing_authorized"] = False
    _save(clock)
    return status()


def status() -> Dict[str, Any]:
    clock = _load()
    if not clock:
        return {
            "ok": False,
            "running": False,
            "error": "clock not started — aegis demo start",
            "days_left": None,
            "buyer_named": False,
            "overdue": False,
            "savings_percent": None,
            "routing_authorized": False,
            "cue": f"0 9 * * * python3 -m aegis demo status",
        }
    today = _today()
    deadline = date.fromisoformat(str(clock["deadline"])[:10])
    days_left = (deadline - today).days
    buyer = str(clock.get("buyer_name") or "").strip()
    overdue = days_left < 0 and not buyer
    return {
        "ok": not overdue,
        "running": True,
        "started": clock.get("started"),
        "deadline": clock.get("deadline"),
        "days": CLOCK_DAYS,
        "days_left": days_left,
        "buyer_name": buyer or None,
        "buyer_named": bool(buyer),
        "buyer_named_at": clock.get("buyer_named_at"),
        "last_rehearsal": clock.get("last_rehearsal"),
        "last_covering_hit": clock.get("last_covering_hit"),
        "overdue": overdue,
        "savings_percent": None,
        "routing_authorized": False,
        "cue": (
            f"Cron: 0 9 * * * python3 -m aegis demo status"
            if buyer
            else 'Name one operator-owner, then aegis demo buyer "Name". Cron: 0 9 * * * python3 -m aegis demo status'
        ),
    }


def _record_rehearsal(*, covering_hit: Optional[bool]) -> None:
    clock = _load()
    if not clock:
        start_clock()
        clock = _load() or {}
    clock["last_rehearsal"] = _now_iso()
    clock["last_covering_hit"] = covering_hit
    clock["savings_percent"] = None
    clock["routing_authorized"] = False
    _save(clock)


def pack_twice(paths: Sequence[str]) -> Dict[str, Any]:
    from aegis.yield_proof import prove

    files = [str(Path(p).expanduser().resolve()) for p in paths if Path(p).is_file()]
    if not files:
        return {"ok": False, "error": "no readable files", "savings_percent": None, "covering_hit": False}
    first = prove(files, task="path-a-demo")
    second = prove(files, task="path-a-demo")
    hit = bool(second.get("reuse"))
    return {
        "ok": bool(first.get("ok")) and bool(second.get("ok")),
        "paths": files,
        "first": {
            "reuse": bool(first.get("reuse")),
            "pack_id": first.get("pack_id"),
            "packed_tokens": first.get("packed_tokens"),
            "naive_tokens": first.get("naive_tokens"),
        },
        "second": {
            "reuse": bool(second.get("reuse")),
            "pack_id": second.get("pack_id"),
            "packed_tokens": second.get("packed_tokens"),
        },
        "covering_hit": hit,
        "savings_percent": None,
        "note": "Second pack is a covering hit only when hashes still match.",
    }


def honesty() -> Dict[str, Any]:
    from aegis.yield_proof import yield_report

    yld = yield_report()
    billed = dict(yld.get("billed_pairs") or {})
    return {
        "aa_index_version": AA_INDEX_VERSION,
        "aa_as_of": AA_AS_OF,
        "aa_models": list(AA_MODELS),
        "billed_implement": dict(BILLED_IMPLEMENT),
        "live_yield": {
            "ledger_tokens_saved_local": yld.get("ledger_tokens_saved_local"),
            "ledger_tokens_consumed": yld.get("ledger_tokens_consumed"),
            "ledger_reduction_percent_local": yld.get("ledger_reduction_percent_local"),
            "reuse_hit_rate": yld.get("reuse_hit_rate"),
            "billed_pairs": billed,
        },
        "agree": "Do not route implement work to nano. AA 40 vs Pro 53. Billed implement nano ~17x Pro.",
        "disagree": "AA list cost-per-task can make nano look cheaper. This stack's receipts say the opposite.",
        "forbidden": [
            "sell 9.7 vs 63",
            "savings_percent from AA",
            "turn routing on from ranks",
            "hosted SKU",
        ],
        "savings_percent": None,
        "routing_authorized": False,
        "source": "artificialanalysis.ai model pages (frozen) + live ledger + matched_provider_pairs",
    }


def spoken_script() -> Dict[str, Any]:
    return {
        "ok": True,
        "beats": list(SPOKEN),
        "savings_percent": None,
        "routing_authorized": False,
    }


def run(paths: Sequence[str], *, skip_pack: bool = False) -> Dict[str, Any]:
    """Rehearse beats 1–4. Starts the 14-day clock if missing."""
    from aegis.doctor import release_report
    from aegis.pricing import quote
    from aegis.yield_proof import yield_report

    if not _load():
        start_clock()
    ready = release_report()
    packed: Dict[str, Any]
    if skip_pack:
        packed = {
            "ok": True,
            "skipped": True,
            "covering_hit": None,
            "savings_percent": None,
            "note": "pack skipped — pass files without --skip-pack for beat 2",
        }
    else:
        packed = pack_twice(paths)
    price = quote()
    yield_body = yield_report()
    covering = packed.get("covering_hit")
    _record_rehearsal(covering_hit=covering if covering is not None else None)
    src = ((price.get("skus") or {}).get("source_nonexclusive") or {}).get("usd") or {}
    close_ok = bool(ready.get("product_ready")) and (skip_pack or bool(packed.get("ok")))
    return {
        "ok": close_ok,
        "savings_percent": None,
        "routing_authorized": False,
        "clock": status(),
        "beat1_ready": {
            "ok": ready.get("ok"),
            "product_ready": ready.get("product_ready"),
            "decisions_ok": ready.get("decisions_ok"),
            "modules_ok": ready.get("modules_ok"),
            "version": ready.get("version"),
            "reuse": ready.get("reuse"),
            "repair": ready.get("repair"),
        },
        "beat2_pack": packed,
        "beat3_price": {
            "source_mid_usd": src.get("mid"),
            "exclusive_mid_usd": ((price.get("skus") or {}).get("exclusive_lab_12mo") or {}).get("usd", {}).get("mid"),
            "composite": (price.get("now") or {}).get("composite"),
            "advice": (price.get("now") or {}).get("advice"),
            "hosted": None,
        },
        "beat4_honesty": honesty(),
        "yield": {
            "accounting": yield_body.get("accounting"),
            "savings_percent": None,
            "admitted_pair": yield_body.get("admitted_pair"),
            "ledger_tokens_saved_local": yield_body.get("ledger_tokens_saved_local"),
            "ledger_tokens_consumed": yield_body.get("ledger_tokens_consumed"),
            "ledger_reduction_percent_local": yield_body.get("ledger_reduction_percent_local"),
            "reuse_hit_rate": yield_body.get("reuse_hit_rate"),
            "billed_pairs": yield_body.get("billed_pairs"),
        },
        "spoken": list(SPOKEN),
    }


def format_run(body: Dict[str, Any]) -> str:
    clock = body.get("clock") or {}
    b1 = body.get("beat1_ready") or {}
    b2 = body.get("beat2_pack") or {}
    b3 = body.get("beat3_price") or {}
    lines = [
        f"Aegis demo  Path A  ok={body.get('ok')}  savings_percent=null  routing=off",
        f"  clock  days_left={clock.get('days_left')}  deadline={clock.get('deadline')}  "
        f"buyer={clock.get('buyer_name') or 'UNNAMED'}",
        f"  beat1  os ready ok={b1.get('ok')}  product_ready={b1.get('product_ready')}  v{b1.get('version')}",
    ]
    if b2.get("skipped"):
        lines.append("  beat2  pack skipped")
    else:
        lines.append(
            f"  beat2  covering_hit={b2.get('covering_hit')}  "
            f"first_reuse={((b2.get('first') or {}).get('reuse'))}  "
            f"second_reuse={((b2.get('second') or {}).get('reuse'))}"
        )
    yld = body.get("yield") or {}
    billed = yld.get("billed_pairs") or {}
    usd = billed.get("total_cost_usd_saved")
    usd_s = "none" if usd is None else f"{usd}"
    lines.append(
        f"  beat3  source mid ${b3.get('source_mid_usd')}  exclusive mid ${b3.get('exclusive_mid_usd')}  "
        f"hosted=not offered"
    )
    lines.append(
        f"  beat4  AA Pro 53 > nano 40  ledger_saved={yld.get('ledger_tokens_saved_local')} tok  "
        f"reduction={yld.get('ledger_reduction_percent_local')}%  "
        f"billed_pairs={billed.get('paired_tasks')}  Δ${usd_s}  savings_percent=null"
    )
    lines.append("  say:")
    for beat in body.get("spoken") or SPOKEN:
        lines.append(f"    {beat}")
    if not clock.get("buyer_named"):
        lines.append('  next  aegis demo buyer "One operator-owner name"')
    return "\n".join(lines)


def format_status(body: Dict[str, Any]) -> str:
    if not body.get("running"):
        return "Aegis demo  clock not started.  python3 -m aegis demo start"
    buyer = body.get("buyer_name") or "UNNAMED"
    flag = "overdue" if body.get("overdue") else "open"
    return (
        f"Aegis demo  {flag}  days_left={body.get('days_left')}  "
        f"deadline={body.get('deadline')}  buyer={buyer}\n"
        f"  last_rehearsal={body.get('last_rehearsal') or 'none'}  "
        f"covering_hit={body.get('last_covering_hit')}\n"
        f"  {body.get('cue')}"
    )
