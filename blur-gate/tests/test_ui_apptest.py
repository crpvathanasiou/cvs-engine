"""Streamlit AppTest regressions for the simplified one-page filter UI."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest
from streamlit.testing.v1 import AppTest

from blur_gate.export_layout import (
    EXPORT_DIR_NAME,
    blur_gate_project_root,
    export_root,
    new_run_output_dir,
)
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

APP_PATH = Path(__file__).resolve().parents[1] / "ui" / "app.py"


def _button_by_label(at: AppTest, label: str):  # noqa: ANN201
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"Button not found: {label}")


def _success_texts(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.success)


def _error_texts(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.error)


def _caption_texts(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.caption)


def _vega_lite_count(at: AppTest) -> int:
    charts = at.get("vega_lite_chart")
    return len(list(charts))


def _build_tiny_source(root: Path) -> Path:
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


def test_readme_public_api_import() -> None:
    from blur_gate import apply_threshold, make_config, save_config, score_bgr, score_file

    assert callable(score_bgr)
    assert callable(score_file)
    assert callable(apply_threshold)
    assert callable(make_config)
    assert callable(save_config)
    assert METHOD_NAME
    assert PREPROCESSING_VERSION


def test_export_root_is_project_local_and_cwd_independent(tmp_path: Path) -> None:
    project = blur_gate_project_root()
    assert export_root() == project / EXPORT_DIR_NAME
    assert export_root().is_absolute()

    original = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert export_root() == project / EXPORT_DIR_NAME
        run_dir = new_run_output_dir(unique_suffix="testrun01")
        assert run_dir.parent == export_root()
        assert run_dir.name.endswith("_testrun01")
    finally:
        os.chdir(original)


def test_ui_page_has_simplified_controls_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Isolate from any leftover local blur_gate_export/ folders.
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: tmp_path / "empty_export")
    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()

    labels = {str(button.label) for button in at.button}
    assert "Filter dataset" in labels
    assert "Scan folder" not in labels

    input_labels = {str(item.label) for item in at.text_input}
    assert "Dataset folder" in input_labels
    assert "Metadata output directory" not in input_labels
    assert "Config YAML path" not in input_labels

    number_labels = {str(item.label) for item in at.number_input}
    assert number_labels == {"Threshold"}

    assert len(at.tabs) == 0
    page_text = "\n".join(str(item.value) for item in at.markdown)
    page_text += "\n".join(str(item.value) for item in at.caption)
    assert "Images with a score below the threshold are excluded" in page_text
    assert "No completed executions found" in page_text or "Previous execution" in page_text


def test_displayed_threshold_reaches_filter_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    suffixes = iter(["runAAAA", "unused"])

    def _fake_new_run_output_dir(**_kwargs: object) -> Path:
        return export_base / f"20260101_000000_{next(suffixes)}"

    monkeypatch.setattr(
        "blur_gate.export_layout.new_run_output_dir",
        _fake_new_run_output_dir,
    )

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    assert at.session_state.last_error is None
    last_obj: object = at.session_state.last_result
    assert isinstance(last_obj, dict)
    last = cast(dict[str, Any], last_obj)
    assert float(last["threshold"]) == 50.0
    assert int(last["accepted"]) + int(last["rejected"]) + int(last["error"]) == 2
    assert int(last["accepted"]) >= 1
    assert int(last["rejected"]) >= 1

    out = Path(str(last["output_dir"]))
    assert out.is_dir()
    assert out.parent == export_base
    assert (out / "results.csv").is_file()
    assert (out / "manifest.jsonl").is_file()
    assert (out / "rejected.txt").is_file()
    assert (out / "video-folder-mapping.csv").is_file()
    assert (out / "run.json").is_file()
    assert not (out / "accepted.csv").exists()
    assert not (out / "images").exists()
    rejected_lines = [
        line
        for line in (out / "rejected.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rejected_lines) == int(last["rejected"])
    for absolute in rejected_lines:
        assert Path(absolute).is_absolute()
        assert Path(absolute).is_file()

    report = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert report["blur_gate"]["threshold"] == 50.0
    assert "accepted=" in _success_texts(at)
    markdown_text = "\n".join(str(item.value) for item in at.markdown)
    assert "Output folder:" in markdown_text
    assert f"Total scanned files: {int(last['input'])}" in markdown_text
    assert len(at.json) == 0
    # Vega-Lite pie is present for classified accept/reject counts.
    assert int(last["accepted"]) + int(last["rejected"]) > 0
    assert _vega_lite_count(at) == 1
    assert (
        f"Accept: {int(last['accepted'])} · Reject: {int(last['rejected'])}"
        in _caption_texts(at)
    )

    # Chart summary remains on a subsequent rerun without rescanning.
    at.run()
    assert _vega_lite_count(at) == 1
    markdown_after = "\n".join(str(item.value) for item in at.markdown)
    assert f"Total scanned files: {int(last['input'])}" in markdown_after
    assert (
        f"Accept: {int(last['accepted'])} · Reject: {int(last['rejected'])}"
        in _caption_texts(at)
    )
    assert at.session_state.last_result is last_obj


def test_successive_runs_preserve_earlier_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    suffixes = iter(["first001", "second002"])

    def _fake_new_run_output_dir(**_kwargs: object) -> Path:
        return export_base / f"20260101_000000_{next(suffixes)}"

    monkeypatch.setattr(
        "blur_gate.export_layout.new_run_output_dir",
        _fake_new_run_output_dir,
    )

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 1.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()
    first_obj: object = at.session_state.last_result
    assert isinstance(first_obj, dict)
    first = Path(str(cast(dict[str, Any], first_obj)["output_dir"]))
    first_run = (first / "run.json").read_text(encoding="utf-8")

    at.session_state.threshold = 9999.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()
    second_obj: object = at.session_state.last_result
    assert isinstance(second_obj, dict)
    second = Path(str(cast(dict[str, Any], second_obj)["output_dir"]))

    assert first != second
    assert first.is_dir()
    assert second.is_dir()
    assert (first / "run.json").read_text(encoding="utf-8") == first_run
    assert json.loads((second / "run.json").read_text(encoding="utf-8"))["blur_gate"][
        "threshold"
    ] == 9999.0


def test_invalid_dataset_folder_shows_readable_error() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()
    at.session_state.dataset_folder = ""
    at.session_state.threshold = 10.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()
    assert "Enter a dataset folder" in _error_texts(at) or "dataset folder" in _error_texts(
        at
    ).lower()


def test_ordinary_rerun_does_not_create_export_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()
    at.session_state.dataset_folder = str(tmp_path / "unused")
    at.session_state.threshold = 10.0
    at.run()
    assert not export_base.exists()


def test_export_root_mkdir_failure_is_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    blocked = tmp_path / "blur_gate_export_blocked"
    blocked.write_text("not-a-directory", encoding="utf-8")
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: blocked)

    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 10.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    errors = _error_texts(at)
    assert "Dataset filtering failed" in errors
    assert at.session_state.last_error is not None
    assert "Dataset filtering failed" in str(at.session_state.last_error)
    assert len(at.exception) == 0
    assert _vega_lite_count(at) == 0
    assert at.session_state.last_result is None


def _build_error_only_source(root: Path) -> Path:
    records = [
        make_record(
            image_id="bad",
            video_id="vidA",
            segment_id="segA1",
            filename="bad.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            timestamp=1.0,
            frame_index=0,
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
    )
    write_corrupt_jpeg(root / "images/vidA/segA1/bad.jpg")
    return root


def test_completion_chart_errors_and_no_classified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_error_only_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)
    def _err_run_dir(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_erronly"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _err_run_dir)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 10.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    last = cast(dict[str, Any], at.session_state.last_result)
    assert int(last["accepted"]) == 0
    assert int(last["rejected"]) == 0
    assert int(last["error"]) == 1
    assert int(last["input"]) == 1
    assert _vega_lite_count(at) == 0
    markdown_text = "\n".join(str(item.value) for item in at.markdown)
    info_text = "\n".join(str(item.value) for item in at.info)
    assert "No classified images" in info_text
    assert "Total scanned files: 1" in markdown_text
    assert "Errors: 1" in markdown_text
    assert "excluded from the pie chart" in markdown_text
    assert "Accept:" not in _caption_texts(at)

    at.run()
    assert "No classified images" in "\n".join(str(item.value) for item in at.info)
    assert "Total scanned files: 1" in "\n".join(str(item.value) for item in at.markdown)
    assert _vega_lite_count(at) == 0
    assert "No rejected images" in "\n".join(str(item.value) for item in at.info)


def _markdown_texts(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.markdown)


def _write_texts(at: AppTest) -> str:
    # st.write often lands in markdown elements in AppTest.
    return _markdown_texts(at)


def test_rejected_viewer_navigation_and_back_to_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    def _run_dir(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_view01"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _run_dir)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    # High threshold → textured may still accept at low threshold; use 50 for mixed.
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    last = cast(dict[str, Any], at.session_state.last_result)
    rejected = int(last["rejected"])
    assert rejected >= 1
    assert at.session_state.viewer_mode == "rejected"
    assert int(at.session_state.viewer_index) == 0
    assert f"Image 1 of {rejected}" in _write_texts(at)
    first_path = str(at.session_state.viewer_path)
    assert first_path
    assert Path(first_path).is_file()
    assert at.session_state.viewer_image_bytes is not None

    prev = _button_by_label(at, "Previous")
    assert prev.disabled is True

    if rejected >= 2:
        _button_by_label(at, "Next").click().run()
        assert int(at.session_state.viewer_index) == 1
        assert f"Image 2 of {rejected}" in _write_texts(at)
        second_path = str(at.session_state.viewer_path)
        assert second_path != first_path
        assert 0 in cast(dict[Any, Any], at.session_state.viewer_offsets)
        assert 1 in cast(dict[Any, Any], at.session_state.viewer_offsets)

        # Manual path switches mode and disables list navigation.
        at.session_state.manual_path_input = first_path
        at.run()
        _button_by_label(at, "Open image").click().run()
        assert at.session_state.viewer_mode == "manual"
        assert "Manual image" in _write_texts(at)
        assert _button_by_label(at, "Previous").disabled is True
        assert _button_by_label(at, "Next").disabled is True

        _button_by_label(at, "Back to rejected").click().run()
        assert at.session_state.viewer_mode == "rejected"
        assert int(at.session_state.viewer_index) == 0
        assert f"Image 1 of {rejected}" in _write_texts(at)
        assert str(at.session_state.viewer_path) == first_path
    else:
        # Single reject: Next disabled; manual → back still returns to image 1.
        assert _button_by_label(at, "Next").disabled is True
        at.session_state.manual_path_input = first_path
        at.run()
        _button_by_label(at, "Open image").click().run()
        assert at.session_state.viewer_mode == "manual"
        _button_by_label(at, "Back to rejected").click().run()
        assert int(at.session_state.viewer_index) == 0
        assert f"Image 1 of {rejected}" in _write_texts(at)


def test_viewer_missing_rejected_image_shows_error_keeps_nav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)
    def _fixed_missing_run(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_missing"

    monkeypatch.setattr(
        "blur_gate.export_layout.new_run_output_dir",
        _fixed_missing_run,
    )

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    last = cast(dict[str, Any], at.session_state.last_result)
    rejected = int(last["rejected"])
    assert rejected >= 1
    path = Path(str(at.session_state.viewer_path))
    assert path.is_file()
    path.unlink()

    # Rerun should re-attempt load of the same index and surface a readable error.
    at.run()
    assert "not found" in _error_texts(at).lower() or "Image file not found" in _error_texts(
        at
    )
    assert at.session_state.viewer_image_bytes is None
    # Navigation controls remain present.
    assert _button_by_label(at, "Previous") is not None
    assert _button_by_label(at, "Next") is not None


def test_viewer_invalid_jpeg_clears_preview_keeps_nav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    def _run_dir(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_invalidjpg"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _run_dir)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    assert at.session_state.viewer_image_bytes is not None
    kept_index = int(at.session_state.viewer_index)

    invalid = tmp_path / "broken.jpg"
    invalid.write_bytes(b"not-a-real-jpeg-payload")
    at.session_state.manual_path_input = str(invalid)
    at.run()
    _button_by_label(at, "Open image").click().run()

    assert at.session_state.viewer_mode == "manual"
    assert at.session_state.viewer_image_bytes is None
    assert "Unreadable or corrupt" in _error_texts(at)
    assert Path(str(at.session_state.viewer_path)).name == "broken.jpg"
    assert int(at.session_state.viewer_index) == kept_index
    assert _button_by_label(at, "Previous") is not None
    assert _button_by_label(at, "Next") is not None
    # List nav disabled in manual mode, but Back to rejected remains usable.
    assert _button_by_label(at, "Back to rejected").disabled is False
    _button_by_label(at, "Back to rejected").click().run()
    assert at.session_state.viewer_mode == "rejected"
    assert int(at.session_state.viewer_index) == 0


def test_ui_reopen_previous_execution_without_scoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    def _run_dir(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_reopen"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _run_dir)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    first = cast(dict[str, Any], at.session_state.last_result)
    out = Path(str(first["output_dir"]))
    assert (out / "blur_gate_info.json").is_file()
    assert str(at.session_state.selected_run_dir) == str(out.resolve())
    assert "Saved execution" in _markdown_texts(at)

    score_calls = {"n": 0}

    def _boom(*_args: object, **_kwargs: object) -> object:
        score_calls["n"] += 1
        raise AssertionError("score_file must not run when reopening a saved execution")

    monkeypatch.setattr("blur_gate.scoring.score_file", _boom)
    monkeypatch.setattr("blur_gate.dataset_filter.score_file", _boom)

    # Fresh UI session: selecting the saved folder must reopen without filtering.
    at2 = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at2.run()
    assert score_calls["n"] == 0
    assert at2.session_state.last_result is not None
    reopened = cast(dict[str, Any], at2.session_state.last_result)
    assert Path(str(reopened["output_dir"])).resolve() == out.resolve()
    assert int(reopened["rejected"]) == int(first["rejected"])
    assert int(reopened["accepted"]) == int(first["accepted"])
    assert score_calls["n"] == 0
    assert "Saved execution" in _markdown_texts(at2)


def test_ui_switch_execution_resets_viewer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    suffixes = iter(["run_old", "run_new"])

    def _run_dir(**_kwargs: object) -> Path:
        return export_base / f"20260101_000000_{next(suffixes)}"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _run_dir)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()
    first_out = Path(str(cast(dict[str, Any], at.session_state.last_result)["output_dir"]))

    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()
    second_out = Path(str(cast(dict[str, Any], at.session_state.last_result)["output_dir"]))
    assert second_out != first_out
    assert Path(str(at.session_state.selected_run_dir)).resolve() == second_out.resolve()

    # Enter manual mode on the newest run, then switch back to the older execution.
    manual = Path(str(at.session_state.viewer_path))
    assert manual.is_file()
    at.session_state.manual_path_input = str(manual)
    at.run()
    _button_by_label(at, "Open image").click().run()
    assert at.session_state.viewer_mode == "manual"

    at.session_state.selected_run_dir = str(first_out.resolve())
    at.run()
    switched = cast(dict[str, Any], at.session_state.last_result)
    assert Path(str(switched["output_dir"])).resolve() == first_out.resolve()
    assert at.session_state.viewer_mode == "rejected"
    assert int(at.session_state.viewer_index) == 0
    assert at.session_state.viewer_initialized_for == str(first_out.resolve())


def test_viewer_literal_html_sensitive_path_display(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    def _run_dir(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_literal"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _run_dir)

    tricky_name = "a&copy;.jpg"
    tricky = tmp_path / tricky_name
    write_textured_jpeg(tricky, seed=9)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    at.session_state.manual_path_input = str(tricky)
    at.run()
    _button_by_label(at, "Open image").click().run()

    # Session path stays the real filesystem name; HTML render escapes entities.
    assert Path(str(at.session_state.viewer_path)).name == tricky_name
    rendered = _markdown_texts(at)
    assert "a&amp;copy;.jpg" in rendered
    assert "<script>" not in rendered.lower()


def test_ui_saved_classification_rejected_and_manual_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_tiny_source(tmp_path / "source")
    export_base = tmp_path / "blur_gate_export"
    monkeypatch.setattr("blur_gate.export_layout.export_root", lambda: export_base)

    def _run_dir(**_kwargs: object) -> Path:
        return export_base / "20260101_000000_classlab"

    monkeypatch.setattr("blur_gate.export_layout.new_run_output_dir", _run_dir)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state.dataset_folder = str(source)
    at.session_state.threshold = 50.0
    at.run()
    _button_by_label(at, "Filter dataset").click().run()

    assert at.session_state.viewer_mode == "rejected"
    assert at.session_state.viewer_classification == "Rejected"
    assert "Classification:</strong> Rejected" in _markdown_texts(at)

    out = Path(str(cast(dict[str, Any], at.session_state.last_result)["output_dir"]))
    accepted_path: Path | None = None
    with (out / "results.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["decision"] == "accept":
                accepted_path = source / str(row["path"]).replace("\\", "/")
                break
    assert accepted_path is not None and accepted_path.is_file()

    at.session_state.manual_path_input = str(accepted_path)
    at.run()
    _button_by_label(at, "Open image").click().run()
    assert at.session_state.viewer_mode == "manual"
    assert at.session_state.viewer_classification == "Accepted"
    assert "Classification:</strong> Accepted" in _markdown_texts(at)

    _button_by_label(at, "Back to rejected").click().run()
    assert at.session_state.viewer_classification == "Rejected"
