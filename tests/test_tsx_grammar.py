"""TSX grammar — validate React fixture, pack .tsx, fallbacks."""

import pytest

from aegis.bento import assemble
from aegis.lang import detect_lang
from aegis.treesitter_backend import (
    pack_with_treesitter,
    treesitter_available,
    tsx_status,
    validate_tsx_grammar,
)

REACT = """
import React from "react";

export function App(props: { title: string }): JSX.Element {
  return (
    <div className="app">
      <h1>{props.title}</h1>
    </div>
  );
}

export function Helper() {
  const x = 1;
  return <span>{x}</span>;
}
"""


@pytest.fixture(autouse=True)
def _reset_tsx_cache(monkeypatch):
    import aegis.treesitter_backend as tb

    monkeypatch.delenv("AEGIS_TSX", raising=False)
    tb._TSX_VALIDATED = None
    tb._TSX_VALIDATION_DETAIL = {}
    tb._AVAILABLE = None
    yield
    tb._TSX_VALIDATED = None
    tb._AVAILABLE = None


def test_detect_tsx_extension():
    assert detect_lang("App.tsx") == "tsx"
    assert detect_lang("app.ts") == "typescript"


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter missing")
def test_validate_tsx_react_fixture():
    assert validate_tsx_grammar() is True
    st = tsx_status()
    assert st["validated"] is True
    assert st["detail"].get("ok") is True


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter missing")
def test_tsx_explore_and_implement():
    exp, meta = pack_with_treesitter("tsx", REACT, "explore")
    assert meta is not None
    assert meta.get("grammar") == "tsx"
    assert "App" in exp
    # body expression should not appear in explore sigs
    assert "className" not in exp or "function App" in exp
    impl, meta2 = pack_with_treesitter(
        "tsx", REACT, "implement", targets=["App"]
    )
    assert meta2["fidelity"] == "target_bodies"
    assert "className" in impl
    assert "props.title" in impl


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter missing")
def test_tsx_disabled_falls_back_to_typescript(monkeypatch):
    monkeypatch.setenv("AEGIS_TSX", "0")
    import aegis.treesitter_backend as tb

    tb._TSX_VALIDATED = None
    text, meta = pack_with_treesitter("tsx", REACT, "explore")
    assert text is not None
    assert meta.get("fallback") == "typescript" or meta.get("grammar") in (
        "typescript_fallback",
        "typescript",
    )


@pytest.mark.skipif(not treesitter_available(), reason="tree-sitter missing")
def test_assemble_tsx_reports_slicer():
    result = assemble(
        core_task="fix App",
        code_snippets=[{"path": "App.tsx", "content": REACT}],
        mode="implement",
        targets=["App"],
    )
    assert "tsx" in result["languages"]
    assert "tree-sitter" in result.get("slicers", [])
    body = result["bento_components"][0]["payload_snippet"]
    assert "className" in body


def test_tsx_force_off_env(monkeypatch):
    monkeypatch.setenv("AEGIS_TSX", "0")
    import aegis.treesitter_backend as tb

    tb._TSX_VALIDATED = None
    assert validate_tsx_grammar() is False
