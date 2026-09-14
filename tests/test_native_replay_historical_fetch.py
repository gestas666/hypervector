"""Continuous native acquisition must preserve source windows, observed cutoffs and gaps."""

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_historical_fetch import (
    HistoricalCandleSource,
    HistoricalNativeFetch,
)

MINUTE = 60_000


def source() -> HistoricalCandleSource:
    """Include an unfinished high-priced bar and a missing minute in an explicit source window."""
    opens = [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11]
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([n * MINUTE for n in opens], unit="ms", utc=True),
            "open": [100.0 + n for n in opens],
            "high": [101.0 + n for n in opens],
            "low": [99.0 + n for n in opens],
            "close": [100.0 + n for n in opens],
            "volume": [1.0] * len(opens),
        }
    )
    return HistoricalCandleSource("declared-gap-fixture", 0, 12 * MINUTE, frame)


def fetcher(clock: ReplayClock, *, span: int = 6 * MINUTE) -> HistoricalNativeFetch:
    """Declare one observed cold span and fixed request latency, without a fabricated row cap."""
    return HistoricalNativeFetch(
        clock=clock,
        sources={"BTC": source()},
        cold_span_ms={"BTC": span},
        elapsed_ms=lambda symbol, cold: 1200,
    )


def test_cold_span_and_warm_overlap_keep_completed_causal_bars_and_original_cutoff() -> None:
    """A fetch's elapsed response cannot expose the forming bar's future close."""
    clock = ReplayClock(10 * MINUTE + 59_500)
    fetch = fetcher(clock)
    cold = fetch("BTC", "1m", 1, end_ms=clock.now_ms)
    assert cold["close"].tolist() == [105, 106, 107, 108, 109]
    assert clock.now_ms == 11 * MINUTE + 700
    warm = fetch("BTC", "1m", 2 / 1440, end_ms=11 * MINUTE)
    assert warm["close"].tolist() == [109, 110]
    assert fetch.completed_requests == 2


def test_source_and_returned_frames_are_detached_without_filling_missing_minutes() -> None:
    """Source/caller mutations cannot rewrite retained history or manufacture quiet bars."""
    clock = ReplayClock(10 * MINUTE)
    original = source()
    fetch = HistoricalNativeFetch(
        clock=clock,
        sources={"BTC": original},
        cold_span_ms={"BTC": 10 * MINUTE},
        elapsed_ms=lambda s, c: 0,
    )
    original.frame.loc[:, "close"] = 999
    first = fetch("BTC", "1m", 10 / 1440, end_ms=clock.now_ms)
    assert first["close"].tolist() == [100, 101, 102, 103, 105, 106, 107, 108, 109]
    first.loc[:, "close"] = 777
    assert fetch("BTC", "1m", 10 / 1440, end_ms=clock.now_ms)["close"].max() == 109


@pytest.mark.parametrize(
    "failure", ["future", "outside_source", "timeframe", "lookback", "fractional_time", "cutoff"]
)
def test_unsupported_requests_fail_before_clock_or_cold_state_changes(failure: str) -> None:
    """A technical source/request problem is not represented as an empty successful fetch."""
    clock = ReplayClock(10 * MINUTE)
    fetch = fetcher(clock)
    end = (
        clock.now_ms + 1
        if failure == "future"
        else 13 * MINUTE
        if failure == "outside_source"
        else clock.now_ms
    )
    if failure == "outside_source":
        clock.advance_to(end)
    before = clock.now_ms
    with pytest.raises(ValueError):
        fetch(
            "BTC",
            "5m" if failure == "timeframe" else "1m",
            True if failure == "lookback" else 1,
            end_ms=1.1 if failure == "fractional_time" else None if failure == "cutoff" else end,
        )
    assert clock.now_ms == before and fetch.completed_requests == 0


@pytest.mark.parametrize("change", ["duplicate", "reversed", "unaligned", "outside"])
def test_bad_source_clocks_fail_at_construction(change: str) -> None:
    """Malformed source ordering cannot be silently sorted or deduplicated into validity."""
    item = source()
    frame = item.frame.copy()
    if change == "duplicate":
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    elif change == "reversed":
        frame = frame.iloc[::-1]
    elif change == "unaligned":
        frame.loc[0, "timestamp"] += pd.Timedelta(milliseconds=1)
    else:
        item = replace(item, start_ms=MINUTE)
    with pytest.raises(ValueError):
        HistoricalNativeFetch(
            clock=ReplayClock(10 * MINUTE),
            sources={"BTC": replace(item, frame=frame)},
            cold_span_ms={"BTC": MINUTE},
            elapsed_ms=lambda s, c: 0,
        )


@pytest.mark.parametrize("change", ["universe", "zero_span", "schema", "missing_time", "window"])
def test_source_contract_failures_are_rejected_before_acquisition(change: str) -> None:
    """A source needs explicit coverage, schema, timestamps and a matching cold policy."""
    item = source()
    spans = {"BTC": MINUTE}
    if change == "universe":
        spans = {"ETH": MINUTE}
    elif change == "zero_span":
        spans = {"BTC": 0}
    elif change == "schema":
        item = replace(item, frame=item.frame.drop(columns="close"))
    elif change == "missing_time":
        item.frame.loc[0, "timestamp"] = pd.NaT
    with pytest.raises(ValueError):
        if change == "window":
            item = replace(item, end_ms=0)
        HistoricalNativeFetch(
            clock=ReplayClock(10 * MINUTE),
            sources={"BTC": item},
            cold_span_ms=spans,
            elapsed_ms=lambda s, c: 0,
        )


@pytest.mark.parametrize("lookback", [0, -1, float("inf"), float("nan")])
def test_bad_lookback_cannot_consume_a_request(lookback: float) -> None:
    """Nonfinite or nonpositive lookbacks leave the cold request and clock untouched."""
    clock = ReplayClock(10 * MINUTE)
    fetch = fetcher(clock)
    with pytest.raises(ValueError, match="finite and positive"):
        fetch("BTC", "1m", lookback, end_ms=clock.now_ms)
    assert fetch.completed_requests == 0 and clock.now_ms == 10 * MINUTE


def test_unknown_symbol_does_not_reuse_another_source() -> None:
    """The configured asset universe is an exact source contract."""
    clock = ReplayClock(10 * MINUTE)
    fetch = fetcher(clock)
    with pytest.raises(ValueError, match="no declared historical candle source"):
        fetch("ETH", "1m", 1, end_ms=clock.now_ms)
    assert fetch.completed_requests == 0 and clock.now_ms == 10 * MINUTE
