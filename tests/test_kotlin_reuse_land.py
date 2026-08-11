"""Kotlin slicer + mode-map reuse + output land."""

import pytest

from aegis.bento import assemble
from aegis.cli import main
from aegis.kotlin_slice import (
    build_explore_kotlin,
    build_implement_kotlin,
    extract_kotlin_units,
)
from aegis.output_lane import activate_output, count_landed, land_output
from aegis.pack_cache import get_or_none, normalize_mode, pack_key, save_pack


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


KOTLIN = """
package com.example

import kotlin.io.println

class Server(val port: Int) {
  fun handle(path: String): String {
    val result = path + ":ok"
    if (port > 0) {
      return result
    }
    return "down"
  }

  fun helper() {
    val x = 1
  }
}

fun topLevel() = 1
"""


def test_kotlin_units_and_implement():
    units = extract_kotlin_units(KOTLIN)
    names = {u["name"] for u in units}
    assert "Server" in names
    assert "handle" in names
    exp = build_explore_kotlin(KOTLIN)
    assert "handle" in exp
    assert 'val result = path + ":ok"' not in exp
    payload, meta = build_implement_kotlin(KOTLIN, targets=["handle"])
    assert meta["fidelity"] == "target_bodies"
    assert 'val result = path + ":ok"' in payload


def test_assemble_py_java_kotlin():
    result = assemble(
        core_task="multi",
        code_snippets=[
            {"path": "a.py", "content": "def foo():\n    return 1\n"},
            {
                "path": "A.java",
                "content": "public class A { public void m() { int x=1; } }",
            },
            {"path": "S.kt", "content": KOTLIN},
        ],
        mode="explore",
    )
    langs = set(result["languages"])
    assert "python" in langs and "java" in langs and "kotlin" in langs


def test_mode_aliases():
    assert normalize_mode("read") == "explore"
    assert normalize_mode("edit") == "implement"
    assert normalize_mode("pr") == "review"


def test_reuse_mode_alias_and_path_set(aegis_tmp, tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n" * 5)
    paths = [str(f)]
    k1 = pack_key("explore", paths, "a")
    k2 = pack_key("read", paths, "b")  # alias → explore
    assert k1 == k2
    # save under explore
    payload = {
        "mode": "explore",
        "total_raw_tokens": 100,
        "total_compressed_tokens": 20,
        "overall_reduction_percent": 80,
        "bento_components": [],
        "core_task": "a",
    }
    save_pack(k1, payload)
    pid, hit, meta = get_or_none("read", paths, "other task")
    assert hit is not None
    assert meta["canon_mode"] == "explore"


def test_review_fallback_to_explore(aegis_tmp, tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n" * 5)
    paths = [str(f)]
    k = pack_key("explore", paths)
    save_pack(
        k,
        {
            "mode": "explore",
            "total_raw_tokens": 50,
            "total_compressed_tokens": 10,
            "bento_components": [],
        },
    )
    pid, hit, meta = get_or_none("review", paths, "r")
    assert hit is not None
    assert meta.get("fallback_used") is True


def test_land_books_output_record(aegis_tmp):
    activate_output(profile="brief", mode="explore")
    landed = land_output(actual_tokens=200, raw_tokens=900, summary="shipped fix")
    assert landed["landed"] is True
    assert landed["tokens_saved"] == 700
    assert count_landed() >= 1
    assert main(["budget"]) == 0
