"""Master Aegis 1.2 product OS: kernel, portable home, frozen API, yield."""

import json

import pytest

from aegis.api_contract import REQUIRED_KEYS, check_payload, spec
from aegis.cli import main
from aegis.kernel import authorize, drivers, scorecard, syscall
from aegis.pack_cache import file_hash
from aegis.portable import backup_home, init_home, restore_home, uninstall_home
from aegis.yield_proof import prove


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AEGIS_HOME", str(home))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return home


def test_init_writes_portable_manifest(aegis_tmp):
    body = init_home()
    assert body["ok"] is True
    assert body["schema"] == 2
    assert body["portable"] is True
    man = json.loads((aegis_tmp / "MANIFEST.json").read_text(encoding="utf-8"))
    assert man["portable"] is True
    assert "/Users/" not in json.dumps(man)


def test_backup_restore_roundtrip(aegis_tmp, tmp_path):
    init_home()
    (aegis_tmp / "packs" / "marker.txt").write_text("keep", encoding="utf-8")
    bak = backup_home(str(tmp_path / "bak"))
    assert bak["ok"] is True
    other = tmp_path / "restored"
    out = restore_home(bak["archive"], str(other))
    assert out["ok"] is True
    assert (other / "packs" / "marker.txt").read_text(encoding="utf-8") == "keep"


def test_uninstall_refuses_without_yes(aegis_tmp):
    init_home()
    denied = uninstall_home(yes=False)
    assert denied["ok"] is False
    assert aegis_tmp.is_dir()
    gone = uninstall_home(yes=True)
    assert gone["ok"] is True
    assert not aegis_tmp.exists()


def test_user_namespace(tmp_path, monkeypatch):
    monkeypatch.delenv("AEGIS_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AEGIS_USER", "lab-2")
    from aegis.paths import aegis_home

    home = aegis_home()
    assert home.parts[-2:] == ("users", "lab-2")


def test_kernel_syscalls_and_drivers(aegis_tmp):
    init_home()
    st = syscall("status")
    assert st["ok"] is True
    assert st["elapsed_ms"] >= 0
    assert st["result"]["host_kernel"] is False
    drv = drivers()
    assert all(d["present"] == "yes" for d in drv)
    mem = syscall("mem")
    assert "rss_bytes" in mem["result"]
    spec_body = syscall("api_spec")["result"]
    assert spec_body["stability"] == "frozen"
    assert spec_body["api_version"] == "v1"


def test_invest_syscall_frozen_on_hard_stop(aegis_tmp):
    from aegis.config import AegisConfig, save_config
    from aegis.ledger import record

    save_config(AegisConfig(weekly_token_cap=100, reserve_floor=0.80, throttle_floor=0.50))
    record(kind="pack", task="fill", mode="explore", raw_in=1000, processed_in=1000)
    auth = authorize("invest")
    assert auth["ok"] is False
    denied = syscall("invest", idea_id="nope")
    assert denied["ok"] is False


def test_api_contract_floor():
    body = spec()
    assert body["ok"] is True
    for endpoint in REQUIRED_KEYS:
        sample = {k: True for k in REQUIRED_KEYS[endpoint]}
        assert check_payload(endpoint, sample)["ok"] is True
        missing = dict(sample)
        missing.pop(next(iter(REQUIRED_KEYS[endpoint])))
        assert check_payload(endpoint, missing)["ok"] is False


def test_yield_prove_never_sets_savings_percent(aegis_tmp, tmp_path):
    src = tmp_path / "mod.py"
    src.write_text("def hello(x):\n    return x + 1\n" * 40, encoding="utf-8")
    proof = prove([str(src)])
    assert proof["ok"] is True
    assert proof["savings_percent"] is None
    assert proof["accounting"] == "counterfactual_chars4"
    assert proof["packed_tokens"] < proof["naive_tokens"]


def test_file_hash_cache_warm_path(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("abc", encoding="utf-8")
    first = file_hash(str(f))
    second = file_hash(str(f))
    assert first == second
    f.write_text("abcd", encoding="utf-8")
    third = file_hash(str(f))
    assert third != first


def test_cli_os_score_and_doctor_product(aegis_tmp):
    assert main(["os", "init", "--json"]) == 0
    assert main(["os", "score", "--json"]) == 0
    assert main(["doctor", "--product", "--json"]) == 0
    assert main(["api", "spec"]) == 0
    assert main(["kernel", "status", "--json"]) == 0
    card = scorecard()
    assert card["layers"]["kernel"]["score"] == 10
    assert card["layers"]["public_api"]["score"] == 10
    assert card["layers"]["persistence"]["score"] == 10
    assert card["layers"]["install_multiuser"]["score"] == 10
    assert card["layers"]["control_plane"]["score"] == 10
    assert card["layers"]["proven_yield"]["score"] >= 8
    assert card["layers"]["proven_yield"]["savings_percent"] is None
    assert card["composite"] >= 9.0


def test_daemon_spec_kernel_yield(aegis_tmp):
    import urllib.request

    from aegis.router_daemon import start_background

    httpd, _t = start_background("127.0.0.1", 18797)
    try:
        for path, key in (
            ("/v1/aegis/spec", "endpoints"),
            ("/v1/aegis/kernel", "kernel"),
            ("/v1/aegis/yield", "yield"),
        ):
            with urllib.request.urlopen(f"http://127.0.0.1:18797{path}", timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            assert data.get("ok") is True
            assert key in data or key in (data.get("yield") or {})
            if path.endswith("/yield"):
                assert data["yield"]["savings_percent"] is None
            if path.endswith("/spec"):
                assert check_payload("GET /v1/aegis/spec", data)["ok"] is True
            if path.endswith("/kernel"):
                assert check_payload("GET /v1/aegis/kernel", data)["ok"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()
