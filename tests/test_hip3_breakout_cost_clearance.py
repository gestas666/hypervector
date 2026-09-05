"""Cost-derived clearance challenger for the HIP-3 pressure breakout."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_breakout_cost_clearance import (
    breakout_cost_clearance_report,
    build_breakout_cost_clearance_signals,
    evaluate_breakout_cost_clearance,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_swing_transfer import common_transfer_windows

from test_hip3_breakout_pressure_transfer import _asset, _friction


def _bars(
    closes: list[float],
    pressures: list[float],
    *,
    gaps: list[int] | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "decision_imbalance_10": pressures,
            "gap_before_bars": gaps or [0] * len(closes),
        },
        index=index,
    )


def _config() -> Hip3BreakoutPressureConfig:
    return Hip3BreakoutPressureConfig(
        breakout_lookback_bars=3,
        fast_ema=2,
        slow_ema=3,
        minimum_abs_imbalance=0.2,
        maximum_stop_bps=80.0,
    )


def _challenger(
    bars: pd.DataFrame,
    *,
    clearance_bps: float = 10.0,
) -> pd.DataFrame:
    control = build_breakout_pressure_signals(bars, _config())
    return build_breakout_cost_clearance_signals(
        bars,
        control,
        _config(),
        minimum_breakout_clearance_bps=clearance_bps,
    )


def test_delays_long_onset_until_close_clears_cost_threshold() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 100.05, 100.2],
        [0.0, 0.0, 0.0, 0.5, 0.5],
    )
    control = build_breakout_pressure_signals(bars, _config())

    challenger = _challenger(bars)

    assert control["long_entry"].tolist() == [False, False, False, True, False]
    assert challenger["long_entry"].tolist() == [False, False, False, False, True]
    assert challenger["entry_direction"].iloc[-1] == "long"
    assert challenger["stop_price"].iloc[-1] == pytest.approx(100.0)
    assert challenger["minimum_breakout_clearance_bps"].iloc[-1] == 10.0


def test_applies_clearance_symmetrically_to_short_onset() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 99.95, 99.8],
        [0.0, 0.0, 0.0, -0.5, -0.5],
    )
    control = build_breakout_pressure_signals(bars, _config())

    challenger = _challenger(bars)

    assert control["short_entry"].tolist() == [False, False, False, True, False]
    assert challenger["short_entry"].tolist() == [False, False, False, False, True]
    assert challenger["entry_direction"].iloc[-1] == "short"
    assert challenger["stop_price"].iloc[-1] == pytest.approx(100.0)


def test_gap_requires_new_post_gap_history_before_challenger_onset() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 100.2, 100.3, 100.4, 100.6],
        [0.5] * 7,
        gaps=[0, 0, 0, 1, 0, 0, 0],
    )

    challenger = _challenger(bars)

    assert not challenger["long_entry"].iloc[3:6].any()
    assert challenger["long_entry"].iloc[6]


def test_future_prices_cannot_change_prior_challenger_signals() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 100.05, 100.2, 100.3],
        [0.0, 0.0, 0.0, 0.5, 0.5, 0.5],
    )
    changed = bars.copy()
    changed.loc[changed.index[-1], ["open", "high", "low", "close"]] = 50.0

    original = _challenger(bars)
    revised = _challenger(changed)

    pd.testing.assert_frame_equal(original.iloc[:-1], revised.iloc[:-1])


@pytest.mark.parametrize("clearance", [0.0, -1.0, float("inf"), float("nan")])
def test_rejects_nonpositive_or_nonfinite_clearance(clearance: float) -> None:
    bars = _bars([100.0] * 4, [0.0] * 4)
    control = build_breakout_pressure_signals(bars, _config())

    with pytest.raises(ValueError, match="clearance"):
        build_breakout_cost_clearance_signals(
            bars,
            control,
            _config(),
            minimum_breakout_clearance_bps=clearance,
        )


def test_rejects_signal_index_that_does_not_match_bars() -> None:
    bars = _bars([100.0] * 4, [0.0] * 4)
    control = build_breakout_pressure_signals(bars, _config()).iloc[:-1]

    with pytest.raises(ValueError, match="index"):
        build_breakout_cost_clearance_signals(
            bars,
            control,
            _config(),
            minimum_breakout_clearance_bps=10.0,
        )


def test_evaluates_control_and_challenger_on_fixed_unsealed_windows() -> None:
    asset = _asset()
    windows = common_transfer_windows((asset,))

    result = evaluate_breakout_cost_clearance(
        asset,
        _friction(),
        windows,
        _config(),
        minimum_breakout_clearance_bps=10.0,
    )

    assert result.execution_authority == "none"
    assert result.holdout_status == "sealed_not_evaluated"
    assert len(result.control.development_folds) == 3
    assert len(result.challenger.development_folds) == 3
    assert result.control.development.completed_trades > 0
    assert result.challenger.development.completed_trades > 0
    all_trades = (
        *result.control.development.trades,
        *result.control.validation_nominal.trades,
        *result.control.validation_stress.trades,
        *result.challenger.development.trades,
        *result.challenger.validation_nominal.trades,
        *result.challenger.validation_stress.trades,
    )
    assert all(
        pd.Timestamp(trade.signal_time_utc) < windows.validation_end_utc
        for trade in all_trades
    )


def test_report_preserves_side_economics_and_largest_winner_sensitivity() -> None:
    asset = _asset()
    windows = common_transfer_windows((asset,))
    result = evaluate_breakout_cost_clearance(
        asset,
        _friction(),
        windows,
        _config(),
        minimum_breakout_clearance_bps=10.0,
    )

    report = breakout_cost_clearance_report(result)

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    assert report["holdout"]["metrics_accessed"] is False
    assert set(report["arms"]) == {"control", "challenger"}
    for arm in report["arms"].values():
        assert len(arm["development_folds"]) == 3
        for cell in (arm["development"], *arm["development_folds"]):
            assert set(cell["direction_trades"]) == {"long", "short"}
            assert set(cell["direction_net_pnl_usd"]) == {"long", "short"}
            assert "net_pnl_excluding_largest_winner_usd" in cell


def test_evaluator_rejects_window_that_would_access_missing_bars() -> None:
    asset = _asset()
    windows = common_transfer_windows((asset,))
    shortened = type(windows)(
        windows.development_start_utc,
        windows.development_end_utc,
        windows.validation_end_utc,
        windows.holdout_end_utc + pd.Timedelta(days=1),
        windows.development_folds,
    )

    with pytest.raises(ValueError, match="window"):
        evaluate_breakout_cost_clearance(
            asset,
            _friction(),
            shortened,
            _config(),
            minimum_breakout_clearance_bps=10.0,
        )
