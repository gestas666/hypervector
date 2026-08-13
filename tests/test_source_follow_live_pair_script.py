"""Report-only contract for paired source-follow live-tape replay."""

from __future__ import annotations

import importlib.util
from datetime import UTC
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_live_pair.py")
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("source_live_pair_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load live pair script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_pair_contract_has_no_execution_or_model_authority() -> None:
    module = _load_script()

    contract = module.experiment_contract()

    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["execution_authority"] == "none"
    assert contract["model_authority"] == "observe"
    assert contract["receipt_timestamp_source"] == "recorded"
    assert contract["paired_profiles"] == ["uniform", "weak_choppy_half"]
    assert contract["maximum_context_gap_seconds"] == 15.0
    assert contract["maximum_funding_age_seconds"] == 5.0


def test_live_pair_allocation_is_explicit_and_propagated() -> None:
    module = _load_script()

    args = module.parse_args(
        [
            "--database",
            "research.duckdb",
            "--labels",
            "labels.parquet",
            "--start",
            "2026-07-30T00:00:00Z",
            "--end",
            "2026-07-30T01:00:00Z",
            "--margin-fraction",
            "0.35",
            "--out",
            "paired.json",
        ]
    )

    assert args.margin_fraction == pytest.approx(0.35)
    assert module.experiment_contract(args.margin_fraction)["margin_fraction"] == 0.35
    assert module._portfolio_config(args.margin_fraction).margin_fraction == 0.35


@pytest.mark.parametrize("value", ["0", "-0.1", "1.1", "nan", "inf"])
def test_live_pair_allocation_rejects_invalid_values(value: str) -> None:
    module = _load_script()

    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--database",
                "research.duckdb",
                "--labels",
                "labels.parquet",
                "--start",
                "2026-07-30T00:00:00Z",
                "--end",
                "2026-07-30T01:00:00Z",
                "--margin-fraction",
                value,
                "--out",
                "paired.json",
            ]
        )


def test_label_bar_bounds_use_project_utc_identity() -> None:
    module = _load_script()
    bounds = getattr(module, "_label_bar_bounds", None)
    assert bounds is not None
    labels = pd.DataFrame(
        index=pd.date_range("2026-07-30", periods=2, freq="5min", tz="UTC")
    )

    start, end = bounds(labels)

    assert start.tzinfo is UTC
    assert end.tzinfo is UTC
    assert end.isoformat() == "2026-07-30T00:10:00+00:00"
