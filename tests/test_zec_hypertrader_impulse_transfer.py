"""Corrected Hypertrader impulse-transfer contracts for V83 ZEC research."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hypervector.research.fixed_risk_signal_screen import FrictionProfile
from hypervector.research.zec_hypertrader_impulse_transfer import (
    build_impulse_signals,
    portfolio_config,
    profile_supported,
)


def test_frozen_oversold_gate_emits_long_with_structural_stop() -> None:
    """A completed falling sequence must activate the exact three source gates."""
    bars = _falling_bars(40)
    signals = build_impulse_signals(bars)
    assert bool(signals["long_entry"].iloc[-1]) is True
    assert bool(signals["short_entry"].iloc[-1]) is False
    assert float(signals["stop_price"].iloc[-1]) < float(bars["close"].iloc[-1])
    assert signals["long_signal_name"].iloc[-1] == (
        "zec_hypertrader_impulse_5m_long_corrected_v1"
    )


def test_signals_are_append_invariant() -> None:
    """Future bars must not change any earlier gate or structural stop."""
    prefix = _falling_bars(50)
    extended = _falling_bars(65)
    expected = build_impulse_signals(prefix)
    actual = build_impulse_signals(extended).loc[prefix.index]
    pd.testing.assert_frame_equal(actual, expected)


def test_gap_resets_indicator_readiness() -> None:
    """Post-gap bars must rebuild thirty completed observations before entry."""
    before = _falling_bars(40)
    after = _falling_bars(20, start=before.index[-1] + pd.Timedelta(minutes=10))
    bars = pd.concat([before, after])
    signals = build_impulse_signals(bars)
    assert not signals.loc[after.index, "long_entry"].any()


def test_portfolio_contract_corrects_time_leverage_and_cost_units() -> None:
    """V83 must not reproduce 40x leverage or fivefold hold-duration inflation."""
    config = portfolio_config(FrictionProfile("stress_20bps_rt", 5.5))
    assert config.symbol == "ZEC"
    assert config.initial_equity == 5_000.0
    assert config.margin_fraction == 0.02
    assert config.leverage == 5.0
    assert config.venue_max_leverage == 10.0
    assert config.maximum_notional_usd == 500.0
    assert config.minimum_stop_distance_bps == 20.0
    assert config.maximum_stop_distance_bps == 250.0
    assert config.target_r_multiple == 7.987184761509152
    assert config.max_hold_seconds == 1_380
    assert config.entry_fee_rate == 0.00045
    assert config.target_fee_rate == 0.00045
    assert config.market_exit_fee_rate == 0.00045
    assert config.entry_slippage_bps == 5.5
    assert config.market_exit_slippage_bps == 5.5
    assert config.same_direction_reentry_requires_reset is True


def test_support_gate_requires_trade_count_tail_and_month_stability() -> None:
    """A positive aggregate must fail if sparse, tail-driven, or monthly unstable."""
    passing: dict[str, object] = {
        "completed_trades": 30,
        "net_pnl_usd": 10.0,
        "profit_factor": 1.1,
        "net_excluding_largest_winner_usd": 1.0,
        "maximum_drawdown_pct": -4.0,
        "liquidations": 0,
        "insolvent": False,
        "monthly_net_pnl_usd": {"2025-10": 1.0, "2025-11": -1.0},
    }
    assert profile_supported(passing) is True
    for key, value in (
        ("completed_trades", 29),
        ("net_excluding_largest_winner_usd", 0.0),
        ("monthly_net_pnl_usd", {"2025-10": -1.0, "2025-11": 1.0}),
    ):
        failing = {**passing, key: value}
        if key == "monthly_net_pnl_usd":
            failing[key] = {"2025-10": -1.0, "2025-11": -1.0, "2025-12": 1.0}
        assert profile_supported(failing) is False


def _falling_bars(
    count: int,
    *,
    start: pd.Timestamp | None = None,
) -> pd.DataFrame:
    origin = start or pd.Timestamp(datetime(2025, 10, 2, 14, tzinfo=UTC))
    index = pd.date_range(origin, periods=count, freq="5min")
    close = pd.Series([100.0 - 0.25 * value for value in range(count)], index=index)
    return pd.DataFrame(
        {
            "open": close + 0.10,
            "high": close + 0.20,
            "low": close - 0.20,
            "close": close,
            "volume": 100.0,
            "funding_rate": 0.0,
        },
        index=index,
    )
