"""Manifest-driven dataset filtering with metadata-only outputs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, TextIO

from blur_gate.config import BlurGateConfig, ConfigError, ensure_compatible_config
from blur_gate.dataset_source import (
    IMAGE_COUNT_FIELD,
    DatasetValidationError,
    SourceDatasetInfo,
    iter_manifest_records,
    open_source_dataset,
    validate_manifest_record,
)
from blur_gate.decision import Decision, apply_threshold
from blur_gate.paths import resolve_under_root
from blur_gate.progress import (
    DEFAULT_THROTTLE_SECONDS,
    CountProgressCallback,
    ProgressReporter,
    ProgressUpdate,
    ProgressUpdateCallback,
)
from blur_gate.run_info import write_run_info_from_report
from blur_gate.scoring import ImageReadError, score_file
from blur_gate.version import __version__

FILTER_PIPELINE_NAME = "blur_filtering"
FILTER_SCHEMA_VERSION = "1.0"


class DatasetFilterError(RuntimeError):
    """Filtering aborted before a successful completion report."""


@dataclass
class AggregateCounts:
    input: int = 0
    accepted: int = 0
    rejected: int = 0
    error: int = 0


@dataclass
class FilterResult:
    output_dir: Path
    status: str
    counts: AggregateCounts
    source: SourceDatasetInfo
    run_report: dict[str, Any] = field(default_factory=lambda: {})


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        if any(output_dir.iterdir()):
            raise DatasetFilterError(
                f"Output directory exists and is not empty: {output_dir}"
            )
    else:
        output_dir.mkdir(parents=True, exist_ok=False)


def _write_failed_report(
    output_dir: Path,
    *,
    config: BlurGateConfig,
    source: SourceDatasetInfo | None,
    message: str,
    counts: AggregateCounts | None = None,
) -> None:
    """Write a non-success run.json so a failed export never looks completed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": FILTER_SCHEMA_VERSION,
        "pipeline_name": FILTER_PIPELINE_NAME,
        "created_at": _utc_now(),
        "status": "failed",
        "error": message,
        "blur_gate": {
            "version": __version__,
            "method": config.method,
            "threshold": config.threshold,
            "preprocessing_version": config.preprocessing_version,
        },
    }
    if counts is not None:
        payload["counts"] = {
            "input": counts.input,
            "accepted": counts.accepted,
            "rejected": counts.rejected,
            "error": counts.error,
        }
    if source is not None:
        payload["source_dataset"] = {
            "root": str(source.root),
            "extraction_status": source.extraction_status,
            "manifest_sha256": source.manifest_sha256,
            "run_sha256": source.run_sha256,
        }
    (output_dir / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    write_run_info_from_report(output_dir, payload)


def _score_record(
    source_root: Path,
    record: dict[str, Any],
    config: BlurGateConfig,
) -> tuple[str, float | None, str]:
    """Return decision, score (or None), reason."""
    rel = str(record["path"]).replace("\\", "/")
    absolute = resolve_under_root(source_root, rel)
    try:
        result = score_file(absolute)
    except ImageReadError as exc:
        return "error", None, str(exc)
    except OSError as exc:
        return "error", None, f"Unreadable image: {exc}"

    decided = apply_threshold(result.sharpness_score, config.threshold)
    return decided.decision.value, result.sharpness_score, decided.reason


def _write_mapping(
    path: Path,
    source: SourceDatasetInfo,
    accepted_video_ids: set[str],
) -> int:
    kept = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["OriginalVideo", "ImageFolder"])
        writer.writeheader()
        for row in source.mapping_rows:
            folder = row.image_folder.replace("\\", "/").rstrip("/")
            video_key = PurePosixPath(folder).name
            if video_key in accepted_video_ids:
                writer.writerow(
                    {
                        "OriginalVideo": row.original_video,
                        "ImageFolder": row.image_folder,
                    }
                )
                kept += 1
    return kept


def _build_success_report(
    *,
    source: SourceDatasetInfo,
    config: BlurGateConfig,
    counts: AggregateCounts,
    per_video: dict[str, AggregateCounts],
    per_segment: dict[str, AggregateCounts],
    status: str,
) -> dict[str, Any]:
    usable_videos = sorted(vid for vid, c in per_video.items() if c.accepted > 0)
    usable_segments = sorted(sid for sid, c in per_segment.items() if c.accepted > 0)

    videos_out: list[dict[str, Any]] = []
    for meta in source.videos_meta:
        vid = str(meta["video_id"])
        c = per_video.get(vid, AggregateCounts())
        videos_out.append(
            {
                "video_id": vid,
                "usable": c.accepted > 0,
                "counts": {
                    "input": c.input,
                    "accepted": c.accepted,
                    "rejected": c.rejected,
                    "error": c.error,
                },
                "source_metadata": {key: meta[key] for key in meta if key != "video_id"},
            }
        )

    segments_out: list[dict[str, Any]] = []
    for meta in source.segments_meta:
        sid = str(meta["segment_id"])
        c = per_segment.get(sid, AggregateCounts())
        segments_out.append(
            {
                "segment_id": sid,
                "video_id": str(meta["video_id"]),
                "usable": c.accepted > 0,
                "counts": {
                    "input": c.input,
                    "accepted": c.accepted,
                    "rejected": c.rejected,
                    "error": c.error,
                },
                "source_metadata": {
                    key: meta[key] for key in meta if key not in {"segment_id", "video_id"}
                },
            }
        )

    return {
        "schema_version": FILTER_SCHEMA_VERSION,
        "pipeline_name": FILTER_PIPELINE_NAME,
        "created_at": _utc_now(),
        "status": status,
        "blur_gate": {
            "version": __version__,
            "method": config.method,
            "threshold": config.threshold,
            "preprocessing_version": config.preprocessing_version,
        },
        "source_dataset": {
            "root": str(source.root),
            "manifest_path": source.manifest_path.name,
            "manifest_sha256": source.manifest_sha256,
            "run_path": source.run_path.name,
            "run_sha256": source.run_sha256,
            "mapping_path": source.mapping_path.name,
            "mapping_sha256": source.mapping_sha256,
            "extraction_status": source.extraction_status,
            "workbook": source.workbook,
            "source_counts": source.source_counts,
        },
        "counts": {
            "input": counts.input,
            "accepted": counts.accepted,
            "rejected": counts.rejected,
            "error": counts.error,
        },
        "usable_membership": {
            "videos": usable_videos,
            "segments": usable_segments,
        },
        "videos": videos_out,
        "segments": segments_out,
    }


def filter_dataset(
    source_root: Path | str,
    output_dir: Path | str,
    config: BlurGateConfig,
    *,
    progress_callback: CountProgressCallback | None = None,
    progress_update_callback: ProgressUpdateCallback | None = None,
    progress_every: int = 100,
    progress_throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
) -> FilterResult:
    """Filter a source extraction dataset into metadata-only BlurGate outputs.

    Never copies, moves, or modifies source images. Paths in the accepted
    ``manifest.jsonl`` remain relative to the source dataset root.

    ``progress_callback`` keeps the legacy ``(processed, total)`` contract.
    ``progress_update_callback`` receives rich ``ProgressUpdate`` snapshots.
    Both are throttled by time and optionally every ``progress_every`` processed
    inputs. Rejected images and read errors are included in the processed count.
    """
    out = Path(output_dir).expanduser().resolve()
    source: SourceDatasetInfo | None = None
    counts = AggregateCounts()
    started = False

    def _notify_progress(update: ProgressUpdate) -> None:
        if progress_update_callback is not None:
            progress_update_callback(update)
        if progress_callback is not None:
            progress_callback(update.processed, update.total)

    reporter = ProgressReporter(
        _notify_progress if (progress_callback or progress_update_callback) else None,
        throttle_seconds=progress_throttle_seconds,
        progress_every=progress_every,
        preparing_message="Reading dataset metadata…",
    )

    try:
        # Validate configuration before creating outputs or scoring images.
        try:
            config = ensure_compatible_config(config)
        except ConfigError as exc:
            raise DatasetFilterError(str(exc)) from exc

        reporter.preparing("Reading dataset metadata…")
        source = open_source_dataset(source_root)
        if out == source.root:
            raise DatasetFilterError(
                "Output directory must not be the source dataset root"
            )
        _prepare_output_dir(out)
        started = True
        reporter.start(source.expected_image_count)

        results_path = out / "results.csv"
        manifest_out_path = out / "manifest.jsonl"
        mapping_out_path = out / "video-folder-mapping.csv"
        rejected_path = out / "rejected.txt"

        per_video: dict[str, AggregateCounts] = defaultdict(AggregateCounts)
        per_segment: dict[str, AggregateCounts] = defaultdict(AggregateCounts)
        accepted_video_ids: set[str] = set()
        seen_image_ids: set[str] = set()
        seen_paths: set[str] = set()
        accepted_written = 0
        rejected_written = 0
        results_written = 0

        results_file: TextIO = results_path.open("w", encoding="utf-8", newline="")
        manifest_file: TextIO = manifest_out_path.open("w", encoding="utf-8")
        # Create rejected.txt immediately (empty when no rejects). Write paths
        # incrementally during the loop — do not accumulate rejected paths in memory.
        rejected_file: TextIO = rejected_path.open("w", encoding="utf-8", newline="\n")
        try:
            results_writer = csv.writer(results_file)
            results_writer.writerow(
                ["image_id", "path", "sharpness_score", "decision", "reason"]
            )

            for record in iter_manifest_records(source.manifest_path):
                validate_manifest_record(
                    record,
                    source=source,
                    seen_image_ids=seen_image_ids,
                    seen_paths=seen_paths,
                )
                record_out = dict(record)
                image_id = str(record_out["image_id"])
                rel_path = str(record_out["path"]).replace("\\", "/")
                video_id = str(record_out["video_id"])
                segment_id = str(record_out["segment_id"])

                decision, score, reason = _score_record(source.root, record_out, config)

                counts.input += 1
                per_video[video_id].input += 1
                per_segment[segment_id].input += 1

                if decision == Decision.ACCEPT.value:
                    counts.accepted += 1
                    per_video[video_id].accepted += 1
                    per_segment[segment_id].accepted += 1
                    accepted_video_ids.add(video_id)
                    # Preserve original relative path (still resolved against source root).
                    manifest_file.write(json.dumps(record_out, sort_keys=False) + "\n")
                    accepted_written += 1
                elif decision == Decision.REJECT.value:
                    counts.rejected += 1
                    per_video[video_id].rejected += 1
                    per_segment[segment_id].rejected += 1
                    absolute = resolve_under_root(source.root, rel_path)
                    rejected_file.write(str(absolute) + "\n")
                    rejected_written += 1
                else:
                    counts.error += 1
                    per_video[video_id].error += 1
                    per_segment[segment_id].error += 1

                score_cell = "" if score is None else f"{score:.10g}"
                results_writer.writerow([image_id, rel_path, score_cell, decision, reason])
                results_written += 1
                reporter.item_done(rel_path)
        finally:
            results_file.close()
            manifest_file.close()
            rejected_file.close()

        # Consistency checks and artifact finalization still remain.
        reporter.finalizing("Finalizing outputs…")

        if counts.input != source.expected_image_count:
            raise DatasetValidationError(
                "Full source manifest row count does not match extraction run "
                f"image count: manifest={counts.input}, "
                f"run.counts.{IMAGE_COUNT_FIELD}={source.expected_image_count}. "
                "Refusing to export an incomplete or sample manifest as the full dataset."
            )

        if counts.input != counts.accepted + counts.rejected + counts.error:
            raise DatasetFilterError("Internal count inconsistency before finalization")
        if accepted_written != counts.accepted:
            raise DatasetFilterError(
                f"Accepted manifest rows ({accepted_written}) != accepted_count "
                f"({counts.accepted})"
            )
        if rejected_written != counts.rejected:
            raise DatasetFilterError(
                f"rejected.txt paths ({rejected_written}) != rejected_count "
                f"({counts.rejected})"
            )
        if results_written != counts.input:
            raise DatasetFilterError(
                f"results.csv data rows ({results_written}) != input_count ({counts.input})"
            )

        mapping_kept = _write_mapping(mapping_out_path, source, accepted_video_ids)
        if mapping_kept != len(accepted_video_ids):
            raise DatasetFilterError(
                "Filtered mapping entry count does not agree with accepted videos"
            )

        # Guard against accidental image materialization in the metadata output.
        if (out / "images").exists():
            raise DatasetFilterError("Output must not contain an images/ directory")

        status = "completed_with_errors" if counts.error > 0 else "completed"
        report = _build_success_report(
            source=source,
            config=config,
            counts=counts,
            per_video=dict(per_video),
            per_segment=dict(per_segment),
            status=status,
        )
        (out / "run.json").write_text(
            json.dumps(report, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        write_run_info_from_report(out, report)
        reporter.completed()

        return FilterResult(
            output_dir=out,
            status=status,
            counts=counts,
            source=source,
            run_report=report,
        )
    except (DatasetValidationError, DatasetFilterError, OSError, ValueError) as exc:
        reporter.failed(f"Failed: {exc}")
        if started:
            try:
                _write_failed_report(
                    out,
                    config=config,
                    source=source,
                    message=str(exc),
                    counts=counts if counts.input else None,
                )
            except OSError:
                pass
        if isinstance(exc, DatasetFilterError):
            raise
        raise DatasetFilterError(str(exc)) from exc
