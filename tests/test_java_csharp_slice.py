"""Java/C# structure slicers — explore sigs; implement full targets."""

from aegis.bento import assemble
from aegis.csharp_slice import (
    build_explore_csharp,
    build_implement_csharp,
    extract_csharp_units,
)
from aegis.java_slice import build_explore_java, build_implement_java, extract_java_units

JAVA = """
package com.example;

import java.util.List;

public class Server {
  private int port;

  public String handle(String path) {
    String result = path + ":ok";
    if (port > 0) {
      return result;
    }
    return "down";
  }

  private void helper() {
    int x = 1;
  }
}

interface Runner {
  void run();
}
"""

CSHARP = """
using System;

namespace Demo;

public class Server {
  public int Port { get; set; }

  public string Handle(string path) {
    var result = path + ":ok";
    if (Port > 0) {
      return result;
    }
    return "down";
  }

  void Helper() {
    var x = 1;
  }
}

public interface IRunner {
  void Run();
}
"""


def test_java_units():
    units = extract_java_units(JAVA)
    qns = {u["qualname"] for u in units}
    assert "Server" in qns
    assert any("handle" in q.lower() for q in qns)
    assert "Runner" in qns


def test_java_explore_drops_body():
    exp = build_explore_java(JAVA)
    assert "handle" in exp
    assert 'String result = path + ":ok"' not in exp


def test_java_implement_keeps_method():
    payload, meta = build_implement_java(JAVA, targets=["Server.handle"])
    if meta["fidelity"] != "target_bodies":
        # name match may be case-sensitive handle
        payload, meta = build_implement_java(JAVA, targets=["handle"])
    assert meta["fidelity"] == "target_bodies"
    assert 'String result = path + ":ok"' in payload
    assert "return result" in payload


def test_csharp_units():
    units = extract_csharp_units(CSHARP)
    qns = {u["qualname"] for u in units}
    assert any("Server" in q for q in qns)
    assert any("Handle" in q for q in qns)


def test_csharp_explore_drops_body():
    exp = build_explore_csharp(CSHARP)
    assert "Handle" in exp
    assert 'var result = path + ":ok"' not in exp


def test_csharp_implement_keeps_method():
    payload, meta = build_implement_csharp(CSHARP, targets=["Handle"])
    assert meta["fidelity"] == "target_bodies"
    assert 'var result = path + ":ok"' in payload


def test_assemble_java_csharp():
    result = assemble(
        core_task="fix Handle",
        code_snippets=[
            {"path": "Server.java", "content": JAVA},
            {"path": "Server.cs", "content": CSHARP},
        ],
        mode="implement",
        targets=["handle", "Handle"],
    )
    assert "java" in result["languages"]
    assert "csharp" in result["languages"]
    by = {c["path"]: c["payload_snippet"] for c in result["bento_components"]}
    assert ":ok" in by["Server.java"] or ":ok" in by["Server.cs"]
