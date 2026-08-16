import pytest

from aegis.config import AegisConfig
from aegis.guard import AegisGuard, AegisGuardError, aegis_protect


def test_guard_budget_and_velocity():
    config = AegisConfig(guard_shadow_mode=False, 
        guard_max_tool_calls=3,
        guard_max_velocity_calls_per_min=2,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def dummy_tool(x):
        return x

    # Call 1 (OK)
    assert dummy_tool(1) == 1
    
    # Call 2 (OK)
    assert dummy_tool(2) == 2
    
    # Call 3 (Fails velocity)
    with pytest.raises(AegisGuardError, match="VELOCITY"):
        dummy_tool(3)

    # Let's bypass velocity for a moment to test total budget
    # by bumping the velocity limit
    guard.config.guard_max_velocity_calls_per_min = 10

    # Call 3 (OK now)
    assert dummy_tool(3) == 3

    # Call 4 (Fails total budget)
    with pytest.raises(AegisGuardError, match="BUDGET"):
        dummy_tool(4)


def test_guard_loop_detection():
    config = AegisConfig(guard_shadow_mode=False, 
        guard_max_tool_calls=10,
        guard_max_velocity_calls_per_min=10,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def dummy_tool(arg1):
        return "ok"

    dummy_tool(arg1="A")
    dummy_tool(arg1="A")
    with pytest.raises(AegisGuardError, match="LOOP"):
        dummy_tool(arg1="A")


def test_guard_mission_lock():
    config = AegisConfig(guard_shadow_mode=False, 
        guard_allowed_domains="/app/logs, https://api.allowed.com",
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def read_file(filepath: str):
        return "file contents"

    @aegis_protect(guard)
    def fetch_url(url: str):
        return "url contents"

    # Valid
    assert read_file(filepath="/app/logs/server.log") == "file contents"
    assert fetch_url(url="https://api.allowed.com/data") == "url contents"

    # Invalid
    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        read_file(filepath="/etc/passwd")

    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        fetch_url(url="https://evil.com/data")


def test_guard_signal_preservation():
    config = AegisConfig(guard_shadow_mode=False,
        guard_signal_shadow_mode=False,
        guard_max_output_length=50,
        guard_min_signal_score=0.5,
        guard_signal_preserve_keywords="DEPLOY_KEY, CRITICAL_SECRET",
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def short_tool():
        return "Short string"

    assert short_tool() == "Short string"

    @aegis_protect(guard)
    def repetitive_tool():
        return "filler " * 1000

    res_rep = repetitive_tool()
    assert "AEGIS SIGNAL PRUNED" in res_rep
    assert "filler filler" in res_rep
    assert len(res_rep) < 200

    @aegis_protect(guard)
    def critical_tool():
        return "This is a very long text with lots of words " * 20 + " DEPLOY_KEY is 123456 " + " and more filler words here to pad it out " * 20

    res_crit = critical_tool()
    assert "AEGIS SIGNAL PRUNED" in res_crit
    assert "DEPLOY_KEY is 123456" in res_crit
    assert "Preserved critical snippet" in res_crit


def test_guard_audit_trail():
    config = AegisConfig(guard_shadow_mode=False, 
        guard_audit_limit=10,
        guard_max_tool_calls=100,
        guard_max_velocity_calls_per_min=100,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def dummy_tool(x):
        return str(x)

    # Generate 15 decisions (above limit of 10)
    for i in range(15):
        dummy_tool(i)
        
    assert len(guard.state.decisions) == 10
    
    # Check that they have the right shape (last recorded rule in success path is 'loop')
    last_decision = guard.state.decisions[-1]
    assert last_decision.rule == "loop"
    assert last_decision.action == "allow"

def test_guard_redaction_contract(monkeypatch, tmp_path):
    import json
    from aegis.guard import GUARD_LOG_PATH
    log_file = tmp_path / "guard_log.jsonl"
    monkeypatch.setattr("aegis.guard.GUARD_LOG_PATH", log_file)

    config = AegisConfig(guard_shadow_mode=False)
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def dummy_tool(secret_value, safe_value):
        return "ok"

    # 1. Safe request
    dummy_tool(secret_value="normal", safe_value="data")
    lines = log_file.read_text().strip().split("\n")
    record = json.loads(lines[-1])
    assert record.get("redaction_version") == "1.0"
    assert "raw_prompt" not in record
    assert "provider_payload" not in record

    # 2. Sensitive request (should not leak into log)
    dummy_tool(secret_value="SUPER_SECRET_TOKEN_123", safe_value="data")
    lines = log_file.read_text().strip().split("\n")
    record_text = lines[-1]
    record = json.loads(record_text)
    assert "SUPER_SECRET_TOKEN_123" not in record_text
    # We asserted it's redacted or safely truncated since the arg signature is not fully exposed or is pruned by the excerpt logger. 
    # (In our case, kwargs aren't natively serialized in decisions except lightly in loop excerpts, which are truncated)

    # 3. Blocked path (e.g. budget exhaustion)
    guard.config.guard_max_tool_calls = 0
    import pytest
    from aegis.guard import AegisGuardError
    with pytest.raises(AegisGuardError):
        dummy_tool(secret_value="blocked", safe_value="data")
    lines = log_file.read_text().strip().split("\n")
    record_text = lines[-1]
    record = json.loads(record_text)
    assert record.get("would_block") is True
    assert record.get("redaction_version") == "1.0"
    assert "raw_prompt" not in record_text

def test_guard_shadow_mode():
    config = AegisConfig(
        guard_shadow_mode=True,
        guard_max_velocity_calls_per_min=2,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def dummy_tool(x):
        return x

    # 1 (OK)
    assert dummy_tool(1) == 1
    # 2 (OK)
    assert dummy_tool(2) == 2
    # 3 (Should fail velocity, but shadow mode suppresses Exception)
    # The call should succeed and return 3.
    assert dummy_tool(3) == 3

    # The decision should still be recorded as a block
    decisions = guard.state.decisions
    assert len(decisions) >= 3
    block_decision = next(d for d in reversed(decisions) if d.action == "block")
    assert block_decision.rule == "budget"
    assert "velocity" in block_decision.reason.lower()

def test_guard_stress_ring_buffer():
    config = AegisConfig(guard_shadow_mode=False, 
        guard_audit_limit=50,
        guard_max_tool_calls=2000,
        guard_max_velocity_calls_per_min=2000,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def dummy_tool(x):
        return str(x)

    # Hammer it with 1000 sequential calls (generating 3000 decisions)
    for i in range(1000):
        dummy_tool(i)
        
    # The ring buffer should strictly limit to 50
    assert len(guard.state.decisions) == 50

def test_guard_nested_calls():
    config = AegisConfig(guard_shadow_mode=False, 
        guard_max_tool_calls=10,
        guard_max_velocity_calls_per_min=10,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def inner_tool():
        return "inner"

    @aegis_protect(guard)
    def outer_tool():
        return inner_tool()

    # Call outer_tool once. Should consume 2 budget tokens.
    assert guard.state.total_calls == 0
    outer_tool()
    
    assert guard.state.total_calls == 2
    
    # Check decision log for 2 sets of decisions
    rules = [d.rule for d in guard.state.decisions]
    # budget, mission, loop (outer), budget, mission, loop (inner) 
    # Or inner then outer depending on return paths, but budget is hit going in.
    assert rules.count("budget") == 2

def test_guard_concurrent_execution():
    import threading
    config = AegisConfig(guard_shadow_mode=False, 
        guard_max_tool_calls=200,
        guard_max_velocity_calls_per_min=200,
        guard_audit_limit=100
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def thread_tool(thread_id, call_idx):
        return "ok"

    threads = []
    for _ in range(10):
        t = threading.Thread(target=lambda: [thread_tool(threading.get_ident(), i) for i in range(5)])
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # 10 threads * 5 calls = 50 calls
    assert guard.state.total_calls == 50
    
    # 50 calls * 3 decisions = 150 decisions.
    # Ring buffer is limited to 100
    assert len(guard.state.decisions) == 100


def test_guard_tool_pilot_flow(tmp_path):
    """Folded demo of read/write/edit + prune + mission-lock.

    outcomes.*_pilot remains the durable matched-pair SoT. This is the
    only remaining guard-tool sequence; src/aegis/pilot_{runner,tools}.py
    are not product modules.
    """
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("seed\n", encoding="utf-8")

    config = AegisConfig(
        guard_shadow_mode=False,
        guard_signal_shadow_mode=False,
        guard_max_output_length=100,
        guard_min_signal_score=0.5,
        guard_max_tool_calls=20,
        guard_max_velocity_calls_per_min=20,
        guard_allowed_domains=str(allowed),
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def read_file(filepath: str) -> str:
        with open(filepath, "r", encoding="utf-8") as handle:
            return handle.read()

    @aegis_protect(guard)
    def write_file(filepath: str, content: str) -> str:
        with open(filepath, "w", encoding="utf-8") as handle:
            handle.write(content)
        return f"wrote {len(content)} bytes"

    @aegis_protect(guard)
    def edit_file(filepath: str, content: str) -> str:
        with open(filepath, "a", encoding="utf-8") as handle:
            handle.write(content)
        return f"appended {len(content)} bytes to {content}"

    @aegis_protect(guard)
    def emit(payload: str) -> str:
        return payload

    assert read_file(filepath=str(target)) == "seed\n"
    assert "wrote" in write_file(filepath=str(target), content="ok\n")
    assert target.read_text(encoding="utf-8") == "ok\n"

    pruned = emit(payload="filler " * 1000)
    assert "AEGIS SIGNAL PRUNED" in pruned

    verbose_edit = edit_file(filepath=str(target), content="filler " * 1000)
    assert "AEGIS SIGNAL PRUNED" in verbose_edit

    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        read_file(filepath="/etc/shadow")
    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        write_file(filepath="/etc/hosts", content="127.0.0.1 evil.com")

    actions = [decision.action for decision in guard.state.decisions]
    assert "allow" in actions
    assert "prune" in actions
    assert "block" in actions
    for decision in guard.state.decisions:
        assert decision.reason
        if decision.action == "block":
            assert decision.input_excerpt is not None
