"""Builders for synthetic extraction-schema fixtures (schema_version 2)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def write_textured_jpeg(path: Path, seed: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    gray = rng.integers(0, 256, size=(48, 48), dtype=np.uint8)
    for i in range(0, 48, 8):
        gray[:, i : i + 4] = 255
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    assert cv2.imwrite(str(path), bgr)


def write_constant_jpeg(path: Path, value: int = 128) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.full((48, 48, 3), value, dtype=np.uint8)
    assert cv2.imwrite(str(path), img)


def write_corrupt_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-a-jpeg")


def build_source_dataset(
    root: Path,
    *,
    records: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    mapping: list[tuple[str, str]],
    extraction_status: str = "partial",
    counts_images_exported: int | None = None,
    workbook: dict[str, Any] | None = None,
    write_bom_mapping: bool = False,
) -> Path:
    """Create a minimal source dataset matching the real frame_extraction schema."""
    root.mkdir(parents=True, exist_ok=True)
    exported = (
        counts_images_exported if counts_images_exported is not None else len(records)
    )
    run = {
        "schema_version": "2",
        "pipeline_name": "frame_extraction",
        "status": extraction_status,
        "workbook": workbook
        or {
            "path": "annotations.xlsx",
            "sheet": "Sheet1",
            "content_sha256": "abc123",
        },
        "videos": videos,
        "segments": segments,
        "counts": {
            "images_exported": exported,
            "segments_planned": len(segments),
            "segments_completed": len(segments),
        },
    }
    (root / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

    with (root / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=False) + "\n")

    mapping_path = root / "video-folder-mapping.csv"
    if write_bom_mapping:
        # UTF-8 BOM + CSV body
        body_lines = ["OriginalVideo,ImageFolder"]
        for original, folder in mapping:
            body_lines.append(f"{original},{folder}")
        mapping_path.write_bytes(("\n".join(body_lines) + "\n").encode("utf-8-sig"))
    else:
        with mapping_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["OriginalVideo", "ImageFolder"])
            writer.writeheader()
            for original, folder in mapping:
                writer.writerow({"OriginalVideo": original, "ImageFolder": folder})

    return root


def make_video(video_id: str, filename: str) -> dict[str, Any]:
    return {"video_id": video_id, "source_filenames": [filename]}


def make_segment(
    *,
    segment_id: str,
    video_id: str,
    video_filename: str,
    excel_row: int,
    start_seconds: float,
    end_seconds: float,
    requested_count: int = 1,
    exported_count: int = 1,
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "video_id": video_id,
        "video_filename": video_filename,
        "excel_row": excel_row,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "requested_count": requested_count,
        "exported_count": exported_count,
    }


def make_record(
    *,
    image_id: str,
    video_id: str,
    segment_id: str,
    filename: str,
    video_filename: str,
    excel_row: int,
    start_seconds: float,
    end_seconds: float,
    frame_index: int = 0,
    timestamp: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if timestamp is None:
        timestamp = float(start_seconds)
    record: dict[str, Any] = {
        "image_id": image_id,
        "video_id": video_id,
        "segment_id": segment_id,
        "frame_index": frame_index,
        "timestamp": timestamp,
        "path": f"images/{video_id}/{segment_id}/{filename}",
        "video_filename": video_filename,
        "workbook_sheet": "Sheet1",
        "excel_row": excel_row,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "image_format": "jpg",
        "width": 48,
        "height": 48,
    }
    if extra:
        record.update(extra)
    return record
