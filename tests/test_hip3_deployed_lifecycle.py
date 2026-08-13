"""Bar-level simulation contract for deployed v25 HIP-3 lifecycle shape."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleSpec,
    deployed_lifecycle_portfolio_config,
    deployed_lifecycle_signals,
    evaluate_deployed_lifecycle,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=5, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [100.2] * 5,
            "low": [99.9, 99.9, 99.0, 99.9, 99.9],
            "close": [100.0] * 5,
            "entry_bid": [100.0] * 5,
            "entry_ask": [100.0] * 5,
            "decision_bid": [100.0] * 5,
            "decision_ask": [100.0] * 5,
            "gap_before_bars": [0] * 5,
            "funding_rate": [0.0] * 5,
        },
        index=index,
    )


def _asset() -> Hip3TransferAsset:
    return Hip3TransferAsset("xyz:SP500", 50.0, _bars())


def _friction() -> Hip3ExecutionFriction:
    return Hip3ExecutionFriction(75.0, 0.00001, 1.0, 0.0, 5.0, 2.0)


def _signals() -> pd.DataFrame:
    index = _bars().index
    return pd.DataFrame(
        {
            "long_entry": [True, False, False, False, False],
            "short_entry": [False] * 5,
            "long_exit": [False, True, False, False, False],
            "short_exit": [False] * 5,
            "stop_price": [95.0] * 5,
            "target_price": [110.0] * 5,
            "signal_name": ["live_recipe"] * 5,
        },
        index=index,
    )


def test_deployed_signals_retain_entries_but_remove_research_only_exits() -> None:
    source = _signals()

    deployed = deployed_lifecycle_signals(source)

    assert deployed["long_entry"].equals(source["long_entry"])
    assert deployed["short_entry"].equals(source["short_entry"])
    assert not deployed["long_exit"].any()
    assert not deployed["short_exit"].any()
    assert deployed["stop_price"].isna().all()
    assert deployed["target_price"].isna().all()


def test_signal_exit_variant_retains_recipe_exit_columns() -> None:
    """The bounded challenger must differ only by honoring signal exits."""
    source = _signals()
    spec = Hip3DeployedLifecycleSpec(signal_exit_policy="honor")

    challenger = deployed_lifecycle_signals(source, spec=spec)

    assert challenger["long_entry"].equals(source["long_entry"])
    assert challenger["short_entry"].equals(source["short_entry"])
    assert challenger["long_exit"].equals(source["long_exit"])
    assert challenger["short_exit"].equals(source["short_exit"])
    assert challenger["stop_price"].isna().all()
    assert challenger["target_price"].isna().all()


def test_early_adverse_variant_binds_fixed_path_conditions() -> None:
    """The preregistered challenger must retain exits and bind exact thresholds."""
    spec = Hip3DeployedLifecycleSpec(signal_exit_policy="early_adverse")

    challenger = deployed_lifecycle_signals(_signals(), spec=spec)
    config = deployed_lifecycle_portfolio_config(
        _asset(),
        _friction(),
        stress=False,
        spec=spec,
    )

    assert challenger["long_exit"].equals(_signals()["long_exit"])
    assert config.signal_exit_max_age_bars == 8
    assert config.signal_exit_max_mfe_bps == pytest.approx(20.0)
    assert config.signal_exit_min_adverse_bps == pytest.approx(13.0)


def test_deployed_config_matches_v25_fixed_stop_and_hold_contract() -> None:
    config = deployed_lifecycle_portfolio_config(
        _asset(),
        _friction(),
        stress=False,
    )

    assert config.margin_fraction == pytest.approx(0.03)
    assert config.leverage == pytest.approx(5.0)
    assert config.stop_margin_pct == pytest.approx(4.0)
    assert config.target_margin_pct is None
    assert config.max_hold_bars == 96
    assert config.same_direction_reentry_requires_reset is False
    assert config.close_on_opposite_signal is True
    assert config.reverse_on_opposite_signal is False
    assert config.open_bid_column == "entry_bid"
    assert config.open_ask_column == "entry_ask"
    assert config.close_bid_column == "decision_bid"
    assert config.close_ask_column == "decision_ask"


def test_deployed_lifecycle_ignores_signal_exit_and_uses_fixed_80_bps_stop() -> None:
    bars = _bars()
    signals = deployed_lifecycle_signals(_signals())
    config = deployed_lifecycle_portfolio_config(
        _asset(),
        _friction(),
        stress=False,
    )

    report = evaluate_shared_bar_portfolio(bars, signals, config)

    assert report.completed_trades == 1
    trade = report.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.entry_position == 1
    assert trade.exit_position == 2
    assert trade.stop_price == pytest.approx(99.2)


def test_deployed_maximum_hold_is_derived_from_exact_bar_clock() -> None:
    spec = Hip3DeployedLifecycleSpec(
        stop_bps=80.0,
        maximum_hold_seconds=3_600,
        bar_minutes=15,
    )

    assert spec.maximum_hold_bars == 4

    with pytest.raises(ValueError, match="whole completed bars"):
        Hip3DeployedLifecycleSpec(
            stop_bps=80.0,
            maximum_hold_seconds=1_000,
            bar_minutes=15,
        )
    with pytest.raises(ValueError, match="signal_exit_policy"):
        Hip3DeployedLifecycleSpec(signal_exit_policy="unsupported")


def test_deployed_evaluation_never_reads_sealed_holdout_prices() -> None:
    bars = pd.concat([_bars(), _bars().iloc[1:].copy()])
    bars.index = pd.date_range("2026-01-01", periods=len(bars), freq="15min", tz="UTC")
    windows = Hip3TransferWindows(
        development_start_utc=bars.index[0],
        development_end_utc=bars.index[3],
        validation_end_utc=bars.index[6],
        holdout_end_utc=bars.index[-1] + pd.Timedelta(minutes=15),
        development_folds=((bars.index[0], bars.index[3]),),
    )
    bars.loc[bars.index[6] :, ["open", "high", "low", "close"]] = float("nan")
    signals = pd.DataFrame(
        {
            "long_entry": [True] + [False] * (len(bars) - 1),
            "short_entry": [False] * len(bars),
            "long_exit": [False] * len(bars),
            "short_exit": [False] * len(bars),
        },
        index=bars.index,
    )
    asset = Hip3TransferAsset("xyz:SP500", 50.0, bars)

    cells = evaluate_deployed_lifecycle(
        asset,
        _friction(),
        deployed_lifecycle_signals(signals),
        windows,
    )

    assert {(cell.phase, cell.friction) for cell in cells} == {
        ("development", "nominal"),
        ("development", "stress"),
        ("validation", "nominal"),
        ("validation", "stress"),
    }
    assert all(cell.execution_authority == "none" for cell in cells)
    assert all(cell.report.forced_end_exits == 0 for cell in cells)
    assert all(cell.tail_suppressed_entries >= 0 for cell in cells)
    assert all(cell.gap_crossing_trades == 0 for cell in cells)
    assert all(
        trade.exit_time_utc < windows.validation_end_utc.isoformat()
        for cell in cells
        for trade in cell.report.trades
    )
