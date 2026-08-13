"""Tests for the post-hoc range-onset friction stress surface."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "multi_asset_range_onset_friction_surface.py"
)


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset range-onset friction surface script is missing")
    spec = spec_from_file_location("multi_asset_range_onset_friction_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_friction_grid_is_frozen_and_complete() -> None:
    """Every predeclared shape, exposure, and slippage must be retained."""
    module = _module()

    trials = module.friction_grid()

    assert len(trials) == 16
    assert len(set(trials)) == len(trials)
    assert {trial.stop_bps for trial in trials} == {60.0, 80.0}
    assert {trial.effective_exposure for trial in trials} == {0.5, 3.0}
    assert {trial.slippage_bps for trial in trials} == {2.0, 5.0, 10.0, 20.0}


def test_friction_config_applies_adverse_slippage_to_every_market_fill() -> None:
    """Entry, ordinary exit, and liquidation impact use the stressed value."""
    module = _module()
    trial = module.OnsetFrictionTrial(80.0, 0.20, 15.0, 10.0)

    config = module.friction_config(trial, symbol="SOL")

    assert config.margin_fraction == pytest.approx(0.20)
    assert config.leverage == pytest.approx(15.0)
    assert config.stop_margin_pct == pytest.approx(12.0)
    assert config.max_hold_bars == 48 * 60
    assert config.entry_slippage_bps == pytest.approx(10.0)
    assert config.market_exit_slippage_bps == pytest.approx(10.0)
    assert config.liquidation_slippage_bps == pytest.approx(10.0)


def test_evaluation_retains_losing_trials() -> None:
    """Friction results must not filter observations based on outcomes."""
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
        module.OnsetFrictionTrial(60.0, 0.10, 5.0, 2.0),
        module.OnsetFrictionTrial(80.0, 0.20, 15.0, 20.0),
    )

    results = module.evaluate_friction_trials(
        bars,
        signals,
        symbol="SOL",
        trials=trials,
    )

    assert len(results) == 2
    assert results[0]["slippage_bps_per_side"] == pytest.approx(2.0)
    assert results[1]["slippage_bps_per_side"] == pytest.approx(20.0)
    assert all(result["execution_authority"] == "none" for result in results)


def test_cli_requires_explicit_chronological_boundaries() -> None:
    """The stress test must declare every chronological boundary."""
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
    assert parsed.development_start.isoformat() == "2025-07-28T00:00:00+00:00"
