"""Regression tests for compatible configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from blur_gate import make_config
from blur_gate.config import ConfigError, load_config, save_config
from blur_gate.scoring import METHOD_NAME, PREPROCESSING_VERSION


def test_make_config_is_exported_from_package() -> None:
    cfg = make_config(12.5)
    assert cfg.method == METHOD_NAME
    assert cfg.preprocessing_version == PREPROCESSING_VERSION
    assert abs(cfg.threshold - 12.5) < 1e-12


def test_load_rejects_incompatible_method(tmp_path: Path) -> None:
    path = tmp_path / "bad_method.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "method": "other_method",
                "threshold": 50.0,
                "preprocessing_version": PREPROCESSING_VERSION,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Incompatible method"):
        load_config(path)


def test_load_rejects_incompatible_preprocessing(tmp_path: Path) -> None:
    path = tmp_path / "bad_prep.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "method": METHOD_NAME,
                "threshold": 50.0,
                "preprocessing_version": "v0_legacy",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Incompatible preprocessing_version"):
        load_config(path)


def test_load_rejects_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("threshold: [unterminated\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Malformed YAML"):
        load_config(path)


def test_load_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML mapping"):
        load_config(path)


def test_compatible_round_trip_still_works(tmp_path: Path) -> None:
    path = tmp_path / "ok.yaml"
    save_config(make_config(77.0), path)
    loaded = load_config(path)
    assert loaded.threshold == 77.0
    assert loaded.method == METHOD_NAME
