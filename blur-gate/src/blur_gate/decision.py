"""Threshold decision, separated from sharpness scoring."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ThresholdDecision:
    decision: Decision
    threshold: float
    reason: str


def validate_threshold(threshold: object) -> float:
    """Require a finite, nonnegative threshold. Raise ``ValueError`` otherwise."""
    if isinstance(threshold, bool) or not isinstance(threshold, int | float):
        raise ValueError("threshold must be a finite nonnegative number")
    value = float(threshold)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("threshold must be a finite nonnegative number")
    return value


def apply_threshold(sharpness_score: float, threshold: object) -> ThresholdDecision:
    """Reject when ``sharpness_score < threshold``; accept at equality and above."""
    validated = validate_threshold(threshold)
    if not math.isfinite(sharpness_score):
        raise ValueError("sharpness_score must be finite")

    if sharpness_score < validated:
        return ThresholdDecision(
            decision=Decision.REJECT,
            threshold=validated,
            reason="sharpness_score_below_threshold",
        )
    return ThresholdDecision(
        decision=Decision.ACCEPT,
        threshold=validated,
        reason="sharpness_score_meets_threshold",
    )
