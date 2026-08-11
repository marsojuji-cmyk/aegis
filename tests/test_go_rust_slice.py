"""Go/Rust structure slicers — explore cuts bodies; implement keeps targets."""

from aegis.bento import assemble
from aegis.go_slice import build_explore_go, build_implement_go, extract_go_units
from aegis.rust_slice import build_explore_rust, build_implement_rust, extract_rust_units

GO = """
package main

import (
  "fmt"
)

type Server struct {
  Port int
}

func helper() int {
  return 1
}

func (s *Server) Handle(path string) string {
  result := path + ":ok"
  if s.Port > 0 {
    return result
  }
  return "down"
}

func main() {
  fmt.Println("hi")
}
"""

RUST = """
use std::io;

pub struct Config {
  pub port: u16,
}

fn helper() -> i32 {
  1
}

pub fn target_fn(a: i32, b: i32) -> i32 {
  let total = a + b;
  if total > 10 {
    return total * 2;
  }
  total - 1
}

impl Config {
  pub fn new(port: u16) -> Self {
    Self { port }
  }
}
"""


def test_go_units_include_methods():
    units = extract_go_units(GO)
    names = {u["qualname"] for u in units}
    assert "Server" in names or any(u["name"] == "Server" for u in units)
    assert "Server.Handle" in names
    assert "helper" in names
    assert "main" in names


def test_go_explore_drops_body():
    exp = build_explore_go(GO)
    assert "Handle" in exp
    assert 'result := path + ":ok"' not in exp


def test_go_implement_keeps_method_body():
    payload, meta = build_implement_go(GO, targets=["Server.Handle"])
    assert meta["fidelity"] == "target_bodies"
    assert 'result := path + ":ok"' in payload
    assert "return result" in payload


def test_rust_units():
    units = extract_rust_units(RUST)
    names = {u["name"] for u in units}
    assert "target_fn" in names
    assert "Config" in names
    assert "helper" in names


def test_rust_explore_drops_body():
    exp = build_explore_rust(RUST)
    assert "target_fn" in exp
    assert "let total = a + b" not in exp


def test_rust_implement_keeps_target():
    payload, meta = build_implement_rust(RUST, targets=["target_fn"])
    assert meta["fidelity"] == "target_bodies"
    assert "let total = a + b" in payload
    assert "total - 1" in payload


def test_assemble_go_rust():
    result = assemble(
        core_task="fix Handle and target_fn",
        code_snippets=[
            {"path": "main.go", "content": GO},
            {"path": "lib.rs", "content": RUST},
        ],
        mode="implement",
        targets=["Server.Handle", "target_fn"],
    )
    assert "go" in result["languages"]
    assert "rust" in result["languages"]
    by = {c["path"]: c["payload_snippet"] for c in result["bento_components"]}
    assert 'result := path + ":ok"' in by["main.go"]
    assert "let total = a + b" in by["lib.rs"]
