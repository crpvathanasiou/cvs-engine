"""Unit tests for saved-classification lookup from results.csv."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from blur_gate.decision_lookup import (
    LABEL_ACCEPTED,
    LABEL_ERROR,
    LABEL_REJECTED,
    LABEL_UNKNOWN,
    ClassificationLookupError,
    DecisionLookupCache,
    label_from_decision,
    lookup_decision_in_results_csv,
    normalize_fs_path,
)


def _write_results(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["image_id", "path", "sharpness_score", "decision", "reason"],
        )
        writer.writeheader()
        for index, (rel, decision) in enumerate(rows):
            writer.writerow(
                {
                    "image_id": f"img{index}",
                    "path": rel,
                    "sharpness_score": "1.0",
                    "decision": decision,
                    "reason": "test",
                }
            )


def test_label_from_decision_mapping() -> None:
    assert label_from_decision("accept") == LABEL_ACCEPTED
    assert label_from_decision("reject") == LABEL_REJECTED
    assert label_from_decision("error") == LABEL_ERROR
    assert label_from_decision("other") == LABEL_UNKNOWN


def test_lookup_accept_reject_error_unknown(tmp_path: Path) -> None:
    source = tmp_path / "dataset"
    (source / "images" / "a").mkdir(parents=True)
    (source / "images" / "b").mkdir(parents=True)
    accept_img = source / "images" / "a" / "frame.jpg"
    reject_img = source / "images" / "b" / "frame.jpg"
    error_img = source / "images" / "a" / "bad.jpg"
    unknown_img = source / "images" / "a" / "other.jpg"
    for path in (accept_img, reject_img, error_img, unknown_img):
        path.write_bytes(b"x")

    results = tmp_path / "run" / "results.csv"
    _write_results(
        results,
        [
            ("images/a/frame.jpg", "accept"),
            ("images/b/frame.jpg", "reject"),
            ("images/a/bad.jpg", "error"),
        ],
    )

    assert (
        lookup_decision_in_results_csv(
            results_csv=results,
            source_dataset_root=source,
            image_path=accept_img,
        )
        == LABEL_ACCEPTED
    )
    assert (
        lookup_decision_in_results_csv(
            results_csv=results,
            source_dataset_root=source,
            image_path=reject_img,
        )
        == LABEL_REJECTED
    )
    assert (
        lookup_decision_in_results_csv(
            results_csv=results,
            source_dataset_root=source,
            image_path=error_img,
        )
        == LABEL_ERROR
    )
    assert (
        lookup_decision_in_results_csv(
            results_csv=results,
            source_dataset_root=source,
            image_path=unknown_img,
        )
        == LABEL_UNKNOWN
    )


def test_identical_filenames_different_folders_do_not_match(tmp_path: Path) -> None:
    source = tmp_path / "dataset"
    left = source / "images" / "left" / "same.jpg"
    right = source / "images" / "right" / "same.jpg"
    left.parent.mkdir(parents=True)
    right.parent.mkdir(parents=True)
    left.write_bytes(b"1")
    right.write_bytes(b"2")

    results = tmp_path / "run" / "results.csv"
    _write_results(
        results,
        [
            ("images/left/same.jpg", "accept"),
            ("images/right/same.jpg", "reject"),
        ],
    )

    assert (
        lookup_decision_in_results_csv(
            results_csv=results,
            source_dataset_root=source,
            image_path=left,
        )
        == LABEL_ACCEPTED
    )
    assert (
        lookup_decision_in_results_csv(
            results_csv=results,
            source_dataset_root=source,
            image_path=right,
        )
        == LABEL_REJECTED
    )
    # Filename-only matching would wrongly collide; full-path compare must not.
    assert normalize_fs_path(left) != normalize_fs_path(right)


def test_same_image_different_decisions_across_executions(tmp_path: Path) -> None:
    source = tmp_path / "dataset"
    image = source / "images" / "v1" / "frame.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"img")

    run_a = tmp_path / "export" / "run_a"
    run_b = tmp_path / "export" / "run_b"
    _write_results(run_a / "results.csv", [("images/v1/frame.jpg", "accept")])
    _write_results(run_b / "results.csv", [("images/v1/frame.jpg", "reject")])

    cache = DecisionLookupCache()
    assert (
        cache.label_for_manual_path(
            output_dir=run_a,
            source_dataset_root=source,
            image_path=image,
        )
        == LABEL_ACCEPTED
    )
    assert (
        cache.label_for_manual_path(
            output_dir=run_b,
            source_dataset_root=source,
            image_path=image,
        )
        == LABEL_REJECTED
    )
    # Cached per execution: rerunning A must not return B's decision.
    assert (
        cache.label_for_manual_path(
            output_dir=run_a,
            source_dataset_root=source,
            image_path=image,
        )
        == LABEL_ACCEPTED
    )


def test_missing_or_malformed_results_is_error_not_unknown(tmp_path: Path) -> None:
    source = tmp_path / "dataset"
    image = source / "images" / "x.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"x")

    with pytest.raises(ClassificationLookupError, match="Missing"):
        lookup_decision_in_results_csv(
            results_csv=tmp_path / "missing.csv",
            source_dataset_root=source,
            image_path=image,
        )

    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,valid\ncsv", encoding="utf-8")
    with pytest.raises(ClassificationLookupError, match="Malformed"):
        lookup_decision_in_results_csv(
            results_csv=bad,
            source_dataset_root=source,
            image_path=image,
        )


def test_rejected_membership_label_never_implies_passed() -> None:
    cache = DecisionLookupCache()
    assert cache.label_for_rejected_membership() == LABEL_REJECTED
    assert cache.label_for_rejected_membership() != LABEL_ACCEPTED


def test_cache_avoids_reread_on_hit(tmp_path: Path) -> None:
    source = tmp_path / "dataset"
    image = source / "images" / "frame.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"x")
    run_dir = tmp_path / "run"
    results = run_dir / "results.csv"
    _write_results(results, [("images/frame.jpg", "error")])

    cache = DecisionLookupCache()
    first = cache.label_for_manual_path(
        output_dir=run_dir,
        source_dataset_root=source,
        image_path=image,
    )
    assert first == LABEL_ERROR

    # Replace CSV with a different decision; cache must keep the first result.
    _write_results(results, [("images/frame.jpg", "accept")])
    second = cache.label_for_manual_path(
        output_dir=run_dir,
        source_dataset_root=source,
        image_path=image,
    )
    assert second == LABEL_ERROR
