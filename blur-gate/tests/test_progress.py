"""Focused tests for progress counts, ETA math, callbacks, and finalization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from blur_gate.config import make_config
from blur_gate.dataset_filter import DatasetFilterError, filter_dataset
from blur_gate.progress import (
    ProgressReporter,
    ProgressUpdate,
    describe_progress,
    format_duration,
    format_percent,
)
from blur_gate.scan import score_tree
from tests.fixture_dataset import (
    build_source_dataset,
    make_record,
    make_segment,
    make_video,
    write_corrupt_jpeg,
    write_textured_jpeg,
)


class FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _write_png(path: Path, value: int = 80) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.full((32, 32, 3), value, dtype=np.uint8)
    img[::2, ::2] = 255 - value
    assert cv2.imwrite(str(path), img)


def _assert_no_premature_completion(updates: list[ProgressUpdate]) -> None:
    for update in updates:
        text = describe_progress(update)
        if update.phase != "completed":
            assert update.fraction is None or update.fraction < 1.0
            assert "100.0%" not in update.message
            assert "100.0%" not in text
        if update.phase == "failed":
            assert "ETA: Estimating…" not in text
            assert "ETA: 0:00" not in text
            assert "Speed: Estimating…" not in text
            assert "(—)" in text or "Processed:" in text


def _minimal_source(root: Path, *, n: int = 2) -> Path:
    records = [
        make_record(
            image_id=f"img{i}",
            video_id="vidA",
            segment_id="segA1",
            filename=f"f{i}.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            timestamp=float(i + 1),
            frame_index=i,
        )
        for i in range(n)
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
                requested_count=n,
                exported_count=n,
            )
        ],
        mapping=[("origA.mp4", "images/vidA")],
    )
    for i in range(n):
        write_textured_jpeg(root / f"images/vidA/segA1/f{i}.jpg", seed=i + 1)
    return root


def test_format_duration_and_percent_estimating() -> None:
    assert format_duration(None) == "Estimating…"
    assert format_duration(65) == "1:05"
    assert format_percent(1, None) == "—"
    assert format_percent(1, 4, phase="running") == "25.0%"
    assert format_percent(4, 4, phase="running") == "99.9%"
    assert format_percent(4, 4, phase="finalizing") == "99.9%"
    assert format_percent(4, 4, phase="completed") == "100.0%"
    assert format_percent(4, 4, phase="failed") == "—"


def test_reporter_throttle_and_forced_final_without_sleep() -> None:
    clock = FakeClock()
    updates: list[ProgressUpdate] = []
    reporter = ProgressReporter(
        updates.append,
        throttle_seconds=0.5,
        clock=clock,
        min_rate_samples=2,
    )

    reporter.preparing("Discovering images…")
    assert updates[-1].phase == "preparing"
    assert updates[-1].processed == 0
    assert "Discovering" in updates[-1].message

    reporter.start(4)
    assert updates[-1].phase == "running"
    assert updates[-1].total == 4
    assert updates[-1].eta_seconds is None

    count_after_start = len(updates)
    reporter.item_done("a.jpg")
    assert len(updates) == count_after_start
    assert updates[-1].processed == 0

    clock.advance(0.49)
    reporter.item_done("b.jpg")
    assert len(updates) == count_after_start

    clock.advance(0.02)
    reporter.item_done("c.jpg")
    assert updates[-1].processed == 3
    rate = updates[-1].images_per_second
    eta = updates[-1].eta_seconds
    assert rate is not None and eta is not None
    expected_eta = 1.0 / rate
    assert abs(eta - expected_eta) < 1e-9

    reporter.item_done("d.jpg")
    assert updates[-1].phase == "finalizing"
    assert updates[-1].processed == 4
    assert updates[-1].fraction is not None
    assert updates[-1].fraction < 1.0
    assert "100.0%" not in updates[-1].message
    assert "100.0%" not in describe_progress(updates[-1])

    reporter.completed()
    assert updates[-1].phase == "completed"
    assert updates[-1].processed == 4
    assert updates[-1].fraction == 1.0
    assert updates[-1].message.startswith("Completed")
    assert "100.0%" in describe_progress(updates[-1])


def test_failed_never_reports_full_completion_fraction() -> None:
    clock = FakeClock()
    updates: list[ProgressUpdate] = []
    reporter = ProgressReporter(updates.append, throttle_seconds=0.0, clock=clock)
    reporter.start(10)
    for index in range(10):
        reporter.item_done(f"{index}.jpg")
    reporter.failed("Interrupted")
    _assert_no_premature_completion(updates)
    final = updates[-1]
    assert final.phase == "failed"
    assert final.processed == 10
    assert final.fraction is not None
    assert final.fraction < 1.0
    assert "Interrupted" in final.message
    assert final.eta_seconds is None
    assert final.images_per_second is None


def test_score_tree_progress_counts_include_read_errors(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    _write_png(root / "ok.png", 40)
    bad = root / "bad.jpg"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"not-an-image")

    updates: list[ProgressUpdate] = []
    rows, _warnings = score_tree(
        root,
        progress_update_callback=updates.append,
        progress_throttle_seconds=0.0,
    )

    assert len(rows) == 2
    assert sum(1 for row in rows if row.error is not None) == 1
    assert updates[0].phase == "preparing"
    assert "Discovering" in updates[0].message
    assert any(item.phase == "running" and item.total == 2 for item in updates)
    assert any(item.phase == "finalizing" for item in updates)
    _assert_no_premature_completion([u for u in updates if u.phase != "completed"])
    final = updates[-1]
    assert final.phase == "completed"
    assert final.processed == 2
    assert final.total == 2
    assert final.fraction == 1.0


def test_filter_dataset_progress_includes_rejects_and_errors(tmp_path: Path) -> None:
    source = tmp_path / "source"
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
        make_record(
            image_id="bad",
            video_id="vidA",
            segment_id="segA1",
            filename="bad.jpg",
            video_filename="origA.mp4",
            excel_row=11,
            start_seconds=0.0,
            end_seconds=10.0,
            timestamp=3.0,
            frame_index=2,
        ),
    ]
    build_source_dataset(
        source,
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
                requested_count=3,
                exported_count=3,
            )
        ],
        mapping=[("origA.mp4", "images/vidA")],
    )
    write_textured_jpeg(source / "images/vidA/segA1/sharp.jpg", seed=1)
    img = np.full((48, 48, 3), 128, dtype=np.uint8)
    assert cv2.imwrite(str(source / "images/vidA/segA1/blur.jpg"), img)
    write_corrupt_jpeg(source / "images/vidA/segA1/bad.jpg")

    updates: list[ProgressUpdate] = []
    out = tmp_path / "out"
    result = filter_dataset(
        source,
        out,
        make_config(50.0),
        progress_update_callback=updates.append,
        progress_throttle_seconds=0.0,
        progress_every=1,
    )

    assert result.counts.input == 3
    assert result.counts.accepted + result.counts.rejected + result.counts.error == 3
    assert result.counts.error == 1
    assert updates[0].phase == "preparing"
    assert "Reading dataset metadata" in updates[0].message
    assert any(item.phase == "finalizing" for item in updates)
    _assert_no_premature_completion([u for u in updates if u.phase != "completed"])
    final = updates[-1]
    assert final.phase == "completed"
    assert final.processed == 3
    assert final.fraction == 1.0
    assert "100.0%" in describe_progress(final)


def test_finalization_failure_after_all_images_never_showed_100(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _minimal_source(tmp_path / "source", n=3)
    updates: list[ProgressUpdate] = []
    texts: list[str] = []

    def on_update(update: ProgressUpdate) -> None:
        updates.append(update)
        texts.append(describe_progress(update))

    def boom(*_args: Any, **_kwargs: Any) -> int:
        raise DatasetFilterError("injected finalization failure")

    monkeypatch.setattr("blur_gate.dataset_filter._write_mapping", boom)

    with pytest.raises(DatasetFilterError, match="injected finalization failure"):
        filter_dataset(
            source,
            tmp_path / "out",
            make_config(1.0),
            progress_update_callback=on_update,
            progress_throttle_seconds=0.0,
            progress_every=1,
        )

    assert any(u.phase == "finalizing" and u.processed == 3 for u in updates)
    assert updates[-1].phase == "failed"
    for update, text in zip(updates, texts, strict=True):
        assert update.phase != "completed"
        assert update.fraction is None or update.fraction < 1.0
        assert "100.0%" not in update.message
        assert "100.0%" not in text
        if update.phase == "failed":
            assert "ETA: Estimating…" not in text
            assert "Speed: Estimating…" not in text


def test_legacy_count_callback_contract(tmp_path: Path) -> None:
    source = _minimal_source(tmp_path / "source", n=2)
    legacy_calls: list[tuple[int, int | None]] = []

    def legacy(processed: int, total: int | None) -> None:
        legacy_calls.append((processed, total))

    result = filter_dataset(
        source,
        tmp_path / "out",
        make_config(1.0),
        progress_callback=legacy,
        progress_throttle_seconds=0.0,
        progress_every=1,
    )
    assert result.counts.input == 2
    assert legacy_calls
    assert legacy_calls[0][0] == 0
    assert any(done == 2 and total == 2 for done, total in legacy_calls)
    assert legacy_calls[-1] == (2, 2)


def test_rich_and_legacy_callbacks_both_invoked(tmp_path: Path) -> None:
    source = _minimal_source(tmp_path / "source", n=1)
    rich: list[ProgressUpdate] = []
    legacy: list[tuple[int, int | None]] = []

    filter_dataset(
        source,
        tmp_path / "out",
        make_config(1.0),
        progress_callback=lambda done, total: legacy.append((done, total)),
        progress_update_callback=rich.append,
        progress_throttle_seconds=0.0,
        progress_every=1,
    )
    assert rich
    assert legacy
    assert len(rich) == len(legacy)
    assert all(r.processed == d and r.total == t for r, (d, t) in zip(rich, legacy, strict=True))
    assert rich[-1].phase == "completed"
    assert rich[-1].fraction == 1.0


def test_filter_without_callbacks(tmp_path: Path) -> None:
    source = _minimal_source(tmp_path / "source", n=1)
    result = filter_dataset(source, tmp_path / "out", make_config(1.0))
    assert result.status == "completed"
    assert result.counts.input == 1


def test_filter_failure_progress_is_not_marked_complete(tmp_path: Path) -> None:
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
        counts_images_exported=99,
    )
    write_textured_jpeg(source / "images/vidA/segA1/f1.jpg", seed=2)

    updates: list[ProgressUpdate] = []
    with pytest.raises(DatasetFilterError):
        filter_dataset(
            source,
            tmp_path / "out",
            make_config(1.0),
            progress_update_callback=updates.append,
            progress_throttle_seconds=0.0,
            progress_every=1,
        )

    _assert_no_premature_completion(updates)
    final = updates[-1]
    assert final.phase == "failed"
    assert final.processed == 1
    assert final.fraction is not None
    assert final.fraction < 1.0
