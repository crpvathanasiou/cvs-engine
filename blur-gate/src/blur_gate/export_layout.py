"""Fixed BlurGate export locations (Streamlit-independent)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

EXPORT_DIR_NAME = "blur_gate_export"


def blur_gate_project_root() -> Path:
    """Return the ``blur-gate/`` project root from this package's install location.

    Resolved from ``src/blur_gate/export_layout.py`` → project root, independent of
    the process current working directory.
    """
    # .../blur-gate/src/blur_gate/export_layout.py → parents[2] == blur-gate/
    return Path(__file__).resolve().parents[2]


def export_root() -> Path:
    """Fixed metadata export root: ``<project>/blur_gate_export/``."""
    return blur_gate_project_root() / EXPORT_DIR_NAME


def new_run_output_dir(
    *,
    when: datetime | None = None,
    unique_suffix: str | None = None,
) -> Path:
    """Return a unique per-execution output directory path (not created yet).

    Example: ``blur_gate_export/20261027_103015_a1b2c3d4/``
    """
    stamp_source = when if when is not None else datetime.now(UTC)
    stamp = stamp_source.strftime("%Y%m%d_%H%M%S")
    suffix = unique_suffix if unique_suffix is not None else uuid.uuid4().hex[:8]
    return export_root() / f"{stamp}_{suffix}"
