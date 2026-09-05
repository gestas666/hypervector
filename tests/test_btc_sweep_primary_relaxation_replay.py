"""Economic replay contract for the V58 BTC sweep-relaxation experiment."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_sweep_primary_relaxation_replay import (
    evaluate_btc_sweep_primary_relaxation,
)


def test_replay_enters_next_minute_with_exact_v58_sizing_and_target() -> None:
    """A candidate onset fills causally and uses the frozen 60/60 contract."""
    bars = _market()
    entry_time = pd.Timestamp("2025-01-03T13:00:00Z")
    bars.loc[entry_time, "high"] = float(bars.loc[entry_time, "open"]) * 1.02
    result = evaluate_btc_sweep_primary_relaxation(bars, 2.0)

    assert result.control.completed_trades == 0
    assert result.candidate.completed_trades == 1
    assert result.control_signal_count == 0
    assert result.candidate_signal_count == 1
    assert result.control_signal_times_utc == ()
    assert result.candidate_signal_times_utc == ("2025-01-03T12:59:00+00:00",)
    trade = result.candidate.trades[0]
    assert trade.signal_time_utc == "2025-01-03T12:59:00+00:00"
    assert trade.entry_time_utc == entry_time.isoformat()
    assert trade.margin_usd == pytest.approx(500.0)
    assert trade.notional_usd == pytest.approx(5_000.0)
    assert trade.leverage == pytest.approx(10.0)
    assert trade.target_price == pytest.approx(trade.entry_price * 1.006)
    assert trade.stop_price == pytest.approx(trade.entry_price * 0.994)
    assert trade.exit_reason == "target"
    expected_fees = trade.quantity * (
        trade.entry_price * 0.00045 + trade.target_price * 0.00015
    )
    assert trade.fees_usd == pytest.approx(expected_fees)


def test_stress_slippage_is_adverse_without_changing_signal_count() -> None:
    """Stress modifies execution economics but cannot alter entry decisions."""
    bars = _market(hours=90)
    entry_time = pd.Timestamp("2025-01-03T13:00:00Z")
    anchor = float(bars.loc[entry_time, "open"])
    selected = bars.index >= entry_time
    bars.loc[selected, "open"] = anchor
    bars.loc[selected, "close"] = anchor
    bars.loc[selected, "high"] = anchor * 1.001
    bars.loc[selected, "low"] = anchor * 0.999
    nominal = evaluate_btc_sweep_primary_relaxation(bars, 2.0)
    stress = evaluate_btc_sweep_primary_relaxation(bars, 5.0)
    assert nominal.candidate_signal_count == stress.candidate_signal_count == 1
    assert nominal.candidate.trades[0].exit_reason == "max_hold"
    assert stress.candidate.trades[0].exit_reason == "max_hold"
    assert stress.candidate.net_pnl_usd < nominal.candidate.net_pnl_usd


def test_same_bar_target_and_stop_use_adverse_precedence_and_disclose_ambiguity() -> (
    None
):
    """A one-minute double touch must resolve as a stop and remain visible."""
    bars = _market()
    entry_time = pd.Timestamp("2025-01-03T13:00:00Z")
    opening = float(bars.loc[entry_time, "open"])
    bars.loc[entry_time, "high"] = opening * 1.02
    bars.loc[entry_time, "low"] = opening * 0.98
    result = evaluate_btc_sweep_primary_relaxation(bars, 2.0)
    trade = result.candidate.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.same_bar_ambiguous is True
    assert trade.exit_price < trade.stop_price


def test_unresolved_position_uses_twenty_four_hour_fallback() -> None:
    """Time is a fallback after stop/target, not the sole exit mechanism."""
    bars = _market(hours=90)
    flat_start = pd.Timestamp("2025-01-03T13:00:00Z")
    anchor = float(bars.loc[flat_start, "open"])
    selected = bars.index >= flat_start
    bars.loc[selected, "open"] = anchor
    bars.loc[selected, "close"] = anchor
    bars.loc[selected, "high"] = anchor * 1.001
    bars.loc[selected, "low"] = anchor * 0.999
    result = evaluate_btc_sweep_primary_relaxation(bars, 2.0)
    trade = result.candidate.trades[0]
    assert trade.exit_reason == "max_hold"
    assert pd.Timestamp(trade.exit_time_utc) - pd.Timestamp(trade.entry_time_utc) == (
        pd.Timedelta(hours=24)
    )


def test_entry_window_uses_warmup_without_admitting_pre_partition_signal() -> None:
    """Partition warmup may build indicators but cannot enter before its boundary."""
    bars = _market()
    start = pd.Timestamp("2025-01-03T13:00:00Z")
    result = evaluate_btc_sweep_primary_relaxation(
        bars,
        2.0,
        entry_start_utc=start,
        entry_end_utc=pd.Timestamp("2025-01-04T00:00:00Z"),
    )
    assert result.candidate_signal_count == 0
    assert result.candidate.completed_trades == 0


def _market(hours: int = 66) -> pd.DataFrame:
    hourly_index = pd.date_range("2025-01-01", periods=hours, freq="1h", tz="UTC")
    hourly = pd.DataFrame(index=hourly_index)
    hourly["close"] = [120.0 + 0.05 * position for position in range(hours)]
    hourly["open"] = hourly["close"] - 0.025
    hourly["high"] = hourly["close"] + 0.1
    hourly["low"] = hourly["open"] - 0.1
    hourly["volume"] = 60.0
    hourly.loc[hourly_index[60:62], "volume"] = 120.0
    bars = _expand_hours(hourly)
    bars["funding_rate"] = 0.0
    return bars


def _expand_hours(hourly: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    timestamps: list[pd.Timestamp] = []
    for timestamp, row in hourly.iterrows():
        for minute in range(60):
            timestamps.append(timestamp + pd.Timedelta(minutes=minute))
            records.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) / 60.0,
                }
            )
    return pd.DataFrame(records, index=pd.DatetimeIndex(timestamps))
