"""Bounded, allowlist-only autoscan for local and public evidence sources."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from aegis.config import load_config
from aegis.evidence_yield import (
    calibration_report,
    govern_claim,
    operational_projection,
    record_calibration_pair,
    reenable_source,
    restore_quarantined_evidence,
)
from aegis.grokbots import validate_claim
from aegis.paths import aegis_home, ensure_home

_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_RUNTIME: Dict[str, Any] = {"running": False, "next_scan_at": "", "last_error": ""}
_LOCAL_SUFFIXES = {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".html"}
_SECRET_PARTS = {
    ".env", "credentials", "credential", "secret", "secrets", "keychain",
    "private_key", "id_rsa", "id_ed25519", ".ssh",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def autoscan_path() -> Path:
    ensure_home()
    return aegis_home() / "autoscan.jsonl"


def _append(event: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(event)
    row.setdefault("id", str(uuid.uuid4()))
    row.setdefault("recorded_at", _now())
    with _LOCK:
        with autoscan_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def load_events() -> List[Dict[str, Any]]:
    path = autoscan_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with _LOCK:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _source_key(kind: str, source: str) -> str:
    return f"{kind}:{source}"


def _active_sources(rows: Optional[Iterable[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    states: Dict[str, Dict[str, Any]] = {}
    for row in rows if rows is not None else load_events():
        if row.get("event") not in {"source_approved", "source_removed"}:
            continue
        key = str(row.get("source_key") or "")
        if not key:
            continue
        if row["event"] == "source_removed":
            states.pop(key, None)
        else:
            states[key] = {
                "source_key": key,
                "kind": row.get("kind"),
                "source": row.get("source"),
                "approved_at": row.get("recorded_at"),
            }
    return sorted(states.values(), key=lambda row: row["source_key"])


def _safe_local_source(raw: str) -> Path:
    path = Path(str(raw or "")).expanduser().resolve()
    if not path.exists():
        raise ValueError("approved local source must exist")
    if path == Path("/") or path == Path.home().resolve():
        raise ValueError("broad filesystem or home-directory approval is forbidden")
    lowered = {part.lower() for part in path.parts}
    if lowered & _SECRET_PARTS:
        raise ValueError("credential or secret paths cannot be approved")
    return path


def _safe_public_source(raw: str) -> str:
    parsed = urlparse(str(raw or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("public sources require a credential-free https URL")
    return parsed.geturl()


def approve_source(kind: str, source: str) -> Dict[str, Any]:
    kind = str(kind or "").strip().lower()
    if kind == "local":
        normalized = str(_safe_local_source(source))
    elif kind == "public":
        normalized = _safe_public_source(source)
    else:
        raise ValueError("kind must be local or public")
    key = _source_key(kind, normalized)
    return _append({"event": "source_approved", "source_key": key, "kind": kind, "source": normalized})


def remove_source(source_key: str) -> Dict[str, Any]:
    key = str(source_key or "").strip()
    if key not in {row["source_key"] for row in _active_sources()}:
        raise ValueError("source is not approved")
    return _append({"event": "source_removed", "source_key": key})


def set_paused(paused: bool, *, reason: str = "operator") -> Dict[str, Any]:
    return _append({"event": "scanner_paused" if paused else "scanner_resumed", "reason": reason})


def _paused(rows: List[Dict[str, Any]]) -> bool:
    state = True
    for row in rows:
        if row.get("event") == "scanner_paused":
            state = True
        elif row.get("event") == "scanner_resumed":
            state = False
    return state


def enable_quarantine() -> Dict[str, Any]:
    report = calibration_report()
    if not report["operator_may_consider_live_calibration"]:
        raise ValueError("quarantine automation requires a passing 20-case calibration")
    return _append({"event": "quarantine_enabled", "calibration_pairs": report["pairs"]})


def _quarantine_enabled(rows: List[Dict[str, Any]]) -> bool:
    enabled = False
    for row in rows:
        if row.get("event") == "quarantine_enabled":
            enabled = True
        elif row.get("event") == "quarantine_disabled":
            enabled = False
    return enabled and calibration_report()["operator_may_consider_live_calibration"]


def _fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _previous_fingerprints(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for row in rows:
        if row.get("event") == "scan_record" and row.get("item") and row.get("fingerprint"):
            found[str(row["item"])] = str(row["fingerprint"])
    return found


def _structured_evidence(data: bytes, source_url: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    claim = str(payload.get("claim") or "").strip()
    observed_at = str(payload.get("observed_at") or "").strip()
    stance = str(payload.get("stance") or "").strip().lower()
    url = str(payload.get("url") or source_url).strip()
    if not claim or not observed_at or stance not in {"supports", "contradicts"}:
        return None
    return {"claim": claim, "observed_at": observed_at, "stance": stance, "url": url}


def _record_item(*, source: Dict[str, Any], item: str, data: bytes,
                 previous: Dict[str, str], apply_quarantine: bool,
                 scan_reason: str) -> Dict[str, Any]:
    digest = _fingerprint(data)
    if previous.get(item) == digest:
        return {"state": "unchanged", "item": item}
    evidence = _structured_evidence(data, item)
    verification_state = (
        "pending_governance" if evidence and apply_quarantine
        else "observed_dry_run" if evidence
        else "review_required_unstructured"
    )
    recorded = _append({
        "event": "scan_record",
        "source_key": source["source_key"],
        "kind": source["kind"],
        "source": source["source"],
        "item": item,
        "fingerprint": digest,
        "bytes": len(data),
        "scan_reason": scan_reason,
        "freshness": "observed_now",
        "verification_state": verification_state,
        "decision_id": "",
        "provider": "",
        "model": "",
        "request_id": "",
        "observed_cost_usd": 0.0,
        "cost_status": "no_provider_request",
        "outbound_action_authorized": False,
    })
    result = {"state": "scanned", **recorded}
    if evidence:
        result["normalized_evidence"] = evidence
    return result


def _claim_impact(claim: str) -> str:
    consequential = {
        "money", "payment", "spend", "purchase", "permission", "legal",
        "contract", "health", "medical", "publish", "delete", "contact",
        "message", "email", "submit",
    }
    words = {word.strip(".,:;!?()[]{}\"").lower() for word in claim.split()}
    return "high" if words & consequential else "low"


def _public_due(source_key: str, rows: List[Dict[str, Any]], interval: int) -> bool:
    last = next(
        (
            row.get("recorded_at") for row in reversed(rows)
            if row.get("event") == "scan_record" and row.get("source_key") == source_key
        ),
        "",
    )
    if not last:
        return True
    try:
        observed = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - observed >= timedelta(seconds=max(60, interval))


def _today_observed_cost(rows: List[Dict[str, Any]]) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(
        float(row.get("observed_cost_usd") or 0)
        for row in rows
        if row.get("event") == "scan_record"
        and str(row.get("recorded_at") or "").startswith(today)
    )


def _paused_public_domains() -> set[str]:
    return {
        str(row.get("domain") or "").lower()
        for row in operational_projection().get("paused_circuits") or []
        if row.get("domain")
    }


def run_calibration_bundle(path: str) -> Dict[str, Any]:
    bundle_path = Path(str(path or "")).expanduser().resolve()
    if not bundle_path.is_file() or bundle_path.suffix.lower() != ".json":
        raise ValueError("calibration bundle must be an existing JSON file")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("measurement_class") != "synthetic_fixture":
        raise ValueError("calibration bundle must be explicitly marked synthetic_fixture")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 20:
        raise ValueError("calibration bundle must contain exactly 20 cases")
    seen = set()
    results = []
    current_date = datetime.now(timezone.utc).date().isoformat()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each calibration case must be an object")
        case_id = str(case.get("case_id") or "").strip()
        expected = str(case.get("expected") or "").strip()
        if not case_id or case_id in seen or expected not in {"accept", "review"}:
            raise ValueError("case IDs must be unique and expected must be accept or review")
        seen.add(case_id)
        evidence = []
        for item in case.get("evidence") or []:
            if not isinstance(item, dict):
                evidence.append(item)
                continue
            normalized = dict(item)
            if normalized.get("observed_at") == "CURRENT":
                normalized["observed_at"] = current_date
            evidence.append(normalized)
        decision = validate_claim(
            str(case.get("claim") or ""), evidence,
            impact=str(case.get("impact") or "low"),
        )
        governed = "accept" if decision["decision"] == "auto_accept_internal" else "review"
        record_calibration_pair(
            case_id=case_id, expected=expected, governed=governed,
            baseline_review_minutes=0, governed_review_minutes=0,
            measurement_class="synthetic_fixture",
        )
        results.append({
            "case_id": case_id, "expected": expected, "governed": governed,
            "match": expected == governed, "reasons": decision["reasons"],
        })
    return {
        "ok": all(row["match"] for row in results),
        "measurement_class": "synthetic_fixture",
        "cases": len(results),
        "matches": sum(row["match"] for row in results),
        "mismatches": [row for row in results if not row["match"]],
        "review_time_measured": False,
        "live_research_authorized": False,
        "outbound_action_authorized": False,
    }


def _local_items(source: Dict[str, Any], max_bytes: int) -> Iterable[tuple[str, bytes]]:
    root = _safe_local_source(str(source["source"]))
    paths = [root] if root.is_file() else sorted(root.rglob("*"))
    for path in paths:
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in _LOCAL_SUFFIXES:
            continue
        if any(part.lower() in _SECRET_PARTS or part.startswith(".") for part in path.parts):
            continue
        try:
            size = path.stat().st_size
            if size > max_bytes:
                _append({"event": "scan_failure", "source_key": source["source_key"], "item": str(path), "reason": "file_too_large"})
                continue
            yield str(path), path.read_bytes()
        except OSError as exc:
            _append({"event": "scan_failure", "source_key": source["source_key"], "item": str(path), "reason": str(exc)})


class _SameHostRedirect(HTTPRedirectHandler):
    def __init__(self, host: str) -> None:
        self.host = host

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> Any:
        if (urlparse(newurl).hostname or "").lower() != self.host:
            raise ValueError("cross-host redirects are forbidden")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_public(source: Dict[str, Any], max_bytes: int) -> bytes:
    url = _safe_public_source(str(source["source"]))
    host = (urlparse(url).hostname or "").lower()
    opener = build_opener(_SameHostRedirect(host))
    request = Request(url, headers={"User-Agent": "AEGIS-Autoscan/1.3.1"})
    with opener.open(request, timeout=10) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("public response exceeds size ceiling")
    return data


def scan_once(*, reason: str = "operator", include_public: bool = True) -> Dict[str, Any]:
    rows = load_events()
    if _paused(rows) and reason != "operator":
        return {"ok": False, "state": "paused", "scanned": 0, "unchanged": 0, "failures": 0}
    cfg = load_config()
    max_bytes = max(1024, int(getattr(cfg, "autoscan_max_item_bytes", 1_000_000)))
    previous = _previous_fingerprints(rows)
    apply_quarantine = _quarantine_enabled(rows)
    calibration = calibration_report()
    scanned = unchanged = failures = 0
    public_blocked = ""
    governed_groups = 0
    pending: Dict[str, List[Dict[str, Any]]] = {}
    daily_ceiling = float(getattr(cfg, "autoscan_daily_cost_ceiling_usd", 0.0))
    paused_domains = _paused_public_domains()
    for source in _active_sources(rows):
        try:
            if source["kind"] == "local":
                items = _local_items(source, max_bytes)
            elif not include_public:
                continue
            elif not calibration["operator_may_consider_live_calibration"]:
                public_blocked = "calibration_gate_closed"
                continue
            elif daily_ceiling <= 0 or _today_observed_cost(rows) >= daily_ceiling:
                public_blocked = "daily_cost_ceiling_closed"
                continue
            elif (urlparse(str(source["source"])).hostname or "").lower() in paused_domains:
                public_blocked = "source_circuit_paused"
                _append({
                    "event": "source_circuit_blocked",
                    "source_key": source["source_key"],
                    "reason": "verified_outcome_circuit",
                })
                continue
            elif reason == "scheduled" and not _public_due(
                source["source_key"], rows,
                int(getattr(cfg, "autoscan_public_interval_seconds", 86400)),
            ):
                continue
            else:
                items = [(str(source["source"]), _fetch_public(source, max_bytes))]
            for item, data in items:
                result = _record_item(
                    source=source, item=item, data=data, previous=previous,
                    apply_quarantine=apply_quarantine, scan_reason=reason,
                )
                if result["state"] == "unchanged":
                    unchanged += 1
                else:
                    scanned += 1
                    previous[item] = str(result["fingerprint"])
                    evidence = result.get("normalized_evidence")
                    if apply_quarantine and isinstance(evidence, dict):
                        pending.setdefault(str(evidence["claim"]), []).append(evidence)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            _append({"event": "scan_failure", "source_key": source["source_key"], "reason": str(exc)})
    for claim, evidence_rows in pending.items():
        claim_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()[:16]
        governed = govern_claim(
            candidate_id=f"autoscan:{claim_hash}", claim=claim,
            evidence=evidence_rows, impact=_claim_impact(claim),
            active_outcome="bounded_autoscan",
        )
        _append({
            "event": "scan_verification",
            "claim_fingerprint": claim_hash,
            "decision_id": governed["decision_id"],
            "verification_state": governed["decision"]["decision"],
            "evidence_count": len(evidence_rows),
            "outbound_action_authorized": False,
        })
        governed_groups += 1
    completed = _append({
        "event": "scan_completed", "scan_reason": reason, "scanned": scanned,
        "unchanged": unchanged, "failures": failures,
        "public_blocked": public_blocked,
        "quarantine_applied": apply_quarantine,
        "governed_groups": governed_groups,
    })
    return {"ok": failures == 0, **{k: completed[k] for k in ("scanned", "unchanged", "failures", "public_blocked", "quarantine_applied", "governed_groups")}}


def status() -> Dict[str, Any]:
    rows = load_events()
    completed = [row for row in rows if row.get("event") == "scan_completed"]
    failures = [row for row in rows if row.get("event") == "scan_failure"]
    records = [row for row in rows if row.get("event") == "scan_record"]
    return {
        "ok": True,
        "state": "paused" if _paused(rows) else "active",
        "scheduler_running": bool(_RUNTIME["running"]),
        "last_successful_scan": next((row.get("recorded_at") for row in reversed(completed) if not row.get("failures")), ""),
        "next_scheduled_scan": _RUNTIME["next_scan_at"],
        "approved_sources": _active_sources(rows),
        "failures": len(failures),
        "last_failure": failures[-1] if failures else None,
        "scan_records": len(records),
        "observed_cost_usd": round(sum(float(row.get("observed_cost_usd") or 0) for row in records), 6),
        "daily_cost_ceiling_usd": float(getattr(load_config(), "autoscan_daily_cost_ceiling_usd", 0.0)),
        "quarantine_enabled": _quarantine_enabled(rows),
        "calibration": calibration_report(),
        "outbound_action_authorized": False,
    }


def control(action: str, **payload: Any) -> Dict[str, Any]:
    action = str(action or "").strip().lower()
    if action == "pause":
        event = set_paused(True, reason=str(payload.get("reason") or "operator"))
    elif action == "resume":
        event = set_paused(False, reason=str(payload.get("reason") or "operator"))
    elif action == "approve_source":
        event = approve_source(str(payload.get("kind") or ""), str(payload.get("source") or ""))
    elif action == "remove_source":
        event = remove_source(str(payload.get("source_key") or ""))
    elif action == "scan_once":
        return {"action": action, "result": scan_once(reason="operator", include_public=bool(payload.get("include_public", True))), "outbound_action_authorized": False}
    elif action == "run_calibration":
        return {"action": action, "result": run_calibration_bundle(str(payload.get("path") or "")), "outbound_action_authorized": False}
    elif action == "enable_quarantine":
        event = enable_quarantine()
    elif action == "disable_quarantine":
        event = _append({"event": "quarantine_disabled", "reason": "operator"})
    elif action == "restore_quarantine":
        event = restore_quarantined_evidence(str(payload.get("quarantine_id") or ""))
    elif action == "reenable_source":
        event = reenable_source(str(payload.get("domain") or ""))
    else:
        raise ValueError("unsupported autoscan control action")
    return {"action": action, "event": event, "outbound_action_authorized": False}


def start_background_autoscan() -> Dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return {"ok": True, "message": "autoscan scheduler already running"}
        _STOP.clear()

        def _loop() -> None:
            _RUNTIME["running"] = True
            while not _STOP.is_set():
                cfg = load_config()
                interval = max(60, int(getattr(cfg, "autoscan_interval_seconds", 300)))
                _RUNTIME["next_scan_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=interval)
                ).replace(microsecond=0).isoformat()
                if _STOP.wait(interval):
                    break
                try:
                    scan_once(reason="scheduled")
                    _RUNTIME["last_error"] = ""
                except Exception as exc:  # noqa: BLE001
                    _RUNTIME["last_error"] = str(exc)
            _RUNTIME["running"] = False

        _THREAD = threading.Thread(target=_loop, name="aegis-autoscan", daemon=True)
        _THREAD.start()
    return {"ok": True, "message": "autoscan scheduler running"}


def stop_background_autoscan() -> Dict[str, Any]:
    _STOP.set()
    return {"ok": True}
