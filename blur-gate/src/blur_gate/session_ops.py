"""Helpers for BlurGate UI session validation (Streamlit-independent)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blur_gate.scan import ScoredImage, cache_key_for_file, list_image_files, score_tree


def fingerprint_tree(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    keys = [cache_key_for_file(path) for path in list_image_files(root)]
    return tuple(keys)


def scan_root_available(input_root: str | None) -> bool:
    """Return True when a previously scanned root path still exists as a directory."""
    if not input_root:
        return False
    return Path(input_root).is_dir()


def export_allowed(input_root: str | None, has_scored_rows: bool) -> tuple[bool, str | None]:
    """Gate exports on a valid live scan root and in-memory scored rows."""
    if not has_scored_rows:
        return False, "No scored results available. Scan a valid folder first."
    if not scan_root_available(input_root):
        return (
            False,
            "Scanned folder is no longer available. Scan a valid folder before exporting.",
        )
    return True, None


@dataclass(frozen=True, slots=True)
class ExportScanPreparation:
    """Rows ready for export after root/fingerprint validation."""

    rows: list[ScoredImage]
    warnings: list[str]
    token: tuple[tuple[str, int, int, str], ...]
    refreshed: bool


def prepare_export_scan(
    input_root: str | None,
    cached_token: object | None,
    cached_rows: list[ScoredImage] | None,
) -> ExportScanPreparation | str:
    """Validate the scan root and refresh scores when the file fingerprint changed.

    Returns an ``ExportScanPreparation`` on success, or an error message string.
    Does not write export files. Threshold-only changes do not alter the fingerprint,
    so they do not trigger rescoring.
    """
    if not input_root:
        return "No scored results available. Scan a valid folder first."
    if not scan_root_available(input_root):
        return (
            "Scanned folder is no longer available. Scan a valid folder before exporting."
        )

    root = Path(input_root)
    try:
        token = fingerprint_tree(root)
    except OSError as exc:
        return f"Could not read scan folder: {exc}"

    if cached_token is None and cached_rows is None:
        return "No scored results available. Scan a valid folder first."

    if token != cached_token:
        try:
            rows, warnings = score_tree(root)
        except OSError as exc:
            return f"Could not refresh scores before export: {exc}"
        return ExportScanPreparation(
            rows=rows,
            warnings=warnings,
            token=token,
            refreshed=True,
        )

    if cached_rows is None:
        return "No scored results available. Scan a valid folder first."
    return ExportScanPreparation(
        rows=list(cached_rows),
        warnings=[],
        token=token,
        refreshed=False,
    )
