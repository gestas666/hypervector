"""Tests for the bounded multi-asset trend robustness search."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "multi_asset_trend_robustness.py"


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset trend robustness script is missing")
    spec = spec_from_file_location("multi_asset_trend_robustness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_shape_grid_is_fixed_complete_and_contains_the_baseline() -> None:
    """The exploration count must be known before any result is observed."""
    module = _module()

    shapes = module.trend_shape_grid()

    assert len(shapes) == 1_024
    assert len(set(shapes)) == len(shapes)
    assert module.TrendShape("1h", 10, 30, None, 60.0, 48) in shapes
    assert {shape.target_bps for shape in shapes} == {None, 80.0, 150.0, 300.0}
    assert {shape.stop_bps for shape in shapes} == {None, 40.0, 60.0, 100.0}


def test_development_selection_is_deterministic_and_retains_failures() -> None:
    """Selection may rank trials but must not remove losing observations."""
    module = _module()
    trials = [
        _trial("winner", 20.0, 2.0, -5.0, 40, 0),
        _trial("loss", -10.0, 0.5, -3.0, 80, 0),
        _trial("liquidated", 50.0, 3.0, -20.0, 50, 1),
    ]

    result = module.select_development_trials(trials, limit=2)

    assert result["searched_trial_count"] == 3
    assert result["eligible_trial_count"] == 1
    assert result["selected_trial_ids"] == ["winner"]
    assert [trial["trial_id"] for trial in trials] == [
        "winner",
        "loss",
        "liquidated",
    ]


def test_shape_config_uses_asset_cost_liquidation_and_exit_contract() -> None:
    """A shape must become an asset-specific executable simulation contract."""
    module = _module()
    shape = module.TrendShape("1h", 10, 30, None, 60.0, 48)

    config = module.shape_config(shape, symbol="SOL")

    assert config.symbol == "SOL"
    assert config.margin_fraction == pytest.approx(0.10)
    assert config.leverage == pytest.approx(5.0)
    assert config.venue_max_leverage == pytest.approx(20.0)
    assert config.target_margin_pct is None
    assert config.stop_margin_pct == pytest.approx(3.0)
    assert config.max_hold_bars == 48
    assert config.entry_fee_rate == pytest.approx(0.00045)
    assert config.market_exit_slippage_bps == pytest.approx(2.0)


def test_evaluate_shapes_retains_one_complete_trial_contract() -> None:
    """One requested shape must produce one result even with no profitable trade."""
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
    shape = module.TrendShape("1h", 10, 30, None, 60.0, 48)

    trials = module.evaluate_shapes(bars, symbol="SOL", shapes=(shape,))

    assert len(trials) == 1
    assert trials[0]["shape"] == {
        "timeframe": "1h",
        "fast": 10,
        "slow": 30,
        "target_bps": None,
        "stop_bps": 60.0,
        "max_hold_hours": 48,
    }
    assert trials[0]["metrics"]["initial_equity"] == pytest.approx(15_000.0)
    assert trials[0]["execution_authority"] == "none"


def test_run_robustness_keeps_chronological_windows_and_authority(
    tmp_path: Path,
) -> None:
    """The artifact must separate development selection from later evidence."""
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
    shape = module.TrendShape("1h", 2, 3, None, 60.0, 24)

    result = module.run_robustness(
        symbol="SOL",
        bars_path=bars_path,
        funding_paths=[funding_path],
        development_start=index[0].to_pydatetime(),
        development_end=index[24 * 60].to_pydatetime(),
        validation_end=index[48 * 60].to_pydatetime(),
        pseudo_holdout_end=(index[-1] + pd.Timedelta(minutes=1)).to_pydatetime(),
        shapes=(shape,),
        selection_limit=1,
    )

    assert result["symbol"] == "SOL"
    assert result["execution_authority"] == "none"
    assert result["development"]["trial_count"] == 1
    assert result["selection"]["searched_trial_count"] == 1
    assert result["validation"]["start_utc"] == "2026-01-02T00:00:00+00:00"
    assert result["pseudo_holdout"]["start_utc"] == "2026-01-03T00:00:00+00:00"


def test_cli_requires_explicit_chronological_evidence_boundaries() -> None:
    """The command line must freeze every data boundary before searching."""
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
    assert parsed.development_end.isoformat() == "2026-01-28T00:00:00+00:00"
    assert parsed.selection_limit == 12


def _trial(
    trial_id: str,
    return_pct: float,
    profit_factor: float,
    drawdown_pct: float,
    trades: int,
    liquidations: int,
) -> dict[str, object]:
    return {
        "trial_id": trial_id,
        "metrics": {
            "return_pct": return_pct,
            "profit_factor": profit_factor,
            "maximum_drawdown_pct": drawdown_pct,
            "completed_trades": trades,
            "liquidations": liquidations,
            "insolvent": False,
        },
    }
