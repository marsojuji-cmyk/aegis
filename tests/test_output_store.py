"""Output reduce path — shrink, store, reuse."""

import pytest

from aegis.cli import main
from aegis.ledger import read_all
from aegis.output_lane import activate_output, land_output
from aegis.output_store import find_by_key, output_key, shrink_output, store_shrunk, store_stats


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_shrink_brief_strips_filler():
    raw = "Sure, happy to help!\n\nFixed the bug in auth.py.\n\nHope this helps!\n"
    shrunk = shrink_output(raw, "brief")
    assert "Sure" not in shrunk
    assert "auth.py" in shrunk
    assert "Hope this" not in shrunk


def test_shrink_diff_keeps_hunks():
    raw = (
        "Here is the patch:\n"
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-old\n"
        "+new\n"
        "\nThanks!\n"
    )
    shrunk = shrink_output(raw, "diff")
    assert "diff --git" in shrunk
    assert "+new" in shrunk
    assert "Thanks" not in shrunk


def test_shrink_json_minifies():
    raw = 'Sure.\n```json\n{ "a": 1, "b": [2, 3] }\n```\n'
    shrunk = shrink_output(raw, "json")
    assert shrunk == '{"a":1,"b":[2,3]}'


def test_store_and_reuse(aegis_tmp):
    body = "Sure, I can help.\n\nShip the feature.\n\nHope this helps!"
    r1 = store_shrunk(body=body, profile="brief", summary="first")
    assert r1["reuse"] is False
    assert r1["shrunk_tokens"] < r1["raw_tokens"]
    r2 = store_shrunk(body=body, profile="brief", summary="again")
    assert r2["reuse"] is True
    assert r2["id"] == r1["id"]
    kinds = [x["kind"] for x in read_all()]
    assert "output_store" in kinds
    assert "output_reuse" in kinds
    st = store_stats()
    assert st["entries"] >= 1
    assert st["tokens_saved"] >= 0


def test_land_with_body(aegis_tmp):
    activate_output(profile="brief", mode="explore")
    body = "Sure!\n\nDone. Updated ledger.py.\n"
    landed = land_output(body=body, summary="landed work")
    assert landed["landed"] is True
    assert landed.get("output_id")
    assert landed.get("shrunk_text")
    assert "Sure" not in (landed.get("shrunk_text") or "")


def test_cli_land_body_file(aegis_tmp, tmp_path):
    activate_output(profile="diff", mode="implement")
    f = tmp_path / "out.txt"
    f.write_text(
        "Here you go:\ndiff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n"
    )
    assert (
        main(
            [
                "land",
                "--body-file",
                str(f),
                "--summary",
                "patch",
            ]
        )
        == 0
    )
