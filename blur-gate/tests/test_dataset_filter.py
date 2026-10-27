"""Integration tests for manifest-driven metadata-only dataset filtering."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from blur_gate.config import BlurGateConfig, make_config
from blur_gate.dataset_filter import DatasetFilterError, filter_dataset
from blur_gate.dataset_source import open_source_dataset
from blur_gate.hashing import sha256_file
from blur_gate.paths import resolve_under_root
from blur_gate.scoring import METHOD_NAME, PREPROCESSING_VERSION
from tests.fixture_dataset import (
    build_source_dataset,
    make_record,
    make_segment,
    make_video,
    write_constant_jpeg,
    write_corrupt_jpeg,
    write_textured_jpeg,
)


def _mixed_dataset(root: Path, *, write_bom_mapping: bool = False) -> Path:
    videos = [
        make_video("vidA", "origA.mp4"),
        make_video("vidB", "origB.mp4"),
    ]
    segments = [
        make_segment(
            segment_id="segA1",
            video_id="vidA",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            requested_count=2,
            exported_count=2,
        ),
        make_segment(
            segment_id="segA2",
            video_id="vidA",
            video_filename="origA.mp4",
            excel_row=12,
            start_seconds=10.0,
            end_seconds=20.0,
            requested_count=1,
            exported_count=1,
        ),
        make_segment(
            segment_id="segB1",
            video_id="vidB",
            video_filename="origB.mp4",
            excel_row=21,
            start_seconds=0.0,
            end_seconds=15.0,
            requested_count=2,
            exported_count=2,
        ),
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
            frame_index=1,
            timestamp=1.0,
            extra={"custom_field": "preserve-me"},
        ),
        make_record(
            image_id="img2",
            video_id="vidA",
            segment_id="segA1",
            filename="f2.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            frame_index=2,
            timestamp=2.0,
        ),
        make_record(
            image_id="img3",
            video_id="vidA",
            segment_id="segA2",
            filename="f3.jpg",
            video_filename="origA.mp4",
            excel_row=12,
            start_seconds=10.0,
            end_seconds=20.0,
            frame_index=3,
            timestamp=11.0,
        ),
        make_record(
            image_id="img4",
            video_id="vidB",
            segment_id="segB1",
            filename="f4.jpg",
            video_filename="origB.mp4",
            excel_row=21,
            start_seconds=0.0,
            end_seconds=15.0,
            frame_index=4,
            timestamp=4.0,
        ),
        make_record(
            image_id="img5",
            video_id="vidB",
            segment_id="segB1",
            filename="f5.jpg",
            video_filename="origB.mp4",
            excel_row=21,
            start_seconds=0.0,
            end_seconds=15.0,
            frame_index=5,
            timestamp=5.0,
        ),
    ]
    build_source_dataset(
        root,
        records=records,
        videos=videos,
        segments=segments,
        mapping=[
            ("origA.mp4", "images/vidA"),
            ("origB.mp4", "images/vidB"),
        ],
        extraction_status="partial",
        write_bom_mapping=write_bom_mapping,
    )
    write_textured_jpeg(root / "images/vidA/segA1/f1.jpg", seed=1)
    write_constant_jpeg(root / "images/vidA/segA1/f2.jpg", value=128)
    write_constant_jpeg(root / "images/vidA/segA2/f3.jpg", value=64)
    write_textured_jpeg(root / "images/vidB/segB1/f4.jpg", seed=2)
    write_corrupt_jpeg(root / "images/vidB/segB1/f5.jpg")
    return root


def test_filter_mixed_accept_reject_error_and_preservation(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "source")
    before_manifest = (source / "manifest.jsonl").read_bytes()
    before_run = (source / "run.json").read_bytes()
    before_map = (source / "video-folder-mapping.csv").read_bytes()
    before_img = (source / "images/vidA/segA1/f1.jpg").read_bytes()
    img_hash = sha256_file(source / "images/vidA/segA1/f1.jpg")

    out = tmp_path / "meta_out"
    result = filter_dataset(source, out, make_config(50.0))

    assert result.status == "completed_with_errors"
    assert result.counts.input == 5
    assert result.counts.accepted + result.counts.rejected + result.counts.error == 5
    assert result.counts.error == 1
    assert result.counts.accepted >= 1
    assert result.counts.rejected >= 1

    assert (source / "manifest.jsonl").read_bytes() == before_manifest
    assert (source / "run.json").read_bytes() == before_run
    assert (source / "video-folder-mapping.csv").read_bytes() == before_map
    assert (source / "images/vidA/segA1/f1.jpg").read_bytes() == before_img
    assert sha256_file(source / "images/vidA/segA1/f1.jpg") == img_hash
    assert not (out / "images").exists()

    accepted = [
        json.loads(line)
        for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(accepted) == result.counts.accepted
    for record in accepted:
        assert record["path"].startswith("images/")
        assert (source / record["path"]).is_file()
        assert not (out / record["path"]).exists()

    accepted_ids = [str(row["image_id"]) for row in accepted]
    expected_order = [
        image_id
        for image_id in ["img1", "img2", "img3", "img4", "img5"]
        if image_id in accepted_ids
    ]
    assert accepted_ids == expected_order

    report = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert report["pipeline_name"] == "blur_filtering"
    assert report["status"] == "completed_with_errors"
    assert report["source_dataset"]["extraction_status"] == "partial"
    assert report["blur_gate"]["method"] == METHOD_NAME
    assert report["blur_gate"]["preprocessing_version"] == PREPROCESSING_VERSION

    seg_a2 = next(s for s in report["segments"] if s["segment_id"] == "segA2")
    assert seg_a2["counts"]["accepted"] == 0
    assert seg_a2["usable"] is False

    rejected_file = out / "rejected.txt"
    assert rejected_file.is_file()
    rejected_lines = [
        line for line in rejected_file.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(rejected_lines) == result.counts.rejected

    expected_rejected_abs: list[str] = []
    with (out / "results.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            decision = str(row["decision"])
            rel = str(row["path"])
            if decision == "reject":
                expected_rejected_abs.append(
                    str(resolve_under_root(source.resolve(), rel))
                )
            else:
                assert decision in {"accept", "error"}
    assert rejected_lines == expected_rejected_abs
    for absolute in rejected_lines:
        path = Path(absolute)
        assert path.is_absolute()
        assert path.is_file()
        assert path.resolve().is_relative_to(source.resolve())


def test_schema_v2_images_exported_and_bom_mapping(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "source", write_bom_mapping=True)
    info = open_source_dataset(source)
    assert info.expected_image_count == 5
    assert info.source_counts["images_exported"] == 5
    assert info.run["schema_version"] == "2"
    assert info.run["pipeline_name"] == "frame_extraction"

    # Non-BOM mapping also works.
    source2 = _mixed_dataset(tmp_path / "source2", write_bom_mapping=False)
    info2 = open_source_dataset(source2)
    assert info2.expected_image_count == 5

    out = tmp_path / "out"
    result = filter_dataset(source, out, make_config(50.0))
    assert result.counts.input == 5


def test_sample_count_mismatch_against_full_export_count(tmp_path: Path) -> None:
    source = tmp_path / "source"
    record = make_record(
        image_id="only",
        video_id="vidA",
        segment_id="segA1",
        filename="f1.jpg",
        video_filename="origA.mp4",
        excel_row=11,
        start_seconds=0.0,
        end_seconds=10.0,
        timestamp=1.0,
    )
    build_source_dataset(
        source,
        records=[record],
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
        counts_images_exported=72273,
        extraction_status="partial",
    )
    write_textured_jpeg(source / "images/vidA/segA1/f1.jpg", seed=3)

    # Opening/indexing succeeds with the real count field.
    info = open_source_dataset(source)
    assert info.expected_image_count == 72273

    out = tmp_path / "out"
    with pytest.raises(DatasetFilterError, match="images_exported"):
        filter_dataset(source, out, make_config(1.0))
    report = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"


def test_output_outside_source_still_resolves(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "src")
    out = tmp_path / "elsewhere" / "filter_meta"
    result = filter_dataset(source, out, make_config(50.0))
    accepted = [
        json.loads(line)
        for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert accepted
    for record in accepted:
        assert (source / record["path"]).is_file()
    assert result.output_dir == out.resolve()


def test_duplicate_image_id_fails(tmp_path: Path) -> None:
    source = tmp_path / "source"
    r1 = make_record(
        image_id="dup",
        video_id="vidA",
        segment_id="segA1",
        filename="a.jpg",
        video_filename="origA.mp4",
        excel_row=11,
        start_seconds=0.0,
        end_seconds=10.0,
        timestamp=1.0,
    )
    r2 = make_record(
        image_id="dup",
        video_id="vidA",
        segment_id="segA1",
        filename="b.jpg",
        video_filename="origA.mp4",
        excel_row=11,
        start_seconds=0.0,
        end_seconds=10.0,
        timestamp=2.0,
        frame_index=1,
    )
    build_source_dataset(
        source,
        records=[r1, r2],
        videos=[make_video("vidA", "origA.mp4")],
        segments=[
            make_segment(
                segment_id="segA1",
                video_id="vidA",
                video_filename="origA.mp4",
                excel_row=11,
                start_seconds=0.0,
                end_seconds=10.0,
                exported_count=2,
            )
        ],
        mapping=[("origA.mp4", "images/vidA")],
    )
    write_textured_jpeg(source / "images/vidA/segA1/a.jpg", seed=1)
    write_textured_jpeg(source / "images/vidA/segA1/b.jpg", seed=2)
    out = tmp_path / "out"
    with pytest.raises(DatasetFilterError, match="Duplicate image_id"):
        filter_dataset(source, out, make_config(1.0))


def test_refuse_nonempty_output_and_no_source_overwrite(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "source")
    out = tmp_path / "out"
    out.mkdir()
    (out / "preexisting.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(DatasetFilterError, match="not empty"):
        filter_dataset(source, out, make_config(50.0))
    assert (out / "preexisting.txt").read_text(encoding="utf-8") == "nope"
    with pytest.raises(DatasetFilterError, match="source dataset root"):
        filter_dataset(source, source, make_config(50.0))


def test_no_copied_images_directory(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "source")
    out = tmp_path / "meta"
    filter_dataset(source, out, make_config(50.0))
    assert list(out.glob("images/**/*")) == []
    image_suffixes = {".jpg", ".jpeg", ".png"}
    assert not any(
        p.is_file() and p.suffix.lower() in image_suffixes for p in out.rglob("*")
    )


def test_incompatible_config_rejected_before_outputs(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "source")
    out = tmp_path / "out"
    bad = BlurGateConfig(
        method="other_method",
        threshold=10.0,
        preprocessing_version="other_preprocessing",
    )
    with pytest.raises(DatasetFilterError, match="Incompatible method"):
        filter_dataset(source, out, bad)
    assert not out.exists()

    bad_thresh = BlurGateConfig(
        method=METHOD_NAME,
        threshold=-1.0,
        preprocessing_version=PREPROCESSING_VERSION,
    )
    with pytest.raises(DatasetFilterError, match="threshold"):
        filter_dataset(source, out, bad_thresh)
    assert not out.exists()


def test_rejected_txt_empty_when_nothing_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    record = make_record(
        image_id="only",
        video_id="vidA",
        segment_id="segA1",
        filename="f1.jpg",
        video_filename="origA.mp4",
        excel_row=11,
        start_seconds=0.0,
        end_seconds=10.0,
        timestamp=1.0,
    )
    build_source_dataset(
        source,
        records=[record],
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
    )
    write_textured_jpeg(source / "images/vidA/segA1/f1.jpg", seed=3)
    out = tmp_path / "out"
    result = filter_dataset(source, out, make_config(0.0))
    assert result.counts.rejected == 0
    assert result.counts.accepted == 1
    rejected = out / "rejected.txt"
    assert rejected.is_file()
    assert rejected.read_text(encoding="utf-8") == ""


def test_rejected_txt_excludes_errors_and_keeps_manifest_order(tmp_path: Path) -> None:
    source = _mixed_dataset(tmp_path / "source")
    out = tmp_path / "out"
    # Very high threshold → textured images still may accept or reject depending on
    # score; use a threshold that rejects constants but keeps checking error exclusion.
    result = filter_dataset(source, out, make_config(1e12))
    assert result.counts.error == 1
    rejected_lines = [
        line
        for line in (out / "rejected.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rejected_lines) == result.counts.rejected
    assert result.counts.accepted == 0
    # Corrupt image is an error, not a reject path.
    for absolute in rejected_lines:
        assert "f5.jpg" not in absolute
        assert Path(absolute).is_absolute()
        assert Path(absolute).is_file()
