"""YAML configuration for BlurGate method, threshold, and preprocessing version."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from blur_gate.decision import validate_threshold
from blur_gate.scoring import METHOD_NAME, PREPROCESSING_VERSION


class ConfigError(ValueError):
    """Readable configuration load/validation failure."""


@dataclass(frozen=True, slots=True)
class BlurGateConfig:
    method: str
    threshold: float
    preprocessing_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_config(threshold: float) -> BlurGateConfig:
    """Build a config for the current v1 method after validating the threshold."""
    return BlurGateConfig(
        method=METHOD_NAME,
        threshold=validate_threshold(threshold),
        preprocessing_version=PREPROCESSING_VERSION,
    )


def save_config(config: BlurGateConfig, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "method": config.method,
        "threshold": config.threshold,
        "preprocessing_version": config.preprocessing_version,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _require_compatible(method: str, preprocessing_version: str) -> None:
    if method != METHOD_NAME:
        raise ConfigError(
            f"Incompatible method {method!r}; this tool supports {METHOD_NAME!r} only. "
            "Refusing to activate a threshold calibrated for another method."
        )
    if preprocessing_version != PREPROCESSING_VERSION:
        raise ConfigError(
            f"Incompatible preprocessing_version {preprocessing_version!r}; "
            f"this tool supports {PREPROCESSING_VERSION!r} only. "
            "Refusing to activate a threshold calibrated for another preprocessing path."
        )


def ensure_compatible_config(config: BlurGateConfig) -> BlurGateConfig:
    """Validate method, preprocessing, and threshold for any config object.

    Used by YAML loading and by the public filtering API so incompatible objects
    cannot bypass shared rules.
    """
    try:
        threshold = validate_threshold(config.threshold)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    _require_compatible(str(config.method), str(config.preprocessing_version))
    return BlurGateConfig(
        method=str(config.method),
        threshold=threshold,
        preprocessing_version=str(config.preprocessing_version),
    )


def load_config(path: Path | str) -> BlurGateConfig:
    """Load YAML config; reject malformed or incompatible method/preprocessing."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read config file: {path}") from exc

    try:
        raw_obj: object = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Malformed YAML in config file: {path}") from exc

    if not isinstance(raw_obj, dict):
        raise ConfigError(
            "config must be a YAML mapping with method, threshold, and preprocessing_version"
        )
    raw = cast(Mapping[str, object], raw_obj)
    required = ("method", "threshold", "preprocessing_version")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ConfigError(f"config missing keys: {', '.join(missing)}")

    try:
        threshold = validate_threshold(raw["threshold"])
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    return ensure_compatible_config(
        BlurGateConfig(
            method=str(raw["method"]),
            threshold=threshold,
            preprocessing_version=str(raw["preprocessing_version"]),
        )
    )
