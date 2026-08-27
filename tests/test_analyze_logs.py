import json
import subprocess
import pytest
from pathlib import Path

def test_analyzer_redaction_contract(tmp_path):
    log_file = tmp_path / "guard_log.jsonl"
    out_file = tmp_path / "report.json"
    
    # 1. Valid redacted records
    records = [
        {
            "event_id": "1", "request_id": "req-1", "run_id": "run-1",
            "environment": "test", "provider": "mock", "rule": "budget",
            "action": "allow", "would_block": False, "shadow_mode": False,
            "timestamp_iso": "2026-08-14T00:00:00Z", "reason": "ok",
            "redaction_version": "1.0"
        },
        {
            "event_id": "2", "request_id": "req-1", "run_id": "run-1",
            "environment": "test", "provider": "mock", "rule": "mission",
            "action": "block", "would_block": True, "shadow_mode": False,
            "timestamp_iso": "2026-08-14T00:00:01Z", "reason": "blocked",
            "redaction_version": "1.0"
        }
    ]
    
    with open(log_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
            
    # Run analyzer
    cmd = [
        "python3", "scripts/analyze_request_telemetry.py",
        "--environment", "test",
        "--run-id", "run-1",
        "--min-requests", "1",
        "--input", str(log_file),
        "--output", str(out_file)
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    
    report = json.loads(out_file.read_text())
    assert report["valid_requests"] == 1
    assert report["isolated_records"] == 2
    assert "SECRET_KEY" not in json.dumps(report)
    
def test_analyzer_rejects_unredacted_payloads(tmp_path):
    log_file = tmp_path / "guard_log.jsonl"
    out_file = tmp_path / "report.json"
    
    # Contains a raw_prompt field which should trigger a hard rejection
    records = [
        {
            "event_id": "1", "request_id": "req-1", "run_id": "run-1",
            "environment": "test", "provider": "mock", "rule": "budget",
            "action": "allow", "would_block": False, "shadow_mode": False,
            "timestamp_iso": "2026-08-14T00:00:00Z", "reason": "ok",
            "redaction_version": "1.0",
            "raw_prompt": "This is a raw prompt with SECRET_KEY_123"
        }
    ]
    
    with open(log_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
            
    cmd = [
        "python3", "scripts/analyze_request_telemetry.py",
        "--environment", "test",
        "--run-id", "run-1",
        "--min-requests", "1",
        "--input", str(log_file),
        "--output", str(out_file)
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode != 0
    assert "FATAL: Unredacted sensitive payload detected" in res.stderr

def test_analyzer_with_labels(tmp_path):
    log_file = tmp_path / "guard_log.jsonl"
    out_file = tmp_path / "report.json"
    labels_file = tmp_path / "labels.json"
    
    # Create 4 blocked requests
    records = []
    for i in range(1, 5):
        req_id = f"req-{i}"
        records.append({
            "event_id": str(i), "request_id": req_id, "run_id": "run-1",
            "environment": "test", "provider": "mock", "rule": "mission",
            "action": "block", "would_block": True, "shadow_mode": False,
            "timestamp_iso": "2026-08-14T00:00:00Z", "reason": "blocked",
            "redaction_version": "1.0"
        })
        
    with open(log_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
            
    # Create labels
    labels = {
        "req-1": "legitimate",
        "req-2": "false_positive",
        "req-3": "unknown"
        # req-4 is unlabeled
    }
    with open(labels_file, "w") as f:
        json.dump(labels, f)
        
    cmd = [
        "python3", "scripts/analyze_request_telemetry.py",
        "--environment", "test",
        "--run-id", "run-1",
        "--min-requests", "1",
        "--input", str(log_file),
        "--output", str(out_file),
        "--labels", str(labels_file)
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    
    report = json.loads(out_file.read_text())
    assert report["valid_requests"] == 4
    assert report["flagged_requests"] == 4
    
    # 2 labeled, 2 unlabeled (one explicit "unknown", one missing)
    assert report["labeled_flagged_requests"] == 2
    assert report["unlabeled_flagged_requests"] == 2
    
    assert report["false_positive_rate"] == 50.0
    assert report["legitimate_would_block_request_rate"] == 50.0
