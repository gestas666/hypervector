from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from hypervector.research.mu_hip3_candidate import (
    MU_PROVIDER_ID,
    MU_SYMBOL,
    MuDepthFriction,
    MuTrial,
    chronological_windows,
    evaluate_mu_swing_candidate,
    quote_mu_bars,
    select_mu_trial,
    summarize_trades,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _bars(count: int = 480) -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=count, freq="15min", tz="UTC")
    wave = np.sin(np.arange(count) / 13.0) * 6.0
    slow = np.sin(np.arange(count) / 91.0) * 18.0
    close = 100.0 + wave + slow
    open_price = np.roll(close, 1)
    open_price[0] = close[0]
    return pd.DataFrame(
        {
            "open": open_price,
            "high": np.maximum(open_price, close) + 0.8,
            "low": np.minimum(open_price, close) - 0.8,
            "close": close,
            "volume": 100.0,
            "gap_before_bars": 0,
            "funding_rate": 0.0,
        },
        index=index,
    )


def _friction() -> MuDepthFriction:
    return MuDepthFriction(
        notional_usd=75.0,
        effective_taker_fee_rate=0.0000864,
        regular_round_trip_p90_bps=8.0,
        regular_round_trip_p99_bps=12.0,
        outside_round_trip_p90_bps=16.0,
        outside_round_trip_p99_bps=24.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
    )


def test_depth_friction_rejects_stress_latency_below_nominal() -> None:
    with pytest.raises(ValueError, match="stress latency"):
        replace(_friction(), stress_latency_bps_per_side=0.5)


def _trade(
    direction: str,
    entry_time: str,
    net_pnl_usd: float,
) -> SharedPortfolioTrade:
    return SharedPortfolioTrade(
        signal_name="mu_test",
        direction=direction,  # type: ignore[arg-type]
        signal_time_utc=entry_time,
        entry_time_utc=entry_time,
        exit_time_utc=entry_time,
        signal_position=0,
        entry_position=1,
        exit_position=2,
        entry_price=100.0,
        exit_price=101.0,
        target_price=None,
        stop_price=None,
        liquidation_price=80.0,
        quantity=1.0,
        margin_usd=15.0,
        notional_usd=75.0,
        leverage=5.0,
        gross_pnl_usd=net_pnl_usd + 0.1,
        fees_usd=0.1,
        funding_cashflow_usd=0.0,
        net_pnl_usd=net_pnl_usd,
        equity_before_usd=500.0,
        equity_after_usd=500.0 + net_pnl_usd,
        exit_reason="signal",
        same_bar_ambiguous=False,
    )


def test_windows_are_strict_chronological_sixty_twenty_twenty() -> None:
    windows = chronological_windows(_bars().index)

    assert windows.development_start_utc == _bars().index[0]
    assert windows.development_end_utc < windows.validation_end_utc
    assert windows.validation_end_utc < windows.holdout_end_utc
    assert len(windows.development_folds) == 3


def test_session_quotes_use_wider_outside_hours_surface() -> None:
    bars = _bars(2).copy()
    bars.index = pd.DatetimeIndex(["2026-01-05T15:00:00Z", "2026-01-05T23:00:00Z"])

    quoted = quote_mu_bars(bars, _friction(), stress=False)

    regular_width = quoted.iloc[0]["open_ask"] / quoted.iloc[0]["open_bid"] - 1.0
    outside_width = quoted.iloc[1]["open_ask"] / quoted.iloc[1]["open_bid"] - 1.0
    assert quoted["friction_session"].tolist() == [
        "us_regular_hours",
        "outside_us_regular_hours",
    ]
    assert outside_width > regular_width


def test_trade_summary_slices_sides_sessions_and_removes_largest_winner() -> None:
    trades = (
        _trade("long", "2026-01-05T15:00:00+00:00", 5.0),
        _trade("long", "2026-01-05T23:00:00+00:00", -2.0),
        _trade("short", "2026-01-06T16:00:00+00:00", 1.0),
    )

    summary = summarize_trades(trades)

    assert summary["all"].net_pnl_usd == pytest.approx(4.0)
    assert summary["all"].net_without_largest_winner_usd == pytest.approx(-1.0)
    assert summary["long"].trades == 2
    assert summary["short"].trades == 1
    assert summary["outside_us_regular_hours"].trades == 1


def test_candidate_is_exact_mu_report_only_and_evaluates_both_sides() -> None:
    configs = (
        SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),
        SwingHaSignalConfig(9, 26, 5, "onset", "alignment_loss"),
    )

    result = evaluate_mu_swing_candidate(_bars(), _friction(), configs=configs)

    assert result.symbol == MU_SYMBOL == "xyz:MU"
    assert result.proposed_provider_id == MU_PROVIDER_ID
    assert "recent_candle_probe" in result.proposed_provider_id
    assert result.execution_authority == "none"
    assert result.automatic_promotion is False
    assert {item.name for item in result.partitions} == {
        "development",
        "validation",
        "holdout",
    }
    assert set(summarize_trades(result.partitions[-1].nominal.trades)) >= {
        "long",
        "short",
    }


def test_invalid_mu_market_identity_cannot_be_substituted() -> None:
    with pytest.raises(ValueError, match="exact xyz:MU"):
        evaluate_mu_swing_candidate(
            _bars(),
            replace(_friction(), symbol="km:MU"),
            configs=(SwingHaSignalConfig(),),
        )


def test_initial_probe_selection_prefers_fold_profit_over_side_breadth() -> None:
    profitable = SwingHaSignalConfig(7, 21, 3, "state", "ha_flip")
    losing_both = SwingHaSignalConfig(9, 26, 5, "onset", "alignment_loss")
    profitable_report = _report(6.0, (_trade("long", "2026-01-05T15:00Z", 6.0),))
    losing_report = _report(
        -2.0,
        (
            _trade("long", "2026-01-05T15:00Z", -1.0),
            _trade("short", "2026-01-05T16:00Z", -1.0),
        ),
    )
    positive_fold = _report(1.0, ())
    negative_fold = _report(-1.0, ())
    trials = (
        MuTrial(profitable, profitable_report, (positive_fold,) * 3),
        MuTrial(losing_both, losing_report, (negative_fold,) * 3),
    )

    assert select_mu_trial(trials).config == profitable


def _report(
    net: float, trades: tuple[SharedPortfolioTrade, ...]
) -> SharedPortfolioReport:
    gains = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    return SharedPortfolioReport(
        500.0,
        500.0 + net,
        net,
        net / 5.0,
        min(net / 5.0, 0.0),
        len(trades),
        sum(trade.net_pnl_usd > 0.0 for trade in trades),
        sum(trade.net_pnl_usd < 0.0 for trade in trades),
        gains,
        losses,
        gains / losses if losses else None,
        0,
        0.0,
        0.0,
        0,
        1,
        0,
        0,
        False,
        {},
        (),
        trades,
    )
