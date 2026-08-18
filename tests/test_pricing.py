"""Honest AGIS pricing quote."""

import pytest

from aegis.cli import main
from aegis.pricing import THEN, quote


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return tmp_path / "home"


def test_quote_is_honest_and_sellable(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    q = quote()
    assert q["ok"] is True
    assert q["savings_percent"] is None
    assert q["then"]["sellable"] is False
    assert q["now"]["sellable"] is True
    src = q["skus"]["source_nonexclusive"]["usd"]
    ex = q["skus"]["exclusive_lab_12mo"]["usd"]
    assert q["skus"]["hosted_saas"]["usd"] is None
    assert THEN["exclusive_usd"]["low"] <= ex["mid"] <= 150000
    assert src["mid"] < ex["mid"]
    assert src["low"] < src["mid"] < src["high"]
    assert q["token_demo"]["savings_percent"] is None
    assert q["value_delta"]["sellable_now"] is True


def test_cli_price_quote(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    assert main(["price", "quote"]) == 0
    assert main(["price", "quote", "--json"]) == 0
