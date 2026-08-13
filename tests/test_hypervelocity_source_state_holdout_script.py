"""Command contract for frozen source-state holdout scoring."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_state_holdout.py")
    spec = importlib.util.spec_from_file_location("source_state_holdout_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source-state holdout script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_requires_source_labels_and_frozen_model_evidence() -> None:
    """Every source-feature and model identity is explicit at the command boundary."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--replay",
            "holdout.json",
            "--bars",
            "bars.parquet",
            "--config",
            "config.toml",
            "--strict-labels",
            "labels.parquet",
            "--expected-resolved",
            "50",
            "--expected-liquidations",
            "10",
            "--training-report",
            "training.json",
            "--training-dataset",
            "training.parquet",
            "--model-dir",
            "models",
            "--out",
            "holdout-report.json",
        ]
    )

    assert args.replay == Path("holdout.json")
    assert args.strict_labels == Path("labels.parquet")
    assert args.expected_resolved == 50
    assert args.expected_liquidations == 10


def test_population_guard_enforces_predeclared_minimums() -> None:
    """Sparse holdouts cannot be presented as the planned model test."""
    module = _load_script()
    too_small = pd.DataFrame(
        {"liquidation_risk": [1] * 9 + [0] * 40},
    )

    with pytest.raises(ValueError, match="at least 50 resolved and 10 liquidations"):
        module._validate_holdout_population(too_small)

    enough = pd.DataFrame({"liquidation_risk": [1] * 10 + [0] * 40})
    assert module._validate_holdout_population(enough) == {
        "resolved": 50,
        "liquidations": 10,
    }
