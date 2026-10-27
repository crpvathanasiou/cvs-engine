"""Source extraction dataset contract validation (manifest-driven)."""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, cast

from blur_gate.hashing import sha256_file
from blur_gate.paths import UnsafePathError, resolve_under_root

REQUIRED_SOURCE_FILES = ("run.json", "manifest.jsonl", "video-folder-mapping.csv")

REQUIRED_MANIFEST_FIELDS = (
    "image_id",
    "video_id",
    "segment_id",
    "frame_index",
    "timestamp",
    "path",
    "video_filename",
    "workbook_sheet",
    "excel_row",
    "start_seconds",
    "end_seconds",
    "image_format",
    "width",
    "height",
)

REQUIRED_SEGMENT_FIELDS = (
    "segment_id",
    "video_id",
    "video_filename",
    "excel_row",
    "start_seconds",
    "end_seconds",
    "requested_count",
    "exported_count",
)

MAPPING_COLUMNS = ("OriginalVideo", "ImageFolder")
IMAGE_COUNT_FIELD = "images_exported"


class DatasetValidationError(ValueError):
    """Malformed records or contradictory source dataset metadata."""


@dataclass(frozen=True, slots=True)
class SourceMappingRow:
    original_video: str
    image_folder: str


@dataclass(frozen=True, slots=True)
class SourceDatasetInfo:
    root: Path
    run: dict[str, Any]
    mapping_rows: list[SourceMappingRow]
    video_ids: frozenset[str]
    segment_ids: frozenset[str]
    segment_to_video: dict[str, str]
    mapping_by_video: dict[str, str]
    mapping_original_by_video: dict[str, str]
    videos_by_id: dict[str, dict[str, Any]]
    segments_by_id: dict[str, dict[str, Any]]
    manifest_path: Path
    run_path: Path
    mapping_path: Path
    manifest_sha256: str
    run_sha256: str
    mapping_sha256: str
    expected_image_count: int
    extraction_status: str
    workbook: dict[str, Any] = field(default_factory=lambda: {})
    source_counts: dict[str, Any] = field(default_factory=lambda: {})
    videos_meta: list[dict[str, Any]] = field(
        default_factory=lambda: cast(list[dict[str, Any]], [])
    )
    segments_meta: list[dict[str, Any]] = field(
        default_factory=lambda: cast(list[dict[str, Any]], [])
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"Malformed JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise DatasetValidationError(f"Expected JSON object in {path}")
    return cast(dict[str, Any], raw)


def _require_nonneg_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DatasetValidationError(f"{label} must be a nonnegative integer")
    if value < 0:
        raise DatasetValidationError(f"{label} must be a nonnegative integer")
    return value


def _require_int(value: object, label: str, *, min_value: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DatasetValidationError(f"{label} must be an integer")
    if min_value is not None and value < min_value:
        raise DatasetValidationError(f"{label} must be >= {min_value}")
    return value


def _require_finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DatasetValidationError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise DatasetValidationError(f"{label} must be a finite number")
    return number


def _require_nonempty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{label} must be a nonempty string")
    return value


def _expected_image_count(run: Mapping[str, Any]) -> int:
    """Read canonical extraction image count from ``counts.images_exported``."""
    counts = run.get("counts")
    if not isinstance(counts, dict):
        raise DatasetValidationError("run.json missing counts object")
    counts_map = cast(dict[str, object], counts)
    if IMAGE_COUNT_FIELD not in counts_map:
        raise DatasetValidationError(
            f"run.json counts must include {IMAGE_COUNT_FIELD}"
        )
    return _require_nonneg_int(
        counts_map[IMAGE_COUNT_FIELD], f"counts.{IMAGE_COUNT_FIELD}"
    )


def _source_filenames(video: Mapping[str, Any]) -> list[str]:
    raw = video.get("source_filenames")
    if not isinstance(raw, list) or not raw:
        raise DatasetValidationError(
            f"Video {video.get('video_id')!r} requires nonempty source_filenames"
        )
    names: list[str] = []
    for item in cast(list[object], raw):
        names.append(_require_nonempty_str(item, "source_filenames entry"))
    return names


def _index_videos_segments(
    run: Mapping[str, Any],
) -> tuple[
    frozenset[str],
    frozenset[str],
    dict[str, str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    videos_raw = run.get("videos", [])
    segments_raw = run.get("segments", [])
    if not isinstance(videos_raw, list) or not isinstance(segments_raw, list):
        raise DatasetValidationError("run.json videos/segments must be lists")

    videos_meta: list[dict[str, Any]] = []
    videos_by_id: dict[str, dict[str, Any]] = {}
    video_ids: set[str] = set()
    for item_obj in cast(list[object], videos_raw):
        if not isinstance(item_obj, dict) or "video_id" not in item_obj:
            raise DatasetValidationError("Each run.json video requires video_id")
        item = cast(dict[str, Any], item_obj)
        vid = _require_nonempty_str(item["video_id"], "video_id")
        if vid in video_ids:
            raise DatasetValidationError(f"Duplicate video_id in run.json: {vid}")
        _source_filenames(item)
        video_ids.add(vid)
        videos_meta.append(dict(item))
        videos_by_id[vid] = dict(item)

    segments_meta: list[dict[str, Any]] = []
    segments_by_id: dict[str, dict[str, Any]] = {}
    segment_ids: set[str] = set()
    segment_to_video: dict[str, str] = {}
    for item_obj in cast(list[object], segments_raw):
        if not isinstance(item_obj, dict):
            raise DatasetValidationError("Each run.json segment must be an object")
        item = cast(dict[str, Any], item_obj)
        missing = [key for key in REQUIRED_SEGMENT_FIELDS if key not in item]
        if missing:
            raise DatasetValidationError(
                f"Each segment requires fields: {', '.join(REQUIRED_SEGMENT_FIELDS)}"
            )
        sid = _require_nonempty_str(item["segment_id"], "segment_id")
        vid = _require_nonempty_str(item["video_id"], "segment video_id")
        _require_nonempty_str(item["video_filename"], "segment video_filename")
        _require_int(item["excel_row"], "segment excel_row", min_value=1)
        start = _require_finite_number(item["start_seconds"], "segment start_seconds")
        end = _require_finite_number(item["end_seconds"], "segment end_seconds")
        if not (start < end):
            raise DatasetValidationError(
                f"Segment {sid} requires start_seconds < end_seconds"
            )
        _require_nonneg_int(item["requested_count"], "segment requested_count")
        _require_nonneg_int(item["exported_count"], "segment exported_count")
        if sid in segment_ids:
            raise DatasetValidationError(f"Duplicate segment_id in run.json: {sid}")
        if vid not in video_ids:
            raise DatasetValidationError(
                f"Segment {sid} references unknown video_id {vid}"
            )
        segment_ids.add(sid)
        segment_to_video[sid] = vid
        segments_meta.append(dict(item))
        segments_by_id[sid] = dict(item)

    return (
        frozenset(video_ids),
        frozenset(segment_ids),
        segment_to_video,
        videos_by_id,
        segments_by_id,
        videos_meta,
        segments_meta,
    )


def load_mapping_csv(path: Path) -> list[SourceMappingRow]:
    """Load mapping CSV with BOM-tolerant UTF-8 (utf-8-sig)."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DatasetValidationError("video-folder-mapping.csv has no header")
        # Normalize possible residual BOM on first header just in case.
        fields = tuple(name.lstrip("\ufeff") for name in reader.fieldnames)
        if fields != MAPPING_COLUMNS:
            raise DatasetValidationError(
                "video-folder-mapping.csv must have exact columns "
                f"{MAPPING_COLUMNS}, found {fields}"
            )
        rows: list[SourceMappingRow] = []
        for row in reader:
            # DictReader keys may still include BOM on first field without utf-8-sig;
            # with utf-8-sig they are clean. Prefer canonical names.
            original_raw = row.get("OriginalVideo")
            folder_raw = row.get("ImageFolder")
            if original_raw is None:
                # Fallback if first key retained a BOM somehow.
                for key, value in row.items():
                    if key.lstrip("\ufeff") == "OriginalVideo":
                        original_raw = value
                    elif key == "ImageFolder":
                        folder_raw = value
            original = str(original_raw or "").strip()
            folder = str(folder_raw or "").strip().replace("\\", "/")
            if not original or not folder:
                raise DatasetValidationError(
                    "Mapping rows require OriginalVideo and ImageFolder"
                )
            rows.append(SourceMappingRow(original_video=original, image_folder=folder))
    return rows


def iter_manifest_records(manifest_path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSONL records incrementally without loading the full file."""
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                raw: object = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(
                    f"Malformed JSONL at {manifest_path}:{line_no}"
                ) from exc
            if not isinstance(raw, dict):
                raise DatasetValidationError(
                    f"Manifest record at line {line_no} must be a JSON object"
                )
            yield cast(dict[str, Any], raw)


def validate_manifest_record(
    record: Mapping[str, Any],
    *,
    source: SourceDatasetInfo,
    seen_image_ids: set[str],
    seen_paths: set[str],
) -> str:
    """Validate one record against source metadata before scoring."""
    missing = [key for key in REQUIRED_MANIFEST_FIELDS if key not in record]
    if missing:
        raise DatasetValidationError(
            f"Manifest record missing fields: {', '.join(missing)}"
        )

    image_id = _require_nonempty_str(record["image_id"], "image_id")
    rel_path = _require_nonempty_str(record["path"], "path").replace("\\", "/")
    video_id = _require_nonempty_str(record["video_id"], "video_id")
    segment_id = _require_nonempty_str(record["segment_id"], "segment_id")
    video_filename = _require_nonempty_str(record["video_filename"], "video_filename")
    workbook_sheet = _require_nonempty_str(record["workbook_sheet"], "workbook_sheet")
    image_format = _require_nonempty_str(record["image_format"], "image_format")
    _ = image_format  # validated nonempty; format values are preserved as-is

    frame_index = _require_int(record["frame_index"], "frame_index", min_value=0)
    excel_row = _require_int(record["excel_row"], "excel_row", min_value=1)
    width = _require_int(record["width"], "width", min_value=1)
    height = _require_int(record["height"], "height", min_value=1)
    _ = (frame_index, width, height)

    timestamp = _require_finite_number(record["timestamp"], "timestamp")
    start_seconds = _require_finite_number(record["start_seconds"], "start_seconds")
    end_seconds = _require_finite_number(record["end_seconds"], "end_seconds")
    if not (start_seconds < end_seconds):
        raise DatasetValidationError(
            f"Record {image_id} requires start_seconds < end_seconds"
        )
    if not (start_seconds <= timestamp < end_seconds):
        raise DatasetValidationError(
            f"Record {image_id} timestamp must lie within "
            f"[start_seconds, end_seconds); got {timestamp}"
        )

    if image_id in seen_image_ids:
        raise DatasetValidationError(f"Duplicate image_id: {image_id}")
    if rel_path in seen_paths:
        raise DatasetValidationError(f"Duplicate image path: {rel_path}")
    seen_image_ids.add(image_id)
    seen_paths.add(rel_path)

    if video_id not in source.video_ids:
        raise DatasetValidationError(
            f"Record {image_id} references unknown video_id {video_id}"
        )
    if segment_id not in source.segment_ids:
        raise DatasetValidationError(
            f"Record {image_id} references unknown segment_id {segment_id}"
        )
    if source.segment_to_video.get(segment_id) != video_id:
        raise DatasetValidationError(
            f"Record {image_id} segment/video mismatch for {segment_id}/{video_id}"
        )

    segment = source.segments_by_id[segment_id]
    video = source.videos_by_id[video_id]

    if str(segment["video_filename"]) != video_filename:
        raise DatasetValidationError(
            f"Record {image_id} video_filename {video_filename!r} does not match "
            f"segment video_filename {segment['video_filename']!r}"
        )
    if int(segment["excel_row"]) != excel_row:
        raise DatasetValidationError(
            f"Record {image_id} excel_row {excel_row} does not match "
            f"segment excel_row {segment['excel_row']}"
        )
    if float(segment["start_seconds"]) != start_seconds:
        raise DatasetValidationError(
            f"Record {image_id} start_seconds does not match referenced segment"
        )
    if float(segment["end_seconds"]) != end_seconds:
        raise DatasetValidationError(
            f"Record {image_id} end_seconds does not match referenced segment"
        )

    workbook_sheet_expected = source.workbook.get("sheet")
    if workbook_sheet_expected is not None and str(workbook_sheet_expected) != workbook_sheet:
        raise DatasetValidationError(
            f"Record {image_id} workbook_sheet {workbook_sheet!r} does not match "
            f"workbook.sheet {workbook_sheet_expected!r}"
        )

    if video_id not in source.mapping_by_video:
        raise DatasetValidationError(
            f"Record {image_id} video_id {video_id} missing from video-folder-mapping.csv"
        )

    folder = source.mapping_by_video[video_id]
    expected_prefix = f"images/{video_id}/{segment_id}/"
    if not rel_path.startswith(expected_prefix):
        raise DatasetValidationError(
            f"Record {image_id} path {rel_path} must be under {expected_prefix}"
        )
    mapped_prefix = folder.rstrip("/") + "/"
    if not rel_path.startswith(mapped_prefix):
        raise DatasetValidationError(
            f"Record {image_id} path {rel_path} is outside mapped folder {folder}"
        )

    original_video = source.mapping_original_by_video[video_id]
    source_names = [str(name) for name in cast(list[object], video["source_filenames"])]
    if original_video not in source_names:
        raise DatasetValidationError(
            f"Mapping OriginalVideo {original_video!r} for {video_id} is not listed in "
            f"video source_filenames {source_names}"
        )
    if video_filename not in source_names:
        raise DatasetValidationError(
            f"Record {image_id} video_filename {video_filename!r} is not listed in "
            f"video source_filenames {source_names}"
        )
    if original_video != video_filename:
        raise DatasetValidationError(
            f"Record {image_id} video_filename {video_filename!r} does not agree with "
            f"mapping OriginalVideo {original_video!r}"
        )

    try:
        resolve_under_root(source.root, rel_path)
    except UnsafePathError as exc:
        raise DatasetValidationError(str(exc)) from exc

    return rel_path


def open_source_dataset(root: Path | str) -> SourceDatasetInfo:
    """Validate required source files and index metadata (not the full image bytes)."""
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise DatasetValidationError(f"Source dataset root is not a directory: {root_path}")

    for name in REQUIRED_SOURCE_FILES:
        if not (root_path / name).is_file():
            raise DatasetValidationError(f"Missing required source file: {name}")

    run_path = root_path / "run.json"
    manifest_path = root_path / "manifest.jsonl"
    mapping_path = root_path / "video-folder-mapping.csv"

    run = _load_json(run_path)
    expected_image_count = _expected_image_count(run)
    (
        video_ids,
        segment_ids,
        segment_to_video,
        videos_by_id,
        segments_by_id,
        videos_meta,
        segments_meta,
    ) = _index_videos_segments(run)
    mapping_rows = load_mapping_csv(mapping_path)

    mapping_by_video: dict[str, str] = {}
    mapping_original_by_video: dict[str, str] = {}
    for row in mapping_rows:
        folder = row.image_folder.replace("\\", "/").rstrip("/")
        video_key = PurePosixPath(folder).name
        if video_key in mapping_by_video:
            raise DatasetValidationError(f"Duplicate mapping for video folder {folder}")
        mapping_by_video[video_key] = folder
        mapping_original_by_video[video_key] = row.original_video

    for vid in video_ids:
        if vid not in mapping_by_video:
            raise DatasetValidationError(
                f"run.json video_id {vid} missing from video-folder-mapping.csv folders"
            )
        video = videos_by_id[vid]
        original = mapping_original_by_video[vid]
        names = [str(name) for name in cast(list[object], video["source_filenames"])]
        if original not in names:
            raise DatasetValidationError(
                f"Mapping OriginalVideo {original!r} for {vid} is not listed in "
                f"source_filenames {names}"
            )

    workbook_obj = run.get("workbook")
    workbook: dict[str, Any] = (
        dict(cast(dict[str, Any], workbook_obj)) if isinstance(workbook_obj, dict) else {}
    )
    for key in ("path", "sheet", "content_sha256"):
        if key not in workbook:
            raise DatasetValidationError(f"run.json workbook missing {key}")
        _require_nonempty_str(workbook[key], f"workbook.{key}")

    counts_obj = run.get("counts")
    source_counts: dict[str, Any] = (
        dict(cast(dict[str, Any], counts_obj)) if isinstance(counts_obj, dict) else {}
    )
    extraction_status = str(run.get("status", "unknown"))

    return SourceDatasetInfo(
        root=root_path,
        run=run,
        mapping_rows=mapping_rows,
        video_ids=video_ids,
        segment_ids=segment_ids,
        segment_to_video=segment_to_video,
        mapping_by_video=mapping_by_video,
        mapping_original_by_video=mapping_original_by_video,
        videos_by_id=videos_by_id,
        segments_by_id=segments_by_id,
        manifest_path=manifest_path,
        run_path=run_path,
        mapping_path=mapping_path,
        manifest_sha256=sha256_file(manifest_path),
        run_sha256=sha256_file(run_path),
        mapping_sha256=sha256_file(mapping_path),
        expected_image_count=expected_image_count,
        extraction_status=extraction_status,
        workbook=workbook,
        source_counts=source_counts,
        videos_meta=videos_meta,
        segments_meta=segments_meta,
    )
