"""Tests for the post-hoc range-onset risk surface."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_range_onset_risk_surface.py"
)


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset range-onset risk surface script is missing")
    spec = spec_from_file_location("multi_asset_range_onset_risk_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_exposure_grid_is_fixed_and_spans_growth_to_tail_boundary() -> None:
    """The mechanical risk ladder must be frozen before outcome inspection."""
    module = _module()

    trials = module.onset_risk_grid()

    assert len(trials) == 10
    assert len(set(trials)) == len(trials)
    assert trials[0] == module.OnsetRiskTrial(0.10, 5.0)
    assert trials[-1] == module.OnsetRiskTrial(0.50, 20.0)
    assert [trial.effective_exposure for trial in trials] == [
        0.5,
        1.0,
        1.5,
        2.0,
        3.0,
        3.5,
        4.0,
        5.0,
        7.0,
        10.0,
    ]


def test_onset_risk_config_preserves_price_stop() -> None:
    """Scaling exposure must keep the stop fixed at 60 price basis points."""
    module = _module()

    config = module.onset_risk_config(
        module.OnsetRiskTrial(0.35, 10.0),
        symbol="SOL",
    )

    assert config.margin_fraction == pytest.approx(0.35)
    assert config.leverage == pytest.approx(10.0)
    assert config.stop_margin_pct == pytest.approx(6.0)
    assert config.max_hold_bars == 48 * 60


def test_evaluate_risk_retains_every_requested_trial() -> None:
    """The risk surface may not drop a losing or insolvent observation."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=60 * 72, freq="1min", tz="UTC")
    close = pd.Series(
        [100.0 + ((position // 360) % 2) * 5.0 for position in range(len(index))],
        index=index,
    )
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1.0,
            "funding_rate": 0.0,
        },
        index=index,
    )
    signals = module.build_range_onset_signals(bars)
    trials = (
        module.OnsetRiskTrial(0.10, 5.0),
        module.OnsetRiskTrial(0.50, 20.0),
    )

    results = module.evaluate_onset_risk(
        bars,
        signals,
        symbol="SOL",
        trials=trials,
    )

    assert len(results) == 2
    assert results[0]["effective_exposure"] == pytest.approx(0.5)
    assert results[1]["effective_exposure"] == pytest.approx(10.0)
    assert all(result["execution_authority"] == "none" for result in results)


def test_cli_requires_explicit_chronological_boundaries() -> None:
    """Every evaluation boundary must be explicit in the command contract."""
    module = _module()

    parsed = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-04-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert parsed.symbol == "SOL"
    assert parsed.pseudo_holdout_end.isoformat() == "2026-07-28T00:00:00+00:00"
