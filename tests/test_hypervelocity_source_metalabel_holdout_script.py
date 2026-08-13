"""Command contract tests for frozen source-model holdout scoring."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_metalabel_holdout.py")
    spec = importlib.util.spec_from_file_location("source_holdout_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source holdout script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_json_metrics_replaces_undefined_rank_metrics_with_null() -> None:
    """A constant predictor must serialize undefined lift as JSON null."""
    module = _load_script()

    result = module._json_metrics(
        {"base_rate": {"log_loss": 0.5, "top_quintile_lift": math.nan}}
    )

    assert result == {"base_rate": {"log_loss": 0.5, "top_quintile_lift": None}}


def test_parser_requires_frozen_training_and_holdout_evidence() -> None:
    """The scorer command makes training identity and holdout population explicit."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--replay",
            "holdout.json",
            "--bars",
            "bars.parquet",
            "--config",
            "config.toml",
            "--expected-resolved",
            "42",
            "--expected-liquidations",
            "7",
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
    assert args.expected_resolved == 42
    assert args.expected_liquidations == 7
    assert args.training_report == Path("training.json")
