"""Tests for the frozen BTC DVOL-VRP economic replay."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_dvol_vrp_replay import (
    evaluate_btc_dvol_vrp_long,
)


_SIGNAL = pd.Timestamp("2026-08-03T12:00:00Z")


def test_replay_enters_next_minute_with_frozen_sizing_and_barriers() -> None:
    """A completed-hour pulse fills once at the strictly next minute open."""
    bars = _market(90)
    bars.loc[_SIGNAL + pd.Timedelta(minutes=1), "high"] = 103.0

    result = evaluate_btc_dvol_vrp_long(bars, _features(), "nominal")

    assert result.primary_signal_count == 1
    assert result.primary_signal_times_utc == (_SIGNAL.isoformat(),)
    trade = result.primary_report.trades[0]
    assert trade.signal_time_utc == _SIGNAL.isoformat()
    assert trade.entry_time_utc == (_SIGNAL + pd.Timedelta(minutes=1)).isoformat()
    assert trade.margin_usd == pytest.approx(500.0)
    assert trade.notional_usd == pytest.approx(5_000.0)
    assert trade.leverage == pytest.approx(10.0)
    assert trade.target_price == pytest.approx(trade.entry_price * 1.025)
    assert trade.stop_price == pytest.approx(trade.entry_price * 0.99)
    assert trade.exit_reason == "target"
    assert result.execution_authority == "none"


def test_replay_executes_strategic_exit_at_next_minute_open() -> None:
    """A completed-hour EMA exit is filled at the next observed minute."""
    features = _features()
    exit_time = _SIGNAL + pd.Timedelta(hours=2)
    selected = features["decision_time"].eq(exit_time)
    features.loc[selected, ["btc_close", "ema24"]] = [99.0, 100.0]

    result = evaluate_btc_dvol_vrp_long(_market(90), features, "nominal")

    trade = result.primary_report.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_time_utc == (exit_time + pd.Timedelta(minutes=1)).isoformat()


@pytest.mark.parametrize(
    ("bar_change", "reason"),
    [("stop", "stop"), ("target", "target")],
)
def test_replay_honors_fixed_protective_barriers(
    bar_change: str,
    reason: str,
) -> None:
    """The fixed 100/250-bps barriers must be active from entry."""
    bars = _market(90)
    entry = _SIGNAL + pd.Timedelta(minutes=1)
    if bar_change == "stop":
        bars.loc[entry, "low"] = 98.0
    else:
        bars.loc[entry, "high"] = 103.0

    result = evaluate_btc_dvol_vrp_long(bars, _features(), "nominal")

    assert result.primary_report.trades[0].exit_reason == reason


def test_replay_uses_72_hour_fallback_and_exact_funding() -> None:
    """A stuck trade must time out and consume supplied hourly funding rows."""
    bars = _market(150)
    funding_time = _SIGNAL + pd.Timedelta(hours=1)
    bars.loc[funding_time, "funding_rate"] = 0.001

    result = evaluate_btc_dvol_vrp_long(bars, _features(), "nominal")

    trade = result.primary_report.trades[0]
    assert trade.exit_reason == "max_hold"
    assert trade.funding_cashflow_usd < 0.0
    assert trade.exit_time_utc == (_SIGNAL + pd.Timedelta(minutes=4_321)).isoformat()


@pytest.mark.parametrize(
    ("scenario", "delay", "slippage"),
    [("nominal", 0, 2.0), ("stress", 5, 5.0), ("delayed", 60, 10.0)],
)
def test_replay_applies_only_frozen_delay_and_slippage_scenarios(
    scenario: str,
    delay: int,
    slippage: float,
) -> None:
    """Every arm must use one preregistered execution sensitivity."""
    result = evaluate_btc_dvol_vrp_long(_market(150), _features(), scenario)

    assert result.extra_delay_minutes == delay
    assert result.slippage_bps_per_taker_side == slippage
    assert result.primary_signal_times_utc == (
        (_SIGNAL + pd.Timedelta(minutes=delay)).isoformat(),
    )
    assert (
        result.primary_report.trades[0].entry_time_utc
        == (_SIGNAL + pd.Timedelta(minutes=delay + 1)).isoformat()
    )


def test_delay_crossing_explicit_gap_cancels_entry() -> None:
    """A delayed pulse cannot cross a declared missing-market boundary."""
    bars = _market(90)
    bars.loc[_SIGNAL + pd.Timedelta(minutes=2), "gap_before_bars"] = 1

    result = evaluate_btc_dvol_vrp_long(bars, _features(), "stress")

    assert result.primary_signal_count == 0
    assert result.primary_report.completed_trades == 0
    assert result.primary_delay_gap_cancellations == 1


def test_replay_masks_entries_half_open_after_delay() -> None:
    """Partition entry windows apply to delayed event time, not raw onset."""
    start = _SIGNAL + pd.Timedelta(minutes=30)
    end = _SIGNAL + pd.Timedelta(hours=2)

    nominal = evaluate_btc_dvol_vrp_long(
        _market(150), _features(), "nominal", entry_start_utc=start, entry_end_utc=end
    )
    delayed = evaluate_btc_dvol_vrp_long(
        _market(150), _features(), "delayed", entry_start_utc=start, entry_end_utc=end
    )

    assert nominal.primary_signal_count == 0
    assert delayed.primary_signal_count == 1


def test_replay_requires_exact_funding_and_known_scenario() -> None:
    """Missing funding or an unregistered scenario is a technical failure."""
    with pytest.raises(ValueError, match="requires exact funding_rate"):
        evaluate_btc_dvol_vrp_long(
            _market(90).drop(columns="funding_rate"), _features(), "nominal"
        )
    with pytest.raises(ValueError, match="unknown scenario"):
        evaluate_btc_dvol_vrp_long(_market(90), _features(), "optimistic")


def test_replay_includes_unchanged_v58_sweep_and_all_controls() -> None:
    """The economic result must expose every preregistered active arm."""
    result = evaluate_btc_dvol_vrp_long(_market(90), _features(), "nominal")

    assert result.price_only_report is not None
    assert result.high_vrp_only_report is not None
    assert result.low_vrp_placebo_report is not None
    assert result.v58_sweep_report is not None


def _market(hours: int) -> pd.DataFrame:
    index = pd.date_range("2026-08-01", periods=hours * 60, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.05,
            "low": 99.95,
            "close": 100.0,
            "volume": 1.0,
            "funding_rate": 0.0,
            "gap_before_bars": 0,
        },
        index=index,
    )


def _features() -> pd.DataFrame:
    source = pd.date_range(
        _SIGNAL - pd.Timedelta(hours=3),
        periods=8,
        freq="h",
    ) - pd.Timedelta(hours=1)
    decision = source + pd.Timedelta(hours=1)
    high = decision == _SIGNAL
    return pd.DataFrame(
        {
            "source_timestamp": source,
            "decision_time": decision,
            "btc_close": 101.0,
            "ema24": 100.0,
            "vrp": 0.3,
            "vrp_median": 0.2,
            "high_vrp": high,
            "low_vrp": False,
            "bullish_structure": high,
        }
    )
