"""Unit tests for blur_gate_info.json create / derive / list behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blur_gate import make_config
from blur_gate.dataset_filter import filter_dataset
from blur_gate.run_info import (
    INFO_FILENAME,
    RunInfoError,
    build_info_from_run_report,
    list_saved_executions,
    load_execution_result,
    load_run_info,
    validate_info_values,
    write_run_info,
)
from blur_gate.scoring import METHOD_NAME, PREPROCESSING_VERSION
from blur_gate.version import __version__
from tests.fixture_dataset import (
    build_source_dataset,
    make_record,
    make_segment,
    make_video,
    write_constant_jpeg,
    write_textured_jpeg,
)


def _tiny_source(root: Path) -> Path:
    records = [
        make_record(
            image_id="sharp",
            video_id="vidA",
            segment_id="segA1",
            filename="sharp.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            timestamp=1.0,
            frame_index=0,
        ),
        make_record(
            image_id="blur",
            video_id="vidA",
            segment_id="segA1",
            filename="blur.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            timestamp=2.0,
            frame_index=1,
        ),
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
                requested_count=2,
                exported_count=2,
            )
        ],
        mapping=[("origA.mp4", "images/vidA")],
    )
    write_textured_jpeg(root / "images/vidA/segA1/sharp.jpg", seed=1)
    write_constant_jpeg(root / "images/vidA/segA1/blur.jpg", value=128)
    return root


def test_filter_writes_blur_gate_info(tmp_path: Path) -> None:
    source = _tiny_source(tmp_path / "source")
    out = tmp_path / "out_info"
    result = filter_dataset(source, out, make_config(50.0))
    info_path = out / INFO_FILENAME
    assert info_path.is_file()
    info = json.loads(info_path.read_text(encoding="utf-8"))
    assert info["status"] == result.status
    assert info["threshold"] == 50.0
    assert info["method"] == METHOD_NAME
    assert info["preprocessing_version"] == PREPROCESSING_VERSION
    assert info["blur_gate_version"] == __version__
    assert Path(info["source_dataset_root"]) == source.resolve()
    assert info["counts"]["input"] == result.counts.input
    assert info["counts"]["accepted"] == result.counts.accepted
    assert info["counts"]["rejected"] == result.counts.rejected
    assert info["counts"]["error"] == result.counts.error


def test_derive_info_from_legacy_run_json_without_overwrite(tmp_path: Path) -> None:
    source = _tiny_source(tmp_path / "source")
    out = tmp_path / "legacy"
    filter_dataset(source, out, make_config(40.0))
    info_path = out / INFO_FILENAME
    assert info_path.is_file()
    original_info = info_path.read_text(encoding="utf-8")
    run_before = (out / "run.json").read_bytes()
    info_path.unlink()

    loaded = load_run_info(out)
    assert info_path.is_file()
    assert loaded["threshold"] == 40.0
    assert loaded["created_at"]
    assert (out / "run.json").read_bytes() == run_before

    # Existing info must not be overwritten.
    info_path.write_text(
        json.dumps({**loaded, "threshold": 999.0}, indent=2) + "\n",
        encoding="utf-8",
    )
    again = load_run_info(out)
    assert again["threshold"] == 999.0
    write_run_info(out, {**loaded, "threshold": 1.0})
    assert json.loads(info_path.read_text(encoding="utf-8"))["threshold"] == 999.0
    assert original_info  # legacy content existed before unlink


def test_failed_status_not_listed_as_viewable(tmp_path: Path) -> None:
    export = tmp_path / "blur_gate_export"
    failed = export / "20260101_000000_failed"
    failed.mkdir(parents=True)
    report = {
        "schema_version": "1.0",
        "pipeline_name": "blur_filtering",
        "created_at": "2026-01-01T00:00:00+00:00",
        "status": "failed",
        "blur_gate": {
            "version": __version__,
            "method": METHOD_NAME,
            "threshold": 10.0,
            "preprocessing_version": PREPROCESSING_VERSION,
        },
        "counts": {"input": 0, "accepted": 0, "rejected": 0, "error": 0},
        "source_dataset": {"root": str(tmp_path / "src")},
    }
    (failed / "run.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    listed = list_saved_executions(export)
    assert listed.executions == []
    assert listed.issues == []
    with pytest.raises(RunInfoError, match="completed"):
        load_execution_result(failed)


def test_list_saved_executions_newest_first(tmp_path: Path) -> None:
    source = _tiny_source(tmp_path / "source")
    export = tmp_path / "export"
    older = export / "20260101_100000_old"
    newer = export / "20260102_100000_new"
    filter_dataset(source, older, make_config(30.0))
    filter_dataset(source, newer, make_config(60.0))
    listed = list_saved_executions(export)
    assert [item.folder_name for item in listed.executions] == [
        "20260102_100000_new",
        "20260101_100000_old",
    ]
    assert listed.issues == []
    assert "threshold=60.0" in listed.executions[0].label
    assert "20260102_100000_new" in listed.executions[0].label


def test_build_info_rejects_incomplete_run(tmp_path: Path) -> None:
    with pytest.raises(RunInfoError, match="blur_gate"):
        build_info_from_run_report({"status": "completed", "created_at": "x"})


def _valid_info(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "1",
        "created_at": "2026-01-01T00:00:00+00:00",
        "status": "completed",
        "threshold": 50.0,
        "method": METHOD_NAME,
        "preprocessing_version": PREPROCESSING_VERSION,
        "blur_gate_version": __version__,
        "source_dataset_root": r"C:\data\source",
        "counts": {"input": 3, "accepted": 1, "rejected": 1, "error": 1},
    }
    base.update(overrides)
    return base


def test_validate_rejects_invalid_count_types_and_negatives() -> None:
    with pytest.raises(RunInfoError, match="nonnegative integer"):
        validate_info_values(
            _valid_info(counts={"input": 1.5, "accepted": 1, "rejected": 0, "error": 0}),
            source_label=INFO_FILENAME,
        )
    with pytest.raises(RunInfoError, match="nonnegative integer"):
        validate_info_values(
            _valid_info(counts={"input": True, "accepted": 0, "rejected": 0, "error": 0}),
            source_label=INFO_FILENAME,
        )
    with pytest.raises(RunInfoError, match="nonnegative integer"):
        validate_info_values(
            _valid_info(counts={"input": -1, "accepted": 0, "rejected": 0, "error": 0}),
            source_label=INFO_FILENAME,
        )
    with pytest.raises(RunInfoError, match="finite nonnegative"):
        validate_info_values(_valid_info(threshold=-1.0), source_label=INFO_FILENAME)


def test_validate_rejects_inconsistent_totals() -> None:
    with pytest.raises(RunInfoError, match="inconsistent"):
        validate_info_values(
            _valid_info(counts={"input": 5, "accepted": 1, "rejected": 1, "error": 1}),
            source_label=INFO_FILENAME,
        )


def test_malformed_json_and_valid_sibling_remain_usable(tmp_path: Path) -> None:
    source = _tiny_source(tmp_path / "source")
    export = tmp_path / "export"
    valid = export / "20260102_100000_good"
    bad = export / "20260101_100000_bad"
    filter_dataset(source, valid, make_config(50.0))
    bad.mkdir(parents=True)
    (bad / INFO_FILENAME).write_text("{not-json", encoding="utf-8")
    before_valid = (valid / INFO_FILENAME).read_text(encoding="utf-8")

    listed = list_saved_executions(export)
    assert [item.folder_name for item in listed.executions] == ["20260102_100000_good"]
    assert len(listed.issues) == 1
    assert "20260101_100000_bad" in listed.issues[0]
    assert "Malformed" in listed.issues[0]

    info, result = load_execution_result(valid)
    assert info["status"] == result["status"]
    assert (valid / INFO_FILENAME).read_text(encoding="utf-8") == before_valid
    assert (bad / INFO_FILENAME).read_text(encoding="utf-8") == "{not-json"

    with pytest.raises(RunInfoError, match="Malformed"):
        load_run_info(bad)


def test_existing_invalid_info_is_not_auto_repaired(tmp_path: Path) -> None:
    source = _tiny_source(tmp_path / "source")
    out = tmp_path / "broken_counts"
    filter_dataset(source, out, make_config(50.0))
    info_path = out / INFO_FILENAME
    run_before = (out / "run.json").read_bytes()
    bad = _valid_info(counts={"input": 9, "accepted": 1, "rejected": 1, "error": 1})
    info_path.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RunInfoError, match="inconsistent"):
        load_run_info(out)
    assert info_path.read_text(encoding="utf-8")
    assert (out / "run.json").read_bytes() == run_before
