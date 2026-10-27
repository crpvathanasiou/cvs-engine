"""Unit tests for incremental rejected.txt navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

from blur_gate.rejected_index import RejectedIndexError, RejectedPathIndex


def test_path_at_retains_offsets_and_order(tmp_path: Path) -> None:
    rejected = tmp_path / "rejected.txt"
    lines = [
        str(tmp_path / "a.jpg"),
        str(tmp_path / "b.jpg"),
        str(tmp_path / "c.jpg"),
    ]
    rejected.write_text("\n".join(lines) + "\n", encoding="utf-8")

    index = RejectedPathIndex(rejected, expected_count=3)
    assert index.path_at(0) == lines[0]
    assert 0 in index.offsets
    assert index.path_at(2) == lines[2]
    assert set(index.offsets) >= {0, 1, 2}
    # Cached offset read must not require a full rescan of unread lines.
    restored = RejectedPathIndex(rejected, expected_count=3)
    restored.restore_offsets({2: index.offsets[2]})
    assert restored.path_at(2) == lines[2]
    assert 0 not in restored.offsets


def test_open_for_run_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RejectedIndexError, match="unavailable"):
        RejectedPathIndex.open_for_run(tmp_path, expected_count=1)


def test_open_for_run_zero_rejected_requires_file(tmp_path: Path) -> None:
    with pytest.raises(RejectedIndexError, match="unavailable"):
        RejectedPathIndex.open_for_run(tmp_path, expected_count=0)
    (tmp_path / "rejected.txt").write_text("", encoding="utf-8")
    index = RejectedPathIndex.open_for_run(tmp_path, expected_count=0)
    with pytest.raises(RejectedIndexError, match="No rejected images"):
        index.path_at(0)
