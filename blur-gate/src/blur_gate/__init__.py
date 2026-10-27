"""BlurGate — deterministic Laplacian-variance blur filter."""

from __future__ import annotations

from blur_gate.config import (
    BlurGateConfig,
    ConfigError,
    ensure_compatible_config,
    load_config,
    make_config,
    save_config,
)
from blur_gate.dataset_filter import DatasetFilterError, FilterResult, filter_dataset
from blur_gate.dataset_source import DatasetValidationError, open_source_dataset
from blur_gate.decision import Decision, apply_threshold, validate_threshold
from blur_gate.progress import (
    CountProgressCallback,
    ProgressCallback,
    ProgressUpdate,
    ProgressUpdateCallback,
)
from blur_gate.scoring import (
    METHOD_NAME,
    PREPROCESSING_VERSION,
    ImageReadError,
    SharpnessResult,
    score_bgr,
    score_file,
)
from blur_gate.version import __version__

__all__ = [
    "METHOD_NAME",
    "PREPROCESSING_VERSION",
    "BlurGateConfig",
    "ConfigError",
    "CountProgressCallback",
    "DatasetFilterError",
    "DatasetValidationError",
    "Decision",
    "FilterResult",
    "ImageReadError",
    "ProgressCallback",
    "ProgressUpdate",
    "ProgressUpdateCallback",
    "SharpnessResult",
    "apply_threshold",
    "ensure_compatible_config",
    "filter_dataset",
    "load_config",
    "make_config",
    "open_source_dataset",
    "save_config",
    "score_bgr",
    "score_file",
    "validate_threshold",
    "__version__",
]
