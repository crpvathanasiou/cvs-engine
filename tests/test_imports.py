"""Smoke tests verifying the cvs_engine package imports successfully."""

from __future__ import annotations


def test_cvs_engine_imports() -> None:
    import cvs_engine

    assert cvs_engine.__version__ == "0.1.0"


def test_cvs_engine_subpackages_import() -> None:
    import cvs_engine.datasets
    import cvs_engine.evaluation
    import cvs_engine.models
    import cvs_engine.tasks
    import cvs_engine.training
    import cvs_engine.utils

    assert cvs_engine.datasets is not None
    assert cvs_engine.models is not None
    assert cvs_engine.tasks is not None
    assert cvs_engine.training is not None
    assert cvs_engine.evaluation is not None
    assert cvs_engine.utils is not None
