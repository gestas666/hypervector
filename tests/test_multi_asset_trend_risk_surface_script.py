"""Tests for the chronological multi-asset trend risk surface."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "multi_asset_trend_risk_surface.py"


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset trend risk surface script is missing")
    spec = spec_from_file_location("multi_asset_trend_risk_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_risk_grid_is_fixed_complete_and_includes_aggressive_limits() -> None:
    """Every predeclared exposure must remain visible in the search artifact."""
    module = _module()

    trials = module.risk_trial_grid()

    assert len(trials) == 96
    assert len(set(trials)) == len(trials)
    assert module.TrendRiskTrial("1h", 10, 30, None, 60.0, 48, 0.10, 5.0) in trials
    assert module.TrendRiskTrial("1h", 10, 30, None, 40.0, 96, 1.00, 20.0) in trials
    assert {trial.margin_fraction for trial in trials} == {
        0.10,
        0.20,
        0.35,
        0.50,
        0.70,
        1.00,
    }
    assert {trial.leverage for trial in trials} == {5.0, 10.0, 15.0, 20.0}


def test_risk_config_preserves_price_stop_when_leverage_changes() -> None:
    """A 60-bps stop must stay 60 bps in price space at every leverage."""
    module = _module()
    trial = module.TrendRiskTrial("1h", 10, 30, None, 60.0, 48, 0.70, 20.0)

    config = module.risk_config(trial, symbol="SOL")

    assert config.symbol == "SOL"
    assert config.margin_fraction == pytest.approx(0.70)
    assert config.leverage == pytest.approx(20.0)
    assert config.venue_max_leverage == pytest.approx(20.0)
    assert config.stop_margin_pct == pytest.approx(12.0)
    assert config.max_hold_bars == 48 * 60


def test_evaluate_risk_trials_retains_every_requested_result() -> None:
    """Negative and liquidated trials must not disappear from the surface."""
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
    trials = (
        module.TrendRiskTrial("1h", 2, 3, None, 60.0, 48, 0.10, 5.0),
        module.TrendRiskTrial("1h", 2, 3, None, 60.0, 48, 1.00, 20.0),
    )

    results = module.evaluate_risk_trials(bars, symbol="SOL", trials=trials)

    assert len(results) == 2
    assert results[0]["risk"]["margin_fraction"] == pytest.approx(0.10)
    assert results[1]["risk"]["leverage"] == pytest.approx(20.0)
    assert all(result["execution_authority"] == "none" for result in results)


def test_run_surface_keeps_all_chronological_windows_and_full_year(
    tmp_path: Path,
) -> None:
    """Risk trials must be evaluated independently on each frozen interval."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=72 * 60, freq="1min", tz="UTC")
    close = pd.Series(
        [100.0 + ((position // 180) % 2) for position in range(len(index))],
        index=index,
    )
    bars = pd.DataFrame(
        {
            "timestamp": index,
            "open": close.to_numpy(),
            "high": (close + 0.5).to_numpy(),
            "low": (close - 0.5).to_numpy(),
            "close": close.to_numpy(),
            "volume": 1.0,
            "source": "hl",
        }
    )
    funding = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=72, freq="1h", tz="UTC"),
            "funding_rate": 0.0,
        }
    )
    bars_path = tmp_path / "SOL.parquet"
    funding_path = tmp_path / "SOL_funding.parquet"
    bars.to_parquet(bars_path, index=False)
    funding.to_parquet(funding_path, index=False)
    trial = module.TrendRiskTrial("1h", 2, 3, None, 60.0, 24, 0.35, 10.0)

    result = module.run_surface(
        symbol="SOL",
        bars_path=bars_path,
        funding_paths=[funding_path],
        development_start=index[0].to_pydatetime(),
        development_end=index[24 * 60].to_pydatetime(),
        validation_end=index[48 * 60].to_pydatetime(),
        pseudo_holdout_end=(index[-1] + pd.Timedelta(minutes=1)).to_pydatetime(),
        trials=(trial,),
    )

    assert result["symbol"] == "SOL"
    assert result["execution_authority"] == "none"
    assert result["trial_count"] == 1
    assert result["development"]["trial_count"] == 1
    assert result["validation"]["start_utc"] == "2026-01-02T00:00:00+00:00"
    assert result["pseudo_holdout"]["start_utc"] == "2026-01-03T00:00:00+00:00"
    assert result["continuous"]["trial_count"] == 1


def test_cli_requires_explicit_data_boundaries() -> None:
    """The risk surface command must freeze every evidence interval."""
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
