"""Frozen V86 ZEC UT-Bot peak-harvest transfer contracts."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.fixed_risk_signal_screen import FrictionProfile
from hypervector.research.zec_utbot_peak_harvest_transfer import (
    STRATEGY_ID,
    UtBotPeakHarvestConfig,
    build_utbot_short_signals,
    build_utbot_signals,
    build_utbot_state,
    portfolio_config,
    profile_supported,
    short_portfolio_config,
)


def test_regular_atr_and_ha_source_emit_fresh_bidirectional_crosses() -> None:
    """The recursive stop must flip once per completed-bar source crossing."""
    bars = _signal_bars([100.0] * 13 + [97.0, 103.0])

    state = build_utbot_state(bars)

    assert state.index[state["short_entry"]].tolist() == [bars.index[13]]
    assert state.index[state["long_entry"]].tolist() == [bars.index[14]]
    assert state.loc[bars.index[13], "atr"] == pytest.approx(28.0 / 13.0)
    assert state.loc[bars.index[13], "ha_close"] == pytest.approx(97.0)


def test_completed_four_hour_cross_projects_to_last_decision_row() -> None:
    """A four-hour close may only schedule the following 15-minute open."""
    bars = _execution_bars([100.0] * 13 + [97.0, 103.0])

    signals = build_utbot_signals(bars)

    short_at = bars.index[13 * 16 + 15]
    long_at = bars.index[14 * 16 + 15]
    assert signals.index[signals["short_entry"]].tolist() == [short_at]
    assert signals.index[signals["long_entry"]].tolist() == [long_at]
    assert bool(signals.loc[short_at, "long_exit"]) is True
    assert bool(signals.loc[long_at, "short_exit"]) is True
    assert signals.loc[short_at, "short_signal_name"] == STRATEGY_ID


def test_signals_are_append_invariant_and_gap_reset() -> None:
    """Future values and pre-gap state must not alter an earlier signal prefix."""
    prefix = _execution_bars([100.0] * 13 + [97.0, 103.0])
    suffix = _execution_bars([70.0] * 14)
    suffix.index = pd.date_range(
        prefix.index[-1] + pd.Timedelta(minutes=15),
        periods=len(suffix),
        freq="15min",
        tz="UTC",
    )
    expected = build_utbot_signals(prefix)
    actual = build_utbot_signals(pd.concat([prefix, suffix])).loc[prefix.index]
    pd.testing.assert_frame_equal(actual, expected)

    gapped = pd.concat(
        [
            prefix,
            _execution_bars([80.0] * 12).set_axis(
                pd.date_range(
                    prefix.index[-1] + pd.Timedelta(hours=4, minutes=15),
                    periods=12 * 16,
                    freq="15min",
                    tz="UTC",
                )
            ),
        ]
    )
    after_gap = build_utbot_signals(gapped).loc[gapped.index > prefix.index[-1]]
    assert not after_gap["long_entry"].any()
    assert not after_gap["short_entry"].any()


def test_frozen_risk_cost_and_peak_lock_contract() -> None:
    """The research lifecycle must match the preregistered probation shape."""
    config = portfolio_config(FrictionProfile("stress_20bps_rt", 5.5))
    assert config.symbol == "ZEC"
    assert config.initial_equity == 5_000.0
    assert config.margin_fraction == 0.02
    assert config.leverage == 5.0
    assert config.venue_max_leverage == 10.0
    assert config.maximum_notional_usd == 500.0
    assert config.risk_fraction_per_position == 0.005
    assert config.stop_margin_pct == 20.0
    assert config.max_hold_seconds == 2_592_000
    assert config.entry_fee_rate == 0.00045
    assert config.market_exit_fee_rate == 0.00045
    assert config.entry_slippage_bps == 5.5
    assert config.market_exit_slippage_bps == 5.5
    assert config.reverse_on_opposite_signal is True
    lock = config.completed_bar_peak_lock
    assert lock is not None
    assert lock.activation_roe_pct == 10.0
    assert lock.locked_peak_ratio == 0.8


def test_selected_short_sleeve_preserves_buy_exit_without_long_entries() -> None:
    """Directional selection must disable longs without suppressing short exits."""
    bars = _execution_bars([100.0] * 13 + [97.0, 103.0])

    signals = build_utbot_short_signals(bars)

    assert not signals["long_entry"].any()
    assert signals["short_entry"].sum() == 1
    assert signals["short_exit"].sum() == 1
    assert signals["short_signal_name"].iloc[-1] == (
        "zec_utbot_ha4h_atr13_peak80_short_v1"
    )
    config = short_portfolio_config(FrictionProfile("nominal_14bps_rt", 2.5))
    assert config.close_on_opposite_signal is True
    assert config.reverse_on_opposite_signal is False


def test_support_gate_requires_count_tail_months_and_drawdown() -> None:
    """Positive headline PnL alone must not qualify a route."""
    passing: dict[str, object] = {
        "completed_trades": 15,
        "net_pnl_usd": 10.0,
        "profit_factor": 1.1,
        "net_excluding_largest_winner_usd": 1.0,
        "maximum_drawdown_pct": -4.0,
        "liquidations": 0,
        "insolvent": False,
        "monthly_net_pnl_usd": {"2026-01": 1.0, "2026-02": -1.0},
    }
    assert profile_supported(passing) is True
    for key, value in (
        ("completed_trades", 14),
        ("net_excluding_largest_winner_usd", 0.0),
        ("maximum_drawdown_pct", -5.01),
        ("monthly_net_pnl_usd", {"2026-01": -1.0, "2026-02": -1.0}),
    ):
        assert profile_supported({**passing, key: value}) is False


def test_config_rejects_parameter_or_authority_drift() -> None:
    """This transfer cannot become a hidden ZEC tuning surface."""
    with pytest.raises(ValueError, match="parameters"):
        UtBotPeakHarvestConfig(atr_period=14)
    with pytest.raises(ValueError, match="report-only"):
        UtBotPeakHarvestConfig(execution_authority="live")


def _signal_bars(closes: list[float]) -> pd.DataFrame:
    values = np.asarray(closes, dtype=np.float64)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
        },
        index=pd.date_range("2026-01-01", periods=len(values), freq="4h", tz="UTC"),
    )


def _execution_bars(closes: list[float]) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for timestamp, row in _signal_bars(closes).iterrows():
        for offset in range(16):
            index.append(timestamp + pd.Timedelta(minutes=15 * offset))
            records.append({column: float(row[column]) for column in row.index})
    return pd.DataFrame.from_records(records, index=pd.DatetimeIndex(index))
