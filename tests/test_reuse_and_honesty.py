"""Reuse boost (mode+paths key) + code-only token accounting."""

import os
import tempfile

import pytest

from aegis.bento import assemble
from aegis.cli import main
from aegis.pack_cache import pack_key
from aegis.tokens import estimate_code_tokens, estimate_tokens, strip_annotations


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_pack_key_ignores_task_by_default(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n")
    paths = [str(f)]
    k1 = pack_key("explore", paths, "task one")
    k2 = pack_key("explore", paths, "completely different task")
    assert k1 == k2
    k3 = pack_key("explore", paths, "task one", include_task=True)
    k4 = pack_key("explore", paths, "other", include_task=True)
    assert k3 != k4


def test_pack_key_includes_targets():
    # different targets must not collide (use nonexistent paths? need real files)
    pass


def test_pack_key_targets_differ(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    paths = [str(f)]
    k1 = pack_key("implement", paths, "x", targets=["foo"])
    k2 = pack_key("implement", paths, "x", targets=["bar"])
    assert k1 != k2


def test_strip_annotations_removes_chrome():
    text = """// imports
import os
// signatures
def foo():  // foo L1-2
    pass
// --- foo L1-2 ---
def foo():
    return 1
"""
    cleaned = strip_annotations(text)
    assert "import os" in cleaned
    assert "return 1" in cleaned
    assert "---" not in cleaned
    assert estimate_code_tokens(text) < estimate_tokens(text)


def test_assemble_code_only_not_expanded_by_labels():
    # implement with labels should not report higher compressed than raw for modest files
    src = '''
def target_fn(a):
    return a + 1

def other():
    return 0
'''
    payload = assemble(
        core_task="fix",
        code_snippets=[{"path": "m.py", "content": src}],
        mode="implement",
        targets=["target_fn"],
    )
    assert payload["token_accounting"] == "code_only"
    # code-only compressed should be <= raw file tokens (task may add to raw)
    file_raw = estimate_tokens(src)
    assert payload["bento_components"][0]["compressed_tokens"] <= file_raw + 5


def test_cli_reuse_across_tasks(aegis_tmp, tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        '"""waste"""\nimport os\n\ndef foo():\n    return 1\n\ndef bar():\n    x=2\n    return x\n'
    )
    path = str(f)
    assert main(["pack", "--task", "first intent", "--mode", "explore", "--refresh", path]) == 0
    assert main(["pack", "--task", "second different intent", "--mode", "explore", path]) == 0
    from aegis.ledger import read_all

    kinds = [r["kind"] for r in read_all()]
    assert "pack" in kinds
    assert "reuse_hit" in kinds
