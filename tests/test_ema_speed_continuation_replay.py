"""Lifecycle and shared-account tests for the EMA-speed challenger."""

from __future__ import annotations

import pandas as pd

from hypervector.research.ema_speed_continuation_replay import (
    combine_ema_speed_reports,
    evaluate_ema_speed_symbol,
)


def test_replay_uses_exact_next_bar_quotes_and_stress_is_adverse() -> None:
    """The economic replay fills from BBO and charges incremental stress friction."""
    bars = _market("BTC", incomplete=False)
    nominal = evaluate_ema_speed_symbol(bars, "BTC", slippage_bps_per_side=2.0)
    stress = evaluate_ema_speed_symbol(bars, "BTC", slippage_bps_per_side=5.0)
    assert nominal.report.completed_trades == 1
    trade = nominal.report.trades[0]
    raw_ask = float(
        bars.loc[pd.Timestamp(trade.entry_time_utc).floor("15min"), "entry_ask"]
    )
    assert trade.entry_price == raw_ask * (1.0 + 2.0 / 10_000.0)
    assert stress.report.net_pnl_usd < nominal.report.net_pnl_usd
    assert nominal.technical_path["mark_path_status"] == "unresolved_not_available"


def test_incomplete_l2_overlap_is_reported_not_hidden() -> None:
    """Economic output cannot convert incomplete L2 into technical acceptance."""
    result = evaluate_ema_speed_symbol(
        _market("BTC", incomplete=True),
        "BTC",
        slippage_bps_per_side=2.0,
    )
    assert result.report.completed_trades == 1
    assert result.technical_path["l2_unresolved_lifecycles"] == 1
    assert result.technical_path["qualification_ready"] is False


def test_two_symbols_replay_on_one_shared_account() -> None:
    """Concurrent BTC and SOL lifecycles reserve two ten-percent margin slots."""
    btc = evaluate_ema_speed_symbol(_market("BTC", False), "BTC", 2.0)
    sol = evaluate_ema_speed_symbol(_market("SOL", False), "SOL", 2.0)
    pooled = combine_ema_speed_reports((btc, sol), initial_equity_usd=5_000.0)
    assert pooled.completed_trades == 2
    assert pooled.maximum_concurrent_positions == 2
    assert pooled.peak_reserved_margin_usd <= 1_000.0


def test_same_bar_stop_has_strict_shared_ledger_ordering() -> None:
    """An entry-bar stop is ordered one millisecond after its exact entry quote."""
    bars = _market("BTC", False)
    bars.loc[bars.index[67], "risk_low"] = 1.0
    btc = evaluate_ema_speed_symbol(bars, "BTC", 2.0)
    sol = evaluate_ema_speed_symbol(_market("SOL", False), "SOL", 2.0)
    assert btc.report.trades[0].entry_time_utc == btc.report.trades[0].exit_time_utc
    pooled = combine_ema_speed_reports((btc, sol), initial_equity_usd=5_000.0)
    stopped = next(trade for trade in pooled.trades if trade.symbol == "BTC")
    assert stopped.exit_time_ms == stopped.entry_time_ms + 1


def _market(symbol: str, incomplete: bool) -> pd.DataFrame:
    del symbol
    index = pd.date_range("2025-01-01", periods=70, freq="15min", tz="UTC")
    closes = pd.Series([100.0 + 0.2 * value for value in range(70)], index=index)
    closes.iloc[65] = closes.iloc[64] - 1.2
    closes.iloc[66] = closes.iloc[64] + 0.8
    frame = pd.DataFrame(index=index)
    frame["close"] = closes
    frame["open"] = closes.shift(1).fillna(closes.iloc[0])
    frame["high"] = frame[["open", "close"]].max(axis=1) + 0.1
    frame["low"] = frame[["open", "close"]].min(axis=1) - 0.1
    frame["source_complete"] = True
    frame["entry_bid"] = frame["open"] - 0.05
    frame["entry_ask"] = frame["open"] + 0.05
    frame["close_bid"] = frame["close"] - 0.05
    frame["close_ask"] = frame["close"] + 0.05
    frame["risk_low"] = frame[["entry_bid", "close_bid"]].min(axis=1)
    frame["risk_high"] = frame[["entry_ask", "close_ask"]].max(axis=1)
    frame["first_boundary_delay_ms"] = 100.0
    frame["end_boundary_age_ms"] = 100.0
    frame["l2_path_complete"] = True
    frame["funding_rate"] = 0.0
    if incomplete:
        frame.loc[index[68], "l2_path_complete"] = False
    return frame
