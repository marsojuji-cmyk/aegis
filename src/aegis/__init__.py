"""Aegis — JIT token supply chain (piggy bank + 3R)."""

__version__ = "1.1.1"

# Shared concurrency defaults (CLI, pipeline, daemon status)
DEFAULT_BATCH_WORKERS = 16
MAX_BATCH_WORKERS = 32

LEGACY_PIPELINE = (
    "/Users/a100/.gemini/antigravity/scratch/aegis_pipeline"
)
DEFAULT_ENGINE = "legacy"
