"""Streamlit-independent progress reporting for sequential BlurGate jobs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ProgressPhase = Literal["preparing", "running", "finalizing", "completed", "failed"]

DEFAULT_THROTTLE_SECONDS = 0.5
MIN_SAMPLES_FOR_RATE = 2
# Keep incomplete bar/text strictly below 100%; .1f rounding must not become 100.0%.
MAX_INCOMPLETE_FRACTION = 0.999
MAX_INCOMPLETE_PERCENT = 99.9


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """One progress notification for UI or logging consumers."""

    phase: ProgressPhase
    processed: int
    total: int | None
    current_path: str | None
    elapsed_seconds: float
    images_per_second: float | None
    eta_seconds: float | None
    fraction: float | None
    message: str


# Legacy filter_dataset contract: (processed, total).
CountProgressCallback = Callable[[int, int | None], None]
# Rich notifications used by the UI and optional API callers.
ProgressUpdateCallback = Callable[[ProgressUpdate], None]
# Backward-compatible alias for rich updates (scan / older rich callers).
ProgressCallback = ProgressUpdateCallback
Clock = Callable[[], float]


def format_duration(seconds: float | None) -> str:
    """Format a duration for display; ``None`` means still estimating."""
    if seconds is None:
        return "Estimating…"
    if seconds < 0:
        seconds = 0.0
    whole = int(seconds)
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def format_rate(images_per_second: float | None) -> str:
    if images_per_second is None:
        return "Estimating…"
    return f"{images_per_second:.2f} img/s"


def format_counts(processed: int, total: int | None) -> str:
    if total is None:
        return f"{processed}/?"
    return f"{processed}/{total}"


def format_percent(
    processed: int,
    total: int | None,
    *,
    phase: ProgressPhase | None = None,
) -> str:
    """Phase-aware percent text. Only ``completed`` may display 100.0%."""
    if phase == "completed":
        return "100.0%"
    if phase in {"preparing", "failed"} or total is None or total <= 0:
        return "—"
    pct = min((processed / total) * 100.0, MAX_INCOMPLETE_PERCENT)
    return f"{pct:.1f}%"


def describe_progress(update: ProgressUpdate) -> str:
    """Single multi-line status block suitable for Streamlit text widgets."""
    percent = format_percent(update.processed, update.total, phase=update.phase)
    lines = [
        update.message,
        f"Processed: {format_counts(update.processed, update.total)} ({percent})",
    ]
    if update.current_path and update.phase not in {"failed", "completed"}:
        lines.append(f"Current: `{update.current_path}`")
    lines.append(f"Elapsed: {format_duration(update.elapsed_seconds)}")
    if update.phase == "failed":
        lines.append("Speed: —")
        lines.append("ETA: —")
    else:
        lines.append(f"Speed: {format_rate(update.images_per_second)}")
        if update.phase == "finalizing":
            lines.append("ETA: Finalizing…")
        else:
            lines.append(f"ETA: {format_duration(update.eta_seconds)}")
    return "\n\n".join(lines)


class ProgressReporter:
    """Throttle and time progress updates for a sequential image job.

    Uses a monotonic clock by default. Inject ``clock`` in tests instead of sleeping.
    Completion fraction/percent of 100% is reserved for ``phase="completed"``.
    """

    def __init__(
        self,
        callback: ProgressUpdateCallback | None,
        *,
        throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
        progress_every: int | None = None,
        clock: Clock = time.monotonic,
        min_rate_samples: int = MIN_SAMPLES_FOR_RATE,
        preparing_message: str = "Preparing…",
        finalizing_message: str = "Finalizing outputs…",
    ) -> None:
        self._callback = callback
        self._throttle = max(0.0, float(throttle_seconds))
        self._progress_every = progress_every
        self._clock = clock
        self._min_rate_samples = max(1, int(min_rate_samples))
        self._preparing_message = preparing_message
        self._finalizing_message = finalizing_message
        self._t0 = clock()
        self._last_emit_at = float("-inf")
        self.processed = 0
        self.total: int | None = None
        self.current_path: str | None = None
        self.phase: ProgressPhase = "preparing"
        self._status_message = preparing_message

    def _elapsed(self) -> float:
        return max(0.0, float(self._clock() - self._t0))

    def images_per_second(self) -> float | None:
        elapsed = self._elapsed()
        if self.processed < self._min_rate_samples or elapsed <= 0.0:
            return None
        return self.processed / elapsed

    def eta_seconds(self) -> float | None:
        if self.phase in {"failed", "finalizing", "completed"}:
            return None
        rate = self.images_per_second()
        if rate is None or self.total is None or rate <= 0.0:
            return None
        remaining = max(self.total - self.processed, 0)
        return remaining / rate

    def fraction(self) -> float | None:
        if self.phase == "preparing":
            return None
        if self.phase == "completed":
            return 1.0
        if self.phase == "failed":
            if self.total is not None and self.total > 0:
                return min(self.processed / self.total, MAX_INCOMPLETE_FRACTION)
            return 0.0
        if self.total is None:
            return None
        if self.total <= 0:
            return 0.0
        # running / finalizing: never report a completed bar.
        return min(self.processed / self.total, MAX_INCOMPLETE_FRACTION)

    def snapshot(self) -> ProgressUpdate:
        total = self.total
        if self.phase == "failed":
            rate = None
            eta = None
        else:
            rate = self.images_per_second()
            eta = self.eta_seconds()

        if self.phase == "preparing":
            message = self._status_message
        elif self.phase == "completed":
            message = (
                f"Completed {format_counts(self.processed, total)} "
                f"in {format_duration(self._elapsed())}"
            )
        elif self.phase == "failed":
            message = self._status_message
        elif self.phase == "finalizing":
            message = (
                f"{self._status_message} "
                f"{format_counts(self.processed, total)} "
                f"({format_percent(self.processed, total, phase=self.phase)})"
            )
        elif total is None:
            message = f"Processing {self.processed}…"
        else:
            message = (
                f"Processing {format_counts(self.processed, total)} "
                f"({format_percent(self.processed, total, phase=self.phase)})"
            )
        return ProgressUpdate(
            phase=self.phase,
            processed=self.processed,
            total=total,
            current_path=self.current_path,
            elapsed_seconds=self._elapsed(),
            images_per_second=rate,
            eta_seconds=eta,
            fraction=self.fraction(),
            message=message,
        )

    def _should_emit(self, *, force: bool) -> bool:
        if self._callback is None:
            return False
        if force:
            return True
        if self._progress_every is not None and self._progress_every > 0:
            if self.processed > 0 and self.processed % self._progress_every == 0:
                return True
        return (self._clock() - self._last_emit_at) >= self._throttle

    def _emit(self, *, force: bool = False) -> None:
        if not self._should_emit(force=force):
            return
        assert self._callback is not None
        self._callback(self.snapshot())
        self._last_emit_at = self._clock()

    def preparing(self, message: str | None = None) -> None:
        self.phase = "preparing"
        self._status_message = message or self._preparing_message
        self.current_path = None
        self._emit(force=True)

    def start(self, total: int | None) -> None:
        self.total = total
        self.phase = "running"
        self._status_message = "Processing…"
        self._emit(force=True)

    def item_done(self, current_path: str | None = None) -> None:
        self.processed += 1
        self.current_path = current_path
        if self.phase == "preparing":
            self.phase = "running"
        if (
            self.total is not None
            and self.total > 0
            and self.processed >= self.total
            and self.phase == "running"
        ):
            # All inputs scored; outputs / consistency checks may still fail.
            self.phase = "finalizing"
            self._status_message = self._finalizing_message
            self._emit(force=True)
        else:
            self._emit(force=False)

    def finalizing(self, message: str | None = None) -> None:
        """Explicit finalizing notification (also entered from ``item_done``)."""
        self.phase = "finalizing"
        self._status_message = message or self._finalizing_message
        self._emit(force=True)

    def completed(self) -> None:
        self.phase = "completed"
        self._emit(force=True)

    def failed(self, message: str = "Failed") -> None:
        self.phase = "failed"
        self._status_message = message
        self._emit(force=True)
