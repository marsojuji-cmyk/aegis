"""Tree-sitter optional backend for py/js/ts."""

import os

import pytest

from aegis.bento import assemble
from aegis.treesitter_backend import pack_with_treesitter, treesitter_available


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_TREE_SITTER", raising=False)
    return tmp_path / "home"


PY = '''
class Foo:
    def bar(self, x):
        y = x + 1
        return y

def top(a):
    return a
'''

JS = """
export function helper(x) {
  return x + 1;
}
export function targetFn(a, b) {
  const total = a + b;
  if (total > 10) {
    return total * 2;
  }
  return total - 1;
}
class Widget {
  render() {
    return null;
  }
}
"""

TS = """
export function helper(x: number): number {
  return x + 1;
}
export function targetFn(a: number, b: number): number {
  const total = a + b;
  if (total > 10) {
    return total * 2;
  }
  return total - 1;
}
export class Widget {
  render(): null {
    return null;
  }
}
"""


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter not installed")
def test_treesitter_python_implement():
    text, meta = pack_with_treesitter(
        "python", PY, "implement", targets=["bar"], task="fix bar"
    )
    assert meta["slicer"] == "tree-sitter"
    assert meta["fidelity"] == "target_bodies"
    assert "y = x + 1" in text
    assert "return y" in text


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter not installed")
def test_treesitter_js_explore_drops_body():
    text, meta = pack_with_treesitter("javascript", JS, "explore")
    assert meta["slicer"] == "tree-sitter"
    assert "targetFn" in text
    assert "const total = a + b" not in text


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter not installed")
def test_treesitter_ts_implement():
    text, meta = pack_with_treesitter(
        "typescript", TS, "implement", targets=["targetFn"]
    )
    assert meta["fidelity"] == "target_bodies"
    assert "const total = a + b" in text


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter not installed")
def test_assemble_reports_treesitter_slicer():
    result = assemble(
        core_task="fix",
        code_snippets=[
            {"path": "a.py", "content": PY},
            {"path": "a.ts", "content": TS},
            {"path": "a.js", "content": JS},
        ],
        mode="implement",
        targets=["bar", "targetFn"],
    )
    assert "tree-sitter" in result.get("slicers", [])


def test_disable_treesitter_env(monkeypatch):
    monkeypatch.setenv("AEGIS_TREE_SITTER", "0")
    # force re-check
    import aegis.treesitter_backend as tb

    tb._AVAILABLE = None
    assert tb.treesitter_available() is False
    assert pack_with_treesitter("python", PY, "explore") is None
    tb._AVAILABLE = None
