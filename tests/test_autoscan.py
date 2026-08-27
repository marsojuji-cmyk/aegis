import json
import urllib.request
from pathlib import Path

import pytest

from aegis import autoscan, evidence_yield


@pytest.fixture()
def autoscan_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path


def test_local_allowlist_incremental_scan_and_secret_exclusion(autoscan_home):
    approved = autoscan_home / "approved"
    approved.mkdir()
    (approved / "note.md").write_text("plain observation", encoding="utf-8")
    (approved / ".env").write_text("TOKEN=never", encoding="utf-8")
    source = autoscan.approve_source("local", str(approved))
    assert source["source_key"].startswith("local:")
    first = autoscan.scan_once()
    second = autoscan.scan_once()
    assert first["scanned"] == 1
    assert first["quarantine_applied"] is False
    assert second["unchanged"] == 1
    records = [row for row in autoscan.load_events() if row.get("event") == "scan_record"]
    assert len(records) == 1
    assert records[0]["verification_state"] == "review_required_unstructured"
    assert "never" not in json.dumps(records)


def test_public_scan_and_quarantine_are_calibration_gated(autoscan_home, monkeypatch):
    autoscan.approve_source("public", "https://example.com/evidence.json")
    called = {"fetch": False}

    def fake_fetch(*_args, **_kwargs):
        called["fetch"] = True
        return b"{}"

    monkeypatch.setattr(autoscan, "_fetch_public", fake_fetch)
    result = autoscan.scan_once()
    assert result["public_blocked"] == "calibration_gate_closed"
    assert called["fetch"] is False
    with pytest.raises(ValueError, match="20-case"):
        autoscan.enable_quarantine()


def test_quarantine_restore_and_source_reenable_are_auditable(autoscan_home):
    governed = evidence_yield.govern_claim(
        candidate_id="q1", claim="claim", evidence=[{"bad": True}], impact="low"
    )
    assert governed["quarantined_evidence"] == 1
    projection = evidence_yield.operational_projection()
    assert projection["evidence_health"]["quarantined"] == 1
    quarantine_id = next(
        row["id"] for row in evidence_yield.load_events()
        if row.get("event") == "evidence_quarantined"
    )
    restored = evidence_yield.restore_quarantined_evidence(quarantine_id)
    assert restored["quarantine_id"] == quarantine_id
    assert evidence_yield.operational_projection()["evidence_health"]["quarantined"] == 0
    override = evidence_yield.reenable_source("example.com")
    assert override["domain"] == "example.com"


def test_control_never_authorizes_outbound_action(autoscan_home):
    result = autoscan.control("resume")
    assert result["outbound_action_authorized"] is False
    assert autoscan.status()["state"] == "active"


def test_passing_calibration_groups_independent_evidence_but_blocks_consequential_claims(autoscan_home):
    approved = autoscan_home / "approved"
    approved.mkdir()
    for idx in range(20):
        evidence_yield.record_calibration_pair(
            case_id=str(idx), expected="accept", governed="accept",
            baseline_review_minutes=2, governed_review_minutes=1,
        )
    autoscan.enable_quarantine()
    for name, url in (("one", "https://one.example/a"), ("two", "https://two.example/b")):
        (approved / f"{name}.json").write_text(json.dumps({
            "claim": "Team adopted AI", "observed_at": "2026-08-24",
            "stance": "supports", "url": url,
        }), encoding="utf-8")
    autoscan.approve_source("local", str(approved))
    result = autoscan.scan_once()
    assert result["governed_groups"] == 1
    decision = next(
        row["decision"] for row in reversed(evidence_yield.load_events())
        if row.get("event") == "claim_decision"
    )
    assert decision["decision"] == "auto_accept_internal"
    assert decision["external_action_authorized"] is False
    assert autoscan._claim_impact("Spend money on a contract") == "high"


def test_http_control_contract_keeps_outbound_blocked(autoscan_home):
    from aegis.router_daemon import start_background

    httpd, _thread = start_background("127.0.0.1", 18801)
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:18801/v1/aegis/autoscan/control",
            data=json.dumps({"action": "resume"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert body["ok"] is True
        assert body["outbound_action_authorized"] is False
        assert body["version"] == "1.3.1"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_source_circuit_is_derived_only_from_verified_outcomes(autoscan_home):
    for idx in range(5):
        evidence_yield.record_verified_outcome(
            candidate_id=f"bad-{idx}", domain="bad.example", verified=False,
            accepted=False, review_minutes=1,
        )
    assert "bad.example" in autoscan._paused_public_domains()
    evidence_yield.reenable_source("bad.example")
    assert "bad.example" not in autoscan._paused_public_domains()


def test_bundled_twenty_case_calibration_is_correct_but_cannot_unlock_live_research(autoscan_home):
    bundle = Path(__file__).parents[1] / "calibration" / "inbox" / "cases.json"
    result = autoscan.run_calibration_bundle(str(bundle))
    assert result["ok"] is True
    assert result["cases"] == 20
    assert result["matches"] == 20
    assert result["review_time_measured"] is False
    report = evidence_yield.calibration_report()
    assert report["synthetic_fixture_pairs"] == 20
    assert report["matched_human_pairs"] == 0
    assert report["operator_may_consider_live_calibration"] is False
    assert "matched human" in report["decision"]
