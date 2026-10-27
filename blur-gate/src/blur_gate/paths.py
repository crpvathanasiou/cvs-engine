"""Safe path resolution relative to a user-supplied dataset root."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class UnsafePathError(ValueError):
    """Raised when a relative path escapes the source dataset root."""


def resolve_under_root(root: Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` under ``root``; reject absolute paths and ``..`` escapes."""
    if not relative_path or not str(relative_path).strip():
        raise UnsafePathError("Image path is empty")
    rel = str(relative_path).replace("\\", "/")
    if PurePosixPath(rel).is_absolute() or Path(rel).is_absolute():
        raise UnsafePathError(f"Absolute image paths are not allowed: {relative_path}")
    parts = PurePosixPath(rel).parts
    if any(part == ".." for part in parts):
        raise UnsafePathError(f"Path escapes source root: {relative_path}")

    root_resolved = root.resolve()
    candidate = (root_resolved / PurePosixPath(rel)).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes source root: {relative_path}") from exc
    return candidate
