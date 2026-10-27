"""Tests for scan-root export gating and export-time refresh helpers."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from blur_gate.scan import score_tree
from blur_gate.session_ops import (
    ExportScanPreparation,
    export_allowed,
    fingerprint_tree,
    prepare_export_scan,
    scan_root_available,
)


def _write_png(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.full((32, 32, 3), value, dtype=np.uint8)
    img[::2, ::2] = 255 - value
    assert cv2.imwrite(str(path), img)


def test_scan_root_available(tmp_path: Path) -> None:
    assert scan_root_available(None) is False
    assert scan_root_available("") is False
    assert scan_root_available(str(tmp_path)) is True
    missing = tmp_path / "gone"
    assert scan_root_available(str(missing)) is False


def test_export_allowed_requires_live_root_and_rows(tmp_path: Path) -> None:
    ok, message = export_allowed(str(tmp_path), has_scored_rows=True)
    assert ok is True
    assert message is None

    ok, message = export_allowed(str(tmp_path / "missing"), has_scored_rows=True)
    assert ok is False
    assert message is not None
    assert "no longer available" in message

    ok, message = export_allowed(str(tmp_path), has_scored_rows=False)
    assert ok is False
    assert message is not None
    assert "Scan a valid folder" in message


def test_prepare_export_scan_refreshes_on_fingerprint_change(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    path = root / "a.png"
    _write_png(path, 80)
    rows, warnings = score_tree(root)
    token = fingerprint_tree(root)
    assert warnings == [] or isinstance(warnings, list)

    # Modify file contents → fingerprint changes.
    constant = np.full((32, 32, 3), 128, dtype=np.uint8)
    assert cv2.imwrite(str(path), constant)

    prepared = prepare_export_scan(str(root.resolve()), token, rows)
    assert isinstance(prepared, ExportScanPreparation)
    assert prepared.refreshed is True
    assert len(prepared.rows) == 1
    assert prepared.rows[0].result is not None
    assert prepared.rows[0].result.sharpness_score == 0.0
    assert prepared.token == fingerprint_tree(root)


def test_prepare_export_scan_skips_rescore_when_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    _write_png(root / "a.png", 80)
    rows, _warnings = score_tree(root)
    token = fingerprint_tree(root)
    prepared = prepare_export_scan(str(root.resolve()), token, rows)
    assert isinstance(prepared, ExportScanPreparation)
    assert prepared.refreshed is False
    assert prepared.rows is not rows  # copied list
    assert prepared.rows[0].result is not None
    assert rows[0].result is not None
    assert prepared.rows[0].result.sharpness_score == rows[0].result.sharpness_score


def test_prepare_export_scan_missing_root(tmp_path: Path) -> None:
    message = prepare_export_scan(str(tmp_path / "missing"), None, [])
    assert isinstance(message, str)
    assert "no longer available" in message.lower()
