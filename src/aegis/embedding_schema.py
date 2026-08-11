"""Validate Semantic Embedding Handoff Packs against schemas/embedding_handoff.schema.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def schema_path() -> Path:
    # src/aegis/embedding_schema.py → repo root / schemas
    return Path(__file__).resolve().parents[2] / "schemas" / "embedding_handoff.schema.json"


def load_schema() -> Dict[str, Any]:
    path = schema_path()
    return json.loads(path.read_text(encoding="utf-8"))


def validate_embedding_pack(pack: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Lightweight validator (no jsonschema dependency required).
    Returns (ok, errors).
    """
    errors: List[str] = []
    required = [
        "handoff_version",
        "generated_at",
        "session_id",
        "embedding_model",
        "dimensions",
        "distance_metric",
        "integrity_hash",
        "vectors",
        "retrieval_hints",
    ]
    for k in required:
        if k not in pack:
            errors.append(f"missing required field: {k}")

    if pack.get("handoff_version") != "1.0":
        errors.append("handoff_version must be '1.0'")

    if pack.get("distance_metric") not in ("cosine", "dot", "euclidean", None):
        if "distance_metric" in pack:
            errors.append("distance_metric invalid")

    ih = str(pack.get("integrity_hash") or "")
    if ih and (len(ih) != 64 or any(c not in "0123456789abcdef" for c in ih)):
        errors.append("integrity_hash must be 64-char lowercase hex")

    vectors = pack.get("vectors")
    if not isinstance(vectors, list) or len(vectors) < 1:
        errors.append("vectors must be non-empty array")
    else:
        for i, v in enumerate(vectors):
            if not isinstance(v, dict):
                errors.append(f"vectors[{i}] not object")
                continue
            for rk in ("id", "label", "canonical_text", "metadata"):
                if rk not in v:
                    errors.append(f"vectors[{i}] missing {rk}")
            if not str(v.get("canonical_text") or "").strip():
                errors.append(f"vectors[{i}] empty canonical_text")
            vec = v.get("vector")
            if vec is not None:
                if not isinstance(vec, list) or not all(isinstance(x, (int, float)) for x in vec):
                    errors.append(f"vectors[{i}].vector invalid")

    hints = pack.get("retrieval_hints")
    if not isinstance(hints, list) or len(hints) < 4:
        errors.append("retrieval_hints must have ≥4 strings")

    return (len(errors) == 0, errors)
