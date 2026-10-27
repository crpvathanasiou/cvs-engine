"""Export results.csv / accepted.csv without modifying source images."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from blur_gate import __version__
from blur_gate.config import BlurGateConfig
from blur_gate.decision import Decision, apply_threshold
from blur_gate.scan import ScoredImage


@dataclass(frozen=True, slots=True)
class ExportRow:
    relative_path: str
    width: int | None
    height: int | None
    sharpness_score: float | None
    decision: str
    reason: str


def build_export_rows(
    scored: list[ScoredImage],
    threshold: float | None,
) -> list[ExportRow]:
    """Build export rows. Without a threshold, decisions are ``unscored`` / ``error`` only."""
    rows: list[ExportRow] = []
    for item in scored:
        if item.error is not None or item.result is None:
            rows.append(
                ExportRow(
                    relative_path=item.relative_path,
                    width=None,
                    height=None,
                    sharpness_score=None,
                    decision="error",
                    reason=item.error or "unreadable_image",
                )
            )
            continue

        result = item.result
        if threshold is None:
            rows.append(
                ExportRow(
                    relative_path=item.relative_path,
                    width=result.width,
                    height=result.height,
                    sharpness_score=result.sharpness_score,
                    decision="scored",
                    reason="threshold_not_selected",
                )
            )
            continue

        decided = apply_threshold(result.sharpness_score, threshold)
        rows.append(
            ExportRow(
                relative_path=item.relative_path,
                width=result.width,
                height=result.height,
                sharpness_score=result.sharpness_score,
                decision=decided.decision.value,
                reason=decided.reason,
            )
        )
    return rows


def write_results_csv(
    path: Path | str,
    rows: list[ExportRow],
    *,
    input_root: Path | str,
    config: BlurGateConfig | None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "relative_path",
                "width",
                "height",
                "sharpness_score",
                "decision",
                "reason",
                "input_root",
                "method",
                "threshold",
                "preprocessing_version",
                "tool_version",
            ]
        )
        method = config.method if config is not None else ""
        threshold = "" if config is None else config.threshold
        prep = config.preprocessing_version if config is not None else ""
        root = str(Path(input_root).resolve())
        for row in rows:
            writer.writerow(
                [
                    row.relative_path,
                    "" if row.width is None else row.width,
                    "" if row.height is None else row.height,
                    "" if row.sharpness_score is None else f"{row.sharpness_score:.10g}",
                    row.decision,
                    row.reason,
                    root,
                    method,
                    threshold,
                    prep,
                    __version__,
                ]
            )


def write_accepted_csv(
    path: Path | str,
    rows: list[ExportRow],
    *,
    input_root: Path | str,
    config: BlurGateConfig,
) -> int:
    """Write only accepted image paths. Requires an explicit config/threshold."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    accepted = [row for row in rows if row.decision == Decision.ACCEPT.value]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "relative_path",
                "input_root",
                "method",
                "threshold",
                "preprocessing_version",
                "tool_version",
            ]
        )
        root = str(Path(input_root).resolve())
        for row in accepted:
            writer.writerow(
                [
                    row.relative_path,
                    root,
                    config.method,
                    config.threshold,
                    config.preprocessing_version,
                    __version__,
                ]
            )
    return len(accepted)


def assert_sources_untouched(paths: list[Path], fingerprints: dict[Path, tuple[int, int]]) -> None:
    """Verify source files were not deleted, moved, or modified during export."""
    for path in paths:
        if not path.is_file():
            raise AssertionError(f"Source image missing after export: {path}")
        stat = path.stat()
        expected = fingerprints.get(path)
        if expected is None:
            continue
        current = (int(stat.st_mtime_ns), int(stat.st_size))
        if current != expected:
            raise AssertionError(f"Source image modified during export: {path}")
