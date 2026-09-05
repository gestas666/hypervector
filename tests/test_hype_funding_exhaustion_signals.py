"""Causal contracts for the HYPE funding-exhaustion signal."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.funding_price_exhaustion_signals import (
    FundingPriceExhaustionConfig,
    build_funding_price_exhaustion_signals,
)
from hypervector.research.hype_funding_exhaustion_signals import (
    HypeFundingExhaustionConfig,
    build_hype_funding_exhaustion_signals,
)


def _bars(*, side: str = "long") -> pd.DataFrame:
    times = pd.date_range("2026-01-02", periods=40, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": [100.0] * len(times),
            "high": [100.1] * len(times),
            "low": [99.9] * len(times),
            "close": [100.0] * len(times),
            "volume": [10.0] * len(times),
            "contains_gap_fill": [False] * len(times),
        }
    )
    prior, current, following = 29, 30, 31
    if side == "long":
        frame.loc[prior, ["open", "high", "low", "close"]] = [100, 100, 97.8, 98]
        frame.loc[current, ["open", "high", "low", "close"]] = [98, 99.2, 97.9, 99]
        frame.loc[following, ["open", "high", "low", "close"]] = [99, 99.4, 98.9, 99.2]
    else:
        frame.loc[prior, ["open", "high", "low", "close"]] = [100, 102.2, 100, 102]
        frame.loc[current, ["open", "high", "low", "close"]] = [102, 102.1, 100.8, 101]
        frame.loc[following, ["open", "high", "low", "close"]] = [
            101,
            101.1,
            100.6,
            100.8,
        ]
    return frame


def _funding(bars: pd.DataFrame, *, extreme: float) -> pd.DataFrame:
    prior_times = pd.date_range("2026-01-01T18:00Z", periods=4, freq="1h")
    event_time = bars.iloc[30]["timestamp"] + pd.Timedelta(minutes=1)
    times = [*prior_times, event_time]
    rates = [0.0001, 0.0002, 0.00015, 0.0001, extreme]
    return pd.DataFrame(
        {
            "timestamp": times,
            "event_ts_ms": [int(value.timestamp() * 1_000) for value in times],
            "funding_rate": rates,
            "source": ["hl_funding_history"] * len(times),
        }
    )


def _config() -> HypeFundingExhaustionConfig:
    return HypeFundingExhaustionConfig(
        funding_lookback_events=4,
        minimum_funding_history_events=4,
        lower_funding_quantile=0.25,
        upper_funding_quantile=0.75,
        minimum_previous_extension_bps=60.0,
        clean_history_bars=21,
    )


def test_funding_threshold_excludes_current_extreme_event() -> None:
    bars = _bars()

    report = build_hype_funding_exhaustion_signals(
        bars, _funding(bars, extreme=-0.001), _config()
    )

    row = report.diagnostics.iloc[30]
    assert row["funding_rate_bps"] == pytest.approx(-10.0)
    assert row["lower_funding_threshold_bps"] == pytest.approx(1.0)
    assert bool(report.long_signals.iloc[30])


def test_future_received_funding_event_cannot_enable_signal() -> None:
    bars = _bars()
    funding = _funding(bars, extreme=-0.001)
    after_close = bars.iloc[30]["timestamp"] + pd.Timedelta(minutes=6)
    funding.loc[4, "event_ts_ms"] = int(after_close.timestamp() * 1_000)

    report = build_hype_funding_exhaustion_signals(bars, funding, _config())

    assert report.diagnostics.iloc[30]["funding_rate_bps"] == pytest.approx(1.0)
    assert not bool(report.long_signals.iloc[30])


@pytest.mark.parametrize(
    ("side", "extreme"),
    [("long", -0.001), ("short", 0.001)],
)
def test_signal_requires_extension_then_reversal(side: str, extreme: float) -> None:
    bars = _bars(side=side)

    report = build_hype_funding_exhaustion_signals(
        bars, _funding(bars, extreme=extreme), _config()
    )

    selected = report.long_signals if side == "long" else report.short_signals
    opposite = report.short_signals if side == "long" else report.long_signals
    assert list(selected[selected].index) == [30]
    assert not bool(opposite.any())


def test_gap_inside_clean_history_blocks_signal() -> None:
    bars = _bars()
    bars.loc[20, "contains_gap_fill"] = True

    report = build_hype_funding_exhaustion_signals(
        bars, _funding(bars, extreme=-0.001), _config()
    )

    assert not bool(report.long_signals.iloc[30])


def test_funding_availability_must_be_ordered_and_unique() -> None:
    bars = _bars()
    funding = _funding(bars, extreme=-0.001)
    funding.loc[4, "event_ts_ms"] = funding.loc[3, "event_ts_ms"]

    with pytest.raises(ValueError, match="availability timestamps"):
        build_hype_funding_exhaustion_signals(bars, funding, _config())


def test_hype_wrapper_matches_asset_generic_signal_contract() -> None:
    bars = _bars(side="short")
    funding = _funding(bars, extreme=0.001)
    generic_config = FundingPriceExhaustionConfig(**vars(_config()))

    generic = build_funding_price_exhaustion_signals(bars, funding, generic_config)
    hype = build_hype_funding_exhaustion_signals(bars, funding, _config())

    pd.testing.assert_series_equal(generic.long_signals, hype.long_signals)
    pd.testing.assert_series_equal(generic.short_signals, hype.short_signals)
    pd.testing.assert_series_equal(generic.atr_bps, hype.atr_bps)
    pd.testing.assert_frame_equal(generic.diagnostics, hype.diagnostics)
