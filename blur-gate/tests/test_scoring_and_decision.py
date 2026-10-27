"""Focused tests for BlurGate scoring and threshold decisions."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from blur_gate.decision import Decision, apply_threshold, validate_threshold
from blur_gate.scoring import ImageReadError, load_bgr, score_bgr, score_file


def _textured_bgr(size: int = 128) -> np.ndarray:
    rng = np.random.default_rng(0)
    gray = rng.integers(0, 256, size=(size, size), dtype=np.uint8)
    for i in range(0, size, 8):
        gray[:, i : i + 4] = 255
        gray[i : i + 4, :] = np.clip(
            gray[i : i + 4, :].astype(np.int16) + 40, 0, 255
        ).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _blurred_bgr(image: np.ndarray, ksize: int = 31) -> np.ndarray:
    return np.asarray(cv2.GaussianBlur(image, (ksize, ksize), sigmaX=0))


def test_textured_scores_higher_than_blurred() -> None:
    sharp = _textured_bgr()
    blurry = _blurred_bgr(sharp)
    sharp_score = score_bgr(sharp).sharpness_score
    blur_score = score_bgr(blurry).sharpness_score
    assert sharp_score > blur_score


def test_threshold_boundary_accepts_equality() -> None:
    score = 10.0
    assert apply_threshold(score, 10.0).decision is Decision.ACCEPT
    assert apply_threshold(score, 10.0000001).decision is Decision.REJECT
    assert apply_threshold(score, 9.999).decision is Decision.ACCEPT


def test_invalid_thresholds() -> None:
    with pytest.raises(ValueError):
        validate_threshold(-1.0)
    with pytest.raises(ValueError):
        validate_threshold(float("nan"))
    with pytest.raises(ValueError):
        validate_threshold(float("inf"))
    with pytest.raises(ValueError):
        apply_threshold(1.0, -0.5)


def test_unreadable_image_is_explicit_error(tmp_path: Path) -> None:
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"not-an-image")
    with pytest.raises(ImageReadError):
        score_file(bad)
    missing = tmp_path / "missing.png"
    with pytest.raises(ImageReadError):
        score_file(missing)


def test_file_and_memory_scoring_consistent(tmp_path: Path) -> None:
    image = _textured_bgr(96)
    path = tmp_path / "sample.png"
    assert cv2.imwrite(str(path), image)
    from_file = score_file(path)
    from_mem = score_bgr(load_bgr(path))
    assert from_file.width == from_mem.width
    assert from_file.height == from_mem.height
    assert abs(from_file.sharpness_score - from_mem.sharpness_score) < 1e-9
