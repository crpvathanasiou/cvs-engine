"""Regression tests for contradictory manifest/reference validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from blur_gate.config import make_config
from blur_gate.dataset_filter import DatasetFilterError, filter_dataset
from blur_gate.dataset_source import DatasetValidationError, open_source_dataset
from tests.fixture_dataset import (
    build_source_dataset,
    make_record,
    make_segment,
    make_video,
    write_textured_jpeg,
)


def _base_parts() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    videos = [make_video("vidA", "origA.mp4")]
    segments = [
        make_segment(
            segment_id="segA1",
            video_id="vidA",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
        )
    ]
    records = [
        make_record(
            image_id="img1",
            video_id="vidA",
            segment_id="segA1",
            filename="f1.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            timestamp=1.0,
        )
    ]
    return videos, segments, records


def _build(
    root: Path,
    *,
    records: list[dict[str, Any]] | None = None,
    videos: list[dict[str, Any]] | None = None,
    segments: list[dict[str, Any]] | None = None,
    mapping: list[tuple[str, str]] | None = None,
) -> Path:
    base_videos, base_segments, base_records = _base_parts()
    build_source_dataset(
        root,
        records=records if records is not None else base_records,
        videos=videos if videos is not None else base_videos,
        segments=segments if segments is not None else base_segments,
        mapping=mapping if mapping is not None else [("origA.mp4", "images/vidA")],
    )
    # Write image for the default path if present.
    for record in records if records is not None else base_records:
        path = root / str(record["path"])
        if not path.exists():
            write_textured_jpeg(path, seed=1)
    return root


def _expect_validation_failure(tmp_path: Path, mutate: Any, match: str) -> None:
    videos, segments, records = _base_parts()
    mutate(videos, segments, records)
    source = _build(tmp_path / "source", records=records, videos=videos, segments=segments)
    out = tmp_path / "out"
    with pytest.raises(DatasetFilterError, match=match):
        filter_dataset(source, out, make_config(1.0))


def test_reject_wrong_video_filename(tmp_path: Path) -> None:
    def mutate(
        _videos: list[dict[str, Any]],
        _segments: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> None:
        records[0]["video_filename"] = "wrong_video.mp4"

    _expect_validation_failure(tmp_path, mutate, "video_filename")


def test_reject_wrong_excel_row(tmp_path: Path) -> None:
    def mutate(
        _videos: list[dict[str, Any]],
        _segments: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> None:
        records[0]["excel_row"] = 999999

    _expect_validation_failure(tmp_path, mutate, "excel_row")


def test_reject_wrong_start_seconds(tmp_path: Path) -> None:
    def mutate(
        _videos: list[dict[str, Any]],
        _segments: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> None:
        records[0]["start_seconds"] = 999999.0
        records[0]["timestamp"] = 999999.5
        records[0]["end_seconds"] = 1000000.0

    _expect_validation_failure(tmp_path, mutate, "start_seconds")


def test_reject_timestamp_outside_interval(tmp_path: Path) -> None:
    def mutate(
        _videos: list[dict[str, Any]],
        _segments: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> None:
        records[0]["timestamp"] = 999999.0

    _expect_validation_failure(tmp_path, mutate, "timestamp must lie within")


def test_reject_non_numeric_timestamp(tmp_path: Path) -> None:
    def mutate(
        _videos: list[dict[str, Any]],
        _segments: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> None:
        records[0]["timestamp"] = "not-a-time"

    _expect_validation_failure(tmp_path, mutate, "timestamp must be a finite number")


def test_reject_incorrect_mapping_filename(tmp_path: Path) -> None:
    videos, segments, records = _base_parts()
    source = _build(
        tmp_path / "source",
        records=records,
        videos=videos,
        segments=segments,
        mapping=[("other.mp4", "images/vidA")],
    )
    with pytest.raises(DatasetValidationError, match="OriginalVideo"):
        open_source_dataset(source)


def test_reject_path_outside_segment_directory(tmp_path: Path) -> None:
    def mutate(
        _videos: list[dict[str, Any]],
        _segments: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> None:
        records[0]["path"] = "images/vidA/other_seg/f1.jpg"

    videos, segments, records = _base_parts()
    mutate(videos, segments, records)
    source = tmp_path / "source"
    build_source_dataset(
        source,
        records=records,
        videos=videos,
        segments=segments,
        mapping=[("origA.mp4", "images/vidA")],
    )
    write_textured_jpeg(source / "images/vidA/other_seg/f1.jpg", seed=1)
    out = tmp_path / "out"
    with pytest.raises(DatasetFilterError, match="must be under"):
        filter_dataset(source, out, make_config(1.0))


def test_valid_record_still_passes(tmp_path: Path) -> None:
    source = _build(tmp_path / "source")
    out = tmp_path / "out"
    result = filter_dataset(source, out, make_config(1.0))
    assert result.status in {"completed", "completed_with_errors"}
    assert result.counts.input == 1
    report = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert report["status"] != "failed"
