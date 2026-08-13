"""Portfolio-screen contracts for the 15-minute Swing/HA challenger."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.swing_ha_screen import (
    SwingHaScreenConfig,
    base_trial_grid,
    delayed_signals,
    evaluate_swing_ha_cell,
    order_block_trial_grid,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _market(rows: int = 40) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    close = [100.0 + position * 0.2 for position in range(rows)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.4 for value in close],
            "low": [value - 0.4 for value in close],
            "close": close,
            "funding_rate": [0.0] * rows,
        },
        index=index,
    )


def _signals(index: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame(
        False,
        index=index,
        columns=["long_entry", "short_entry", "long_exit", "short_exit"],
    )
    frame.loc[index[2], "long_entry"] = True
    frame.loc[index[8], "long_exit"] = True
    frame.loc[index[12], "short_entry"] = True
    frame.loc[index[18], "short_exit"] = True
    frame["long_signal_name"] = "swing_ha_long@15m"
    frame["short_signal_name"] = "swing_ha_short@15m"
    frame["stop_price"] = float("nan")
    return frame


def test_default_screen_models_full_taker_friction_without_hidden_hold() -> None:
    config = SwingHaScreenConfig()

    portfolio = config.portfolio_config(symbol="BTC", venue_max_leverage=40.0)

    assert portfolio.entry_fee_rate == pytest.approx(0.00045)
    assert portfolio.market_exit_fee_rate == pytest.approx(0.00045)
    assert portfolio.entry_slippage_bps == pytest.approx(2.0)
    assert portfolio.market_exit_slippage_bps == pytest.approx(2.0)
    assert portfolio.max_hold_bars is None
    assert portfolio.target_margin_pct is None
    assert portfolio.stop_margin_pct is None


def test_base_grid_contains_requested_and_source_control_ema_pairs() -> None:
    pairs = {(trial.fast_ema, trial.slow_ema) for trial in base_trial_grid()}

    assert (9, 21) in pairs
    assert (50, 200) in pairs
    assert len(base_trial_grid()) == 72


def test_order_block_grid_retains_control_agreement_and_stop_roles() -> None:
    base = SwingHaSignalConfig(fast_ema=9, slow_ema=21, pivot_length=5)

    trials = order_block_trial_grid(base)

    roles = {trial.order_block_role for trial in trials}
    assert roles == {"none", "agreement", "structural_stop"}
    assert len(trials) == 13


def test_screen_retains_long_and_short_trades_with_real_market_prices() -> None:
    market = _market()
    signals = _signals(market.index)

    cell = evaluate_swing_ha_cell(
        market,
        signals,
        symbol="BTC",
        signal_config=SwingHaSignalConfig(),
        venue_max_leverage=40.0,
    )

    assert cell.completed_trades == 2
    assert cell.direction_trades == {"long": 1, "short": 1}
    assert cell.total_fees_usd > 0.0
    assert cell.execution_authority == "none"
    assert all(trade["entry_price"] != 0.0 for trade in cell.trade_records)


def test_delayed_entry_moves_only_entry_instructions_one_bar() -> None:
    signals = _signals(_market().index)

    delayed = delayed_signals(signals, bars=1)

    assert not delayed["long_entry"].iloc[2]
    assert delayed["long_entry"].iloc[3]
    assert delayed["long_exit"].equals(signals["long_exit"])
