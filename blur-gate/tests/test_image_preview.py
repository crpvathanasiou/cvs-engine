"""Unit tests for preview path normalization and byte loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from blur_gate.image_preview import (
    PreviewImageError,
    build_zoom_pan_html,
    load_preview_bytes,
    normalize_manual_path,
)
from tests.fixture_dataset import write_textured_jpeg


def test_normalize_manual_path_strips_quotes(tmp_path: Path) -> None:
    target = tmp_path / "frame.jpg"
    write_textured_jpeg(target, seed=1)
    quoted = f'"{target}"'
    assert normalize_manual_path(quoted) == Path(str(target)).expanduser()


def test_load_preview_bytes_and_html(tmp_path: Path) -> None:
    target = tmp_path / "frame.jpg"
    write_textured_jpeg(target, seed=2)
    data, mime, resolved = load_preview_bytes(target)
    assert mime == "image/jpeg"
    assert resolved == target.resolve()
    assert data.startswith(b"\xff\xd8")
    html = build_zoom_pan_html(data, mime=mime)
    assert "Zoom +" in html
    assert "Zoom −" in html
    assert ">Fit<" in html
    assert "data:image/jpeg;base64," in html


def test_load_preview_missing_and_bad_suffix(tmp_path: Path) -> None:
    with pytest.raises(PreviewImageError, match="not found"):
        load_preview_bytes(tmp_path / "missing.jpg")
    bad = tmp_path / "notes.txt"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(PreviewImageError, match="Unsupported"):
        load_preview_bytes(bad)


def test_load_preview_rejects_nonempty_invalid_jpeg(tmp_path: Path) -> None:
    corrupt = tmp_path / "broken.jpg"
    corrupt.write_bytes(b"not-a-jpeg-but-nonempty")
    with pytest.raises(PreviewImageError, match="Unreadable or corrupt"):
        load_preview_bytes(corrupt)


def test_load_preview_returns_original_bytes_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "frame.jpg"
    write_textured_jpeg(target, seed=3)
    original = target.read_bytes()
    data, _mime, _resolved = load_preview_bytes(target)
    assert data == original
    assert target.read_bytes() == original
