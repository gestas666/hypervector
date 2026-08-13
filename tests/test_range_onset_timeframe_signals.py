"""Tests for fixed lower-timeframe range-onset challengers."""

from __future__ import annotations

import pandas as pd

from hypervector.research import range_onset_signals


def _cross_bars(timeframe_minutes: int) -> pd.DataFrame:
    source_closes = [100.0] * 30 + [110.0]
    closes = [value for value in source_closes for _ in range(timeframe_minutes)]
    index = pd.date_range("2026-01-01", periods=len(closes), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        },
        index=index,
    )


def test_five_minute_challenger_emits_only_at_completed_cross_bar(
    monkeypatch: object,
) -> None:
    bars = _cross_bars(5)
    regimes = pd.DataFrame({"state_5m": "RANGE"}, index=bars.index)
    monkeypatch.setattr(
        range_onset_signals, "classify_multitimeframe", lambda _: regimes
    )

    signals = range_onset_signals.build_range_onset_signals(
        bars,
        timeframe="5min",
    )

    assert not signals["long_entry"].iloc[:-1].any()
    assert signals["long_entry"].iloc[-1]
    assert signals["raw_long_cross"].iloc[-1]
    assert signals["structural_direction"].iloc[-1] == "long"
    assert signals["source_timeframe"].iloc[-1] == "5min"


def test_challenger_reuses_precomputed_regimes(monkeypatch: object) -> None:
    bars = _cross_bars(15)
    regimes = pd.DataFrame({"state_5m": "BREAKOUT"}, index=bars.index)
    monkeypatch.setattr(
        range_onset_signals,
        "classify_multitimeframe",
        lambda _: (_ for _ in ()).throw(AssertionError("classifier reran")),
    )

    signals = range_onset_signals.build_range_onset_signals(
        bars,
        timeframe="15min",
        regimes=regimes,
    )

    assert signals["long_entry"].iloc[-1]
    assert signals["source_timeframe"].iloc[-1] == "15min"
