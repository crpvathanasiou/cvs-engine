"""Recursive image discovery and batch scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blur_gate.progress import (
    DEFAULT_THROTTLE_SECONDS,
    ProgressReporter,
    ProgressUpdateCallback,
)
from blur_gate.scoring import (
    METHOD_NAME,
    PREPROCESSING_VERSION,
    SUPPORTED_SUFFIXES,
    ImageReadError,
    SharpnessResult,
    score_file,
)


@dataclass(frozen=True, slots=True)
class ScoredImage:
    """One scanned file with relative path and either a score or a read error."""

    relative_path: str
    absolute_path: Path
    result: SharpnessResult | None
    error: str | None


def list_image_files(root: Path | str) -> list[Path]:
    """Scan PNG/JPG/JPEG recursively in a stable lexicographic order by relative path."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")

    files: list[Path] = []
    for path in root_path.rglob("*"):
        if path.is_file() and path.suffix in SUPPORTED_SUFFIXES:
            files.append(path)
    files.sort(key=lambda p: p.relative_to(root_path).as_posix().lower())
    return files


def score_tree(
    root: Path | str,
    *,
    progress_callback: ProgressUpdateCallback | None = None,
    progress_update_callback: ProgressUpdateCallback | None = None,
    progress_throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
) -> tuple[list[ScoredImage], list[str]]:
    """Score every supported image under ``root``.

    Returns scored rows and resolution-mix warnings (not errors).
    Optional ``progress_update_callback`` (or legacy alias ``progress_callback``)
    receives throttled ``ProgressUpdate`` values. Read errors are included in the
    processed count.
    """
    root_path = Path(root).resolve()
    rich_callback = progress_update_callback or progress_callback
    reporter = ProgressReporter(
        rich_callback,
        throttle_seconds=progress_throttle_seconds,
        preparing_message="Discovering images…",
    )
    reporter.preparing("Discovering images…")

    files = list_image_files(root_path)
    reporter.start(len(files))

    rows: list[ScoredImage] = []
    resolutions: set[tuple[int, int]] = set()

    try:
        for absolute in files:
            relative = absolute.relative_to(root_path).as_posix()
            try:
                result = score_file(absolute)
                resolutions.add((result.width, result.height))
                rows.append(
                    ScoredImage(
                        relative_path=relative,
                        absolute_path=absolute,
                        result=result,
                        error=None,
                    )
                )
            except ImageReadError as exc:
                rows.append(
                    ScoredImage(
                        relative_path=relative,
                        absolute_path=absolute,
                        result=None,
                        error=str(exc),
                    )
                )
            reporter.item_done(relative)
        reporter.completed()
    except Exception:
        reporter.failed("Scan interrupted or failed")
        raise

    warnings: list[str] = []
    if len(resolutions) > 1:
        res_list = ", ".join(f"{w}x{h}" for w, h in sorted(resolutions))
        warnings.append(
            "Sample contains multiple image resolutions "
            f"({res_list}). Laplacian variance is resolution-sensitive; "
            "changing resolution or preprocessing requires threshold reassessment."
        )
    return rows, warnings


def cache_key_for_file(path: Path) -> tuple[str, int, int, str]:
    """Identity used to invalidate cached scores when a file changes."""
    stat = path.stat()
    return (
        str(path.resolve()),
        int(stat.st_mtime_ns),
        int(stat.st_size),
        f"{METHOD_NAME}:{PREPROCESSING_VERSION}",
    )
