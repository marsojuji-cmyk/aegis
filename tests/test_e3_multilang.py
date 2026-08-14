"""E3 multi-lang scrub + TS slice + scrub-only fallback."""

from aegis.bento import assemble
from aegis.lang import detect_lang, is_first_class
from aegis.scrub import scrub
from aegis.ts_slice import build_explore_js, build_implement_js

TS_SAMPLE = """
/* license header */
import { foo } from "./foo";

// helper
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
  render() {
    return null;
  }
}
"""

GO_SAMPLE = """
package main
// comment
import "fmt"

/* block */
func main() {
  fmt.Println("hi")
}
"""


def test_detect_lang():
    assert detect_lang("a.ts") == "typescript"
    assert detect_lang("a.py") == "python"
    assert detect_lang("a.go") == "go"


def test_is_first_class():
    assert is_first_class("python") is True
    assert is_first_class("go") is False


def test_ts_explore_drops_bodies():
    exp = build_explore_js(TS_SAMPLE)
    assert "targetFn" in exp
    assert "const total = a + b" not in exp


def test_ts_implement_keeps_target_body():
    payload, meta = build_implement_js(TS_SAMPLE, targets=["targetFn"])
    assert meta["fidelity"] == "target_bodies"
    assert "const total = a + b" in payload
    assert "return total - 1" in payload


def test_assemble_ts_and_go():
    result = assemble(
        core_task="fix targetFn",
        code_snippets=[
            {"path": "app.ts", "content": TS_SAMPLE},
            {"path": "main.go", "content": GO_SAMPLE},
        ],
        mode="implement",
        targets=["targetFn"],
    )
    assert result["engine"] == "product_e3"
    assert "typescript" in result["languages"]
    assert "go" in result["languages"]
    by_path = {c["path"]: c for c in result["bento_components"]}
    assert "const total = a + b" in by_path["app.ts"]["payload_snippet"]
    # go implement unknown structure → full file fidelity
    assert "func main" in by_path["main.go"]["payload_snippet"]


def test_scrub_js_strips_block_comments():
    cleaned, stats = scrub(TS_SAMPLE, "typescript")
    assert "license header" not in cleaned
    assert stats["tokens_saved"] >= 0


def test_python_still_fidelity():
    py = "def target_fn(a):\n    return a + 1\n\ndef other():\n    return 0\n"
    result = assemble(
        core_task="fix target_fn",
        code_snippets=[{"path": "m.py", "content": py}],
        mode="implement",
        targets=["target_fn"],
    )
    text = result["bento_components"][0]["payload_snippet"]
    assert "return a + 1" in text
