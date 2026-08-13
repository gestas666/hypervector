"""Development-only HIP-3 signal-source sensitivity tests."""

from __future__ import annotations

import pandas as pd
from pytest import raises

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_signal_source_sensitivity import (
    build_hip3_signal_source_sensitivity,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution


def test_source_change_reports_signal_and_economic_difference() -> None:
    bars = _bars()
    venue = bars.loc[:, ["signal_open", "signal_high", "signal_low", "signal_close"]]
    venue = venue.rename(columns=lambda name: name.removeprefix("signal_"))
    venue.loc[venue.index[-2], ["open", "high", "low", "close"]] = 100.0

    report = build_hip3_signal_source_sensitivity(
        bars=bars,
        venue_ohlc=venue,
        config=_config(),
        execution=_execution(),
        start_utc=bars.index[0],
        end_utc=bars.index[-1] + pd.Timedelta(minutes=15),
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["out_of_sample_evaluated"] is False
    assert report["coverage"]["bars"] == len(bars)
    assert report["signal_comparison"]["entry_disagreement_bars"] == 2
    assert report["signal_comparison"]["disagreement_rows"] == [
        {
            "timestamp_utc": bars.index[-2].isoformat(),
            "fields": ["long_entry", "long_exit"],
        },
        {
            "timestamp_utc": bars.index[-1].isoformat(),
            "fields": ["long_entry"],
        },
    ]
    assert report["public_trade_source"]["nominal"]["completed_trades"] == 1
    assert report["venue_candle_source"]["nominal"]["completed_trades"] == 0


def test_rows_at_or_after_end_cannot_change_report() -> None:
    bars = _bars()
    venue = _venue(bars)
    end = bars.index[-1]
    control = build_hip3_signal_source_sensitivity(
        bars=bars,
        venue_ohlc=venue,
        config=_config(),
        execution=_execution(),
        start_utc=bars.index[0],
        end_utc=end,
    )
    venue.loc[bars.index[-1], "close"] = 999.0

    observed = build_hip3_signal_source_sensitivity(
        bars=bars,
        venue_ohlc=venue,
        config=_config(),
        execution=_execution(),
        start_utc=bars.index[0],
        end_utc=end,
    )

    assert observed == control


def test_missing_venue_bar_fails_closed() -> None:
    bars = _bars()

    with raises(ValueError, match="exactly match archive bars"):
        build_hip3_signal_source_sensitivity(
            bars=bars,
            venue_ohlc=_venue(bars).iloc[1:],
            config=_config(),
            execution=_execution(),
            start_utc=bars.index[0],
            end_utc=bars.index[-1],
        )


def _config() -> Hip3BreakoutPressureConfig:
    return Hip3BreakoutPressureConfig(4, 2, 3, 0.5, 40.0)


def _execution() -> MuArchiveExecution:
    return MuArchiveExecution(
        0.0000864,
        75.0,
        10.0,
        1.0,
        2.0,
        2.5,
        maximum_hold_bars=96,
        risk_high_column="risk_high",
        risk_low_column="risk_low",
        entry_risk_high_column="risk_entry_high",
        entry_risk_low_column="risk_entry_low",
        symbol="xyz:SKHX",
    )


def _venue(bars: pd.DataFrame) -> pd.DataFrame:
    columns = ["signal_open", "signal_high", "signal_low", "signal_close"]
    return bars.loc[:, columns].rename(
        columns=lambda name: name.removeprefix("signal_")
    )


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-06-21", periods=70, freq="15min", tz="UTC")
    close = [100.0] * 68 + [105.0, 105.0]
    frame = pd.DataFrame(index=index)
    for name in ("open", "close", "signal_open", "signal_close"):
        frame[name] = close
    for name in ("high", "signal_high"):
        frame[name] = [value + 0.2 for value in close]
    for name in ("low", "signal_low"):
        frame[name] = [value - 0.2 for value in close]
    frame["signal_gap_before_bars"] = 0
    frame["signal_ohlc_source"] = "0xarchive_public_trade_ohlc_v1"
    frame["signal_ohlc_synthetic_no_trade"] = False
    frame["decision_imbalance_10"] = 0.8
    frame["entry_bid"] = frame["close"] - 0.01
    frame["entry_ask"] = frame["close"] + 0.01
    frame["decision_bid"] = frame["entry_bid"]
    frame["decision_ask"] = frame["entry_ask"]
    frame["first_boundary_delay_ms"] = 1_000
    frame["end_boundary_age_ms"] = 1_000
    frame["maximum_snapshot_interval_ms"] = 1_000
    frame["source_snapshot_count"] = 2
    frame["gap_before_bars"] = 0
    frame["funding_rate"] = 0.0
    frame["risk_high"] = frame["high"]
    frame["risk_low"] = frame["low"]
    frame["risk_entry_high"] = frame["high"]
    frame["risk_entry_low"] = frame["low"]
    return frame
