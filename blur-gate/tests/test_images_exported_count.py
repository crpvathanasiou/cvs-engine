"""Tests for canonical counts.images_exported handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blur_gate.dataset_source import DatasetValidationError, open_source_dataset
from tests.fixture_dataset import (
    build_source_dataset,
    make_record,
    make_segment,
    make_video,
    write_textured_jpeg,
)


def _minimal(root: Path, counts: dict[str, object]) -> Path:
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
    build_source_dataset(
        root,
        records=records,
        videos=[make_video("vidA", "origA.mp4")],
        segments=[
            make_segment(
                segment_id="segA1",
                video_id="vidA",
                video_filename="origA.mp4",
                excel_row=11,
                start_seconds=0.0,
                end_seconds=10.0,
            )
        ],
        mapping=[("origA.mp4", "images/vidA")],
        counts_images_exported=1,
    )
    run_path = root / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["counts"] = counts
    run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    write_textured_jpeg(root / "images/vidA/segA1/f1.jpg", seed=1)
    return root


def test_images_exported_required(tmp_path: Path) -> None:
    source = _minimal(tmp_path / "source", {"images": 1})
    with pytest.raises(DatasetValidationError, match="images_exported"):
        open_source_dataset(source)


def test_images_exported_rejects_bool_and_float(tmp_path: Path) -> None:
    source = _minimal(tmp_path / "source", {"images_exported": True})
    with pytest.raises(DatasetValidationError, match="nonnegative integer"):
        open_source_dataset(source)

    source2 = _minimal(tmp_path / "source2", {"images_exported": 1.5})
    with pytest.raises(DatasetValidationError, match="nonnegative integer"):
        open_source_dataset(source2)


def test_images_exported_accepts_zero(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    build_source_dataset(
        root,
        records=[],
        videos=[make_video("vidA", "origA.mp4")],
        segments=[
            make_segment(
                segment_id="segA1",
                video_id="vidA",
                video_filename="origA.mp4",
                excel_row=11,
                start_seconds=0.0,
                end_seconds=10.0,
                exported_count=0,
            )
        ],
        mapping=[("origA.mp4", "images/vidA")],
        counts_images_exported=0,
    )
    info = open_source_dataset(root)
    assert info.expected_image_count == 0
