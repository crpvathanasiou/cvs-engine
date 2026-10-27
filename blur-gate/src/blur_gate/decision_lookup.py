"""Lookup saved Accept/Reject/Error labels from an execution's results.csv."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from blur_gate.paths import UnsafePathError, resolve_under_root

LABEL_ACCEPTED = "Accepted"
LABEL_REJECTED = "Rejected"
LABEL_ERROR = "Error"
LABEL_UNKNOWN = "Unknown"

_DECISION_LABELS = {
    "accept": LABEL_ACCEPTED,
    "reject": LABEL_REJECTED,
    "error": LABEL_ERROR,
}

RESULTS_FILENAME = "results.csv"


class ClassificationLookupError(ValueError):
    """Readable failure while reading saved classification from results.csv."""


def normalize_fs_path(path: Path | str) -> str:
    """Normalize a filesystem path for equality checks (Windows-aware)."""
    candidate = Path(path)
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate.absolute() if candidate.is_absolute() else candidate
    text = str(resolved)
    if os.name == "nt":
        return os.path.normcase(os.path.normpath(text))
    return os.path.normpath(text)


def label_from_decision(decision: object) -> str:
    """Map a results.csv decision cell to a display label."""
    key = str(decision).strip().lower()
    return _DECISION_LABELS.get(key, LABEL_UNKNOWN)


def results_csv_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / RESULTS_FILENAME


def lookup_decision_in_results_csv(
    *,
    results_csv: Path | str,
    source_dataset_root: Path | str,
    image_path: Path | str,
) -> str:
    """Stream ``results.csv`` and return the saved label for ``image_path``.

    Paths in the CSV are resolved against ``source_dataset_root`` (the execution's
    saved root), never against the live UI dataset input. Matching uses normalized
    full filesystem paths, not bare filenames.
    """
    csv_path = Path(results_csv)
    if not csv_path.is_file():
        raise ClassificationLookupError(f"Missing {RESULTS_FILENAME}: {csv_path}")

    source_root = Path(source_dataset_root)
    if not str(source_dataset_root).strip():
        raise ClassificationLookupError(
            "Saved source_dataset_root is missing; cannot look up classification."
        )

    target = normalize_fs_path(image_path)

    try:
        handle = csv_path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise ClassificationLookupError(
            f"Could not read {RESULTS_FILENAME}: {exc}"
        ) from exc

    try:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ClassificationLookupError(
                f"Malformed {RESULTS_FILENAME}: missing header"
            )
        required = {"path", "decision"}
        present = {name.strip() for name in fieldnames}
        if not required.issubset(present):
            raise ClassificationLookupError(
                f"Malformed {RESULTS_FILENAME}: expected columns path and decision"
            )

        for row in reader:
            rel = str(row.get("path", "") or "").strip()
            if not rel:
                continue
            try:
                absolute = resolve_under_root(source_root, rel)
            except (UnsafePathError, OSError):
                continue
            if normalize_fs_path(absolute) != target:
                continue
            return label_from_decision(row.get("decision", ""))
    except csv.Error as exc:
        raise ClassificationLookupError(
            f"Malformed {RESULTS_FILENAME}: {exc}"
        ) from exc
    finally:
        handle.close()

    return LABEL_UNKNOWN


class DecisionLookupCache:
    """Cache classification labels per execution folder and image path."""

    def __init__(self) -> None:
        self._labels: dict[tuple[str, str], str] = {}
        self._csv_errors: dict[str, str] = {}

    def clear(self) -> None:
        self._labels.clear()
        self._csv_errors.clear()

    def clear_execution(self, output_dir: Path | str) -> None:
        exec_key = normalize_fs_path(output_dir)
        self._csv_errors.pop(exec_key, None)
        stale = [key for key in self._labels if key[0] == exec_key]
        for key in stale:
            del self._labels[key]

    def label_for_rejected_membership(self) -> str:
        """Rejected-list browsing uses list membership, not CSV absence-as-pass."""
        return LABEL_REJECTED

    def label_for_manual_path(
        self,
        *,
        output_dir: Path | str,
        source_dataset_root: Path | str,
        image_path: Path | str,
    ) -> str:
        exec_key = normalize_fs_path(output_dir)
        path_key = normalize_fs_path(image_path)
        cache_key = (exec_key, path_key)
        if cache_key in self._labels:
            return self._labels[cache_key]
        if exec_key in self._csv_errors:
            raise ClassificationLookupError(self._csv_errors[exec_key])

        try:
            label = lookup_decision_in_results_csv(
                results_csv=results_csv_path(output_dir),
                source_dataset_root=source_dataset_root,
                image_path=image_path,
            )
        except ClassificationLookupError as exc:
            self._csv_errors[exec_key] = str(exc)
            raise

        self._labels[cache_key] = label
        return label
