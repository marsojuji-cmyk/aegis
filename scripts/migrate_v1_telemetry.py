#!/usr/bin/env python3
import os
import sys
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_FIELDS = {
    "event_id", "request_id", "run_id", "environment", 
    "provider", "rule", "action", "would_block", 
    "shadow_mode", "timestamp_iso", "reason", "redaction_version"
}

def get_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def main():
    if "--dry-run" in sys.argv:
        dry_run = True
        log_path = Path(sys.argv[sys.argv.index("--dry-run") + 1]).expanduser()
    else:
        dry_run = False
        log_path = Path("~/.aegis/guard_log.jsonl").expanduser()

    if not log_path.exists():
        print(f"ERROR: File {log_path} does not exist.")
        sys.exit(1)

    print(f"Starting migration for {log_path}")
    source_sha256 = get_sha256(log_path)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    
    dir_path = log_path.parent
    base_name = "guard_log"
    
    v2_tmp_path = dir_path / f"{base_name}.v2.tmp"
    archive_path = dir_path / f"{base_name}.v1-archive-{timestamp}.jsonl"
    backup_path = dir_path / f"{base_name}.pre-v2-split-{timestamp}.jsonl"
    manifest_path = dir_path / f"{base_name}.v1-split-{timestamp}.manifest.json"

    if archive_path.exists() or backup_path.exists() or manifest_path.exists() or v2_tmp_path.exists():
        print("ERROR: Target paths already exist.")
        sys.exit(1)

    source_lines = 0
    v2_lines = 0
    v1_lines = 0
    malformed_lines = 0

    print("Streaming and categorizing records...")
    with open(log_path, "r") as f_in, \
         open(v2_tmp_path, "w") as f_v2, \
         open(archive_path, "w") as f_v1:
         
        for line in f_in:
            if not line.strip():
                # We skip empty lines in counting, or do we count them?
                # Let's count them to ensure strict line-by-line equality
                source_lines += 1
                f_v1.write(line) # push empty lines to archive or skip? Just treat as malformed.
                malformed_lines += 1
                continue
                
            source_lines += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                malformed_lines += 1
                f_v1.write(line)
                continue

            if REQUIRED_FIELDS.issubset(set(r.keys())):
                v2_lines += 1
                f_v2.write(line)
            else:
                v1_lines += 1
                f_v1.write(line)

    print(f"Verification: {source_lines} == {v2_lines} + {v1_lines} + {malformed_lines}")
    if source_lines != (v2_lines + v1_lines + malformed_lines):
        print("ERROR: Verification failed. Aborting.")
        v2_tmp_path.unlink()
        archive_path.unlink()
        sys.exit(1)

    manifest = {
        "source_sha256": source_sha256,
        "source_lines": source_lines,
        "v2_lines": v2_lines,
        "v1_or_incomplete_lines": v1_lines,
        "malformed_json_lines": malformed_lines,
        "schema_required_fields": sorted(list(REQUIRED_FIELDS)),
        "timestamp_utc": timestamp,
        "tool_version": "1.0",
        "paused_concurrent_writers": True
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    if dry_run:
        print("DRY RUN: Verification succeeded. Cleaning up temps.")
        v2_tmp_path.unlink()
        archive_path.unlink()
        manifest_path.unlink()
        sys.exit(0)

    # Atomic Rename
    print("Performing atomic rename...")
    log_path.rename(backup_path)
    v2_tmp_path.rename(log_path)
    
    print("Migration complete. Manifest written.")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
