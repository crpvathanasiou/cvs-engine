"""Incremental reader for BlurGate ``rejected.txt`` (one absolute path per line)."""

from __future__ import annotations

from pathlib import Path


class RejectedIndexError(ValueError):
    """Readable failure while opening or reading rejected.txt."""


class RejectedPathIndex:
    """Seek rejected.txt by retaining byte offsets for visited 0-based indices.

    Does not load all paths into memory up front. Callers load/decode only the
    selected image path returned by ``path_at``.
    """

    def __init__(self, path: Path | str, *, expected_count: int) -> None:
        self.path = Path(path)
        self.expected_count = int(expected_count)
        if self.expected_count < 0:
            raise RejectedIndexError("expected_count must be nonnegative")
        # index -> absolute byte offset of the start of that line
        self._offsets: dict[int, int] = {}

    @classmethod
    def open_for_run(
        cls,
        output_dir: Path | str,
        *,
        expected_count: int,
    ) -> RejectedPathIndex:
        """Open ``rejected.txt`` under a completed run directory."""
        rejected = Path(output_dir) / "rejected.txt"
        if expected_count == 0:
            # Empty list is valid; file should exist and may be empty.
            if not rejected.is_file():
                raise RejectedIndexError(
                    f"rejected.txt is unavailable in the run output: {rejected}"
                )
            return cls(rejected, expected_count=0)
        if not rejected.is_file():
            raise RejectedIndexError(
                f"rejected.txt is unavailable in the run output: {rejected}"
            )
        return cls(rejected, expected_count=expected_count)

    @property
    def offsets(self) -> dict[int, int]:
        """Copy of retained file positions (for session persistence)."""
        return dict(self._offsets)

    def restore_offsets(self, offsets: dict[int, int] | None) -> None:
        if not offsets:
            self._offsets = {}
            return
        self._offsets = {int(k): int(v) for k, v in offsets.items()}

    def path_at(self, index: int) -> str:
        """Return the absolute path string at ``index`` (0-based)."""
        if self.expected_count == 0:
            raise RejectedIndexError("No rejected images")
        if index < 0 or index >= self.expected_count:
            raise RejectedIndexError(
                f"Image index {index + 1} is out of range for {self.expected_count} rejected images"
            )
        if index in self._offsets:
            return self._read_at_offset(self._offsets[index])

        start_index = 0
        start_offset = 0
        for known_index, known_offset in self._offsets.items():
            if known_index <= index and (
                known_index > start_index
                or (known_index == start_index and known_offset >= start_offset)
            ):
                start_index = known_index
                start_offset = known_offset

        try:
            with self.path.open("rb") as handle:
                handle.seek(start_offset)
                current = start_index
                # If we seeked to a known line start, consume that line as current.
                while current <= index:
                    offset = handle.tell()
                    raw = handle.readline()
                    if not raw:
                        raise RejectedIndexError(
                            f"rejected.txt ended before image {index + 1} of "
                            f"{self.expected_count}"
                        )
                    self._offsets[current] = offset
                    if current == index:
                        return raw.decode("utf-8").rstrip("\r\n")
                    current += 1
        except OSError as exc:
            raise RejectedIndexError(f"Could not read rejected.txt: {exc}") from exc

        raise RejectedIndexError(f"Could not locate rejected image {index + 1}")

    def _read_at_offset(self, offset: int) -> str:
        try:
            with self.path.open("rb") as handle:
                handle.seek(offset)
                raw = handle.readline()
                if not raw:
                    raise RejectedIndexError("rejected.txt line is missing or truncated")
                return raw.decode("utf-8").rstrip("\r\n")
        except OSError as exc:
            raise RejectedIndexError(f"Could not read rejected.txt: {exc}") from exc
