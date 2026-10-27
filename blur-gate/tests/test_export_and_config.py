"""Tests for accepted manifest, source preservation, and config round-trip."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from blur_gate.config import load_config, make_config, save_config
from blur_gate.decision import Decision
from blur_gate.export import (
    assert_sources_untouched,
    build_export_rows,
    write_accepted_csv,
    write_results_csv,
)
from blur_gate.scan import ScoredImage, score_tree
from blur_gate.scoring import METHOD_NAME, PREPROCESSING_VERSION, score_bgr


def _write_png(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.full((32, 32, 3), value, dtype=np.uint8)
    img[::2, ::2] = 255 - value
    assert cv2.imwrite(str(path), img)


def test_config_round_trip(tmp_path: Path) -> None:
    cfg = make_config(42.5)
    path = tmp_path / "blur_gate_config.yaml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.method == METHOD_NAME
    assert loaded.preprocessing_version == PREPROCESSING_VERSION
    assert abs(loaded.threshold - 42.5) < 1e-12


def test_accepted_manifest_and_source_preservation(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    a = root / "video_a" / "frame_001.png"
    b = root / "video_b" / "frame_001.png"
    _write_png(a, 40)
    _write_png(b, 200)

    loaded_a = cv2.imread(str(a), cv2.IMREAD_COLOR)
    assert loaded_a is not None
    blurry = np.asarray(cv2.GaussianBlur(loaded_a, (31, 31), 0))
    assert cv2.imwrite(str(a), blurry)

    fingerprints = {
        a: (a.stat().st_mtime_ns, a.stat().st_size),
        b: (b.stat().st_mtime_ns, b.stat().st_size),
    }

    scored, _warnings = score_tree(root)
    assert len(scored) == 2
    assert {row.relative_path for row in scored} == {
        "video_a/frame_001.png",
        "video_b/frame_001.png",
    }

    scores = {
        row.relative_path: row.result.sharpness_score
        for row in scored
        if row.result is not None
    }
    assert scores["video_b/frame_001.png"] > scores["video_a/frame_001.png"]
    threshold = (scores["video_a/frame_001.png"] + scores["video_b/frame_001.png"]) / 2.0
    cfg = make_config(threshold)

    export_rows = build_export_rows(scored, threshold)
    out_dir = tmp_path / "export"
    write_results_csv(out_dir / "results.csv", export_rows, input_root=root, config=cfg)
    accepted_count = write_accepted_csv(
        out_dir / "accepted.csv",
        export_rows,
        input_root=root,
        config=cfg,
    )

    accepted_lines = (out_dir / "accepted.csv").read_text(encoding="utf-8").splitlines()
    accepted_body = "\n".join(accepted_lines[1:])
    assert "video_b/frame_001.png" in accepted_body
    assert "video_a/frame_001.png" not in accepted_body
    assert accepted_count == 1
    assert str(root.resolve()) in accepted_body

    results_text = (out_dir / "results.csv").read_text(encoding="utf-8")
    assert "video_a/frame_001.png" in results_text
    assert "video_b/frame_001.png" in results_text
    assert Decision.REJECT.value in results_text
    assert Decision.ACCEPT.value in results_text

    assert_sources_untouched([a, b], fingerprints)
    assert a.is_file() and b.is_file()
    assert (a.stat().st_mtime_ns, a.stat().st_size) == fingerprints[a]
    assert (b.stat().st_mtime_ns, b.stat().st_size) == fingerprints[b]


def test_scoring_without_threshold_is_not_accept_or_reject(tmp_path: Path) -> None:
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    image[::2, ::2] = 255
    result = score_bgr(image)
    scored = [
        ScoredImage(
            relative_path="x.png",
            absolute_path=tmp_path / "x.png",
            result=result,
            error=None,
        )
    ]
    rows = build_export_rows(scored, threshold=None)
    assert rows[0].decision == "scored"
    assert rows[0].reason == "threshold_not_selected"
    assert Decision.ACCEPT.value not in {row.decision for row in rows}
    assert Decision.REJECT.value not in {row.decision for row in rows}
