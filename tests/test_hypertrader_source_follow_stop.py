"""Contracts for the report-only source-follow liquidation-tail grid."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("source_follow_stop_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load maker replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_follow_margin_stop_is_report_only_grid() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "source-follow-margin-stop",
            "--out",
            "grid.json",
        ]
    )

    contract = module._experiment_contract(args.candidate_family)

    assert contract["event_policy"] == "pinned_source_recipe_c_follow_only"
    assert contract["stop_policy"] == "fixed margin grid: none, 6%, 10%, 14%, 18%"
    assert contract["runtime_strategy_changed"] is False
