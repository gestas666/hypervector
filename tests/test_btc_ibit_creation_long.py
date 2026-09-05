"""Tests for point-in-time IBIT creation-persistence long signals."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_ibit_creation_long import (
    build_btc_ibit_creation_signals,
)


def test_primary_fires_on_second_positive_only_and_zero_rearms() -> None:
    """Persistence emits once, suppresses a third positive, and resets on zero."""
    history = _history(
        pd.date_range("2026-08-01", periods=8, freq="1D"),
        [100, 110, 120, 130, 130, 140, 150, 160],
    )
    expected = ("2026-08-04T12:00:00+00:00", "2026-08-08T12:00:00+00:00")
    market = _market(*expected)

    result = build_btc_ibit_creation_signals(history, market)

    assert result.candidate_event_times_utc == expected
    assert _entry_times(result.candidate_entries) == expected
    assert (
        not result.candidate_entries[["short_entry", "long_exit", "short_exit"]]
        .to_numpy()
        .any()
    )
    assert set(result.candidate_entries["signal_name"]) == {
        "ibit_two_creation_persistence_long_v1"
    }


def test_consecutive_issuer_observations_cross_weekend() -> None:
    """Missing weekend dates must not fabricate resets between issuer rows."""
    history = _history(
        pd.to_datetime(["2026-08-07", "2026-08-10", "2026-08-11"]),
        [100, 110, 120],
    )
    expected = "2026-08-12T12:00:00+00:00"

    result = build_btc_ibit_creation_signals(history, _market(expected))

    assert result.candidate_event_times_utc == (expected,)
    assert _entry_times(result.candidate_entries) == (expected,)


def test_creation_control_and_redemption_placebo_use_distinct_onsets() -> None:
    """Controls must preserve the exact frozen state-transition definitions."""
    history = _history(
        pd.date_range("2026-08-01", periods=10, freq="1D"),
        [100, 110, 120, 120, 110, 100, 90, 90, 100, 110],
    )
    market = _market(
        "2026-08-03T12:00:00Z",
        "2026-08-04T12:00:00Z",
        "2026-08-07T12:00:00Z",
        "2026-08-10T12:00:00Z",
        "2026-08-11T12:00:00Z",
    )

    result = build_btc_ibit_creation_signals(history, market)

    assert result.candidate_event_times_utc == (
        "2026-08-04T12:00:00+00:00",
        "2026-08-11T12:00:00+00:00",
    )
    assert result.single_creation_event_times_utc == (
        "2026-08-03T12:00:00+00:00",
        "2026-08-10T12:00:00+00:00",
    )
    assert result.redemption_placebo_event_times_utc == ("2026-08-07T12:00:00+00:00",)
    assert result.redemption_placebo_entries["short_entry"].sum() == 0


def test_missing_market_minute_cancels_instead_of_nearest_mapping() -> None:
    """An event inside coverage but absent from the index is an explicit gap."""
    history = _history(
        pd.date_range("2026-08-01", periods=3, freq="1D"),
        [100, 110, 120],
    )
    missing = "2026-08-04T12:00:00+00:00"
    market = _market("2026-08-04T11:59:00Z", "2026-08-04T12:01:00Z")

    result = build_btc_ibit_creation_signals(history, market)

    assert result.candidate_entries["long_entry"].sum() == 0
    assert result.candidate_market_gap_times_utc == (missing,)


def test_out_of_range_event_is_not_fabricated_on_market_boundary() -> None:
    """Availability before market coverage cannot shift to the first minute."""
    history = _history(
        pd.date_range("2026-08-01", periods=3, freq="1D"),
        [100, 110, 120],
    )
    market = _market("2026-08-05T00:00:00Z", "2026-08-05T00:01:00Z")

    result = build_btc_ibit_creation_signals(history, market)

    assert result.candidate_entries["long_entry"].sum() == 0
    assert result.candidate_market_gap_times_utc == ()


@pytest.mark.parametrize(
    "dates, message",
    [
        (["2026-08-01", "2026-08-01"], "duplicate as-of dates"),
        (["2026-08-02", "2026-08-01"], "increasing as-of dates"),
    ],
)
def test_history_requires_unique_increasing_dates(
    dates: list[str],
    message: str,
) -> None:
    """Signal state must not depend on ambiguous issuer row ordering."""
    history = _history(pd.to_datetime(dates), [100, 110])

    with pytest.raises(ValueError, match=message):
        build_btc_ibit_creation_signals(history, _market("2026-08-04T12:00:00Z"))


def test_market_index_rejects_duplicates_and_naive_timestamps() -> None:
    """Entry mapping requires exact unique UTC minute labels."""
    history = _history(pd.date_range("2026-08-01", periods=3), [100, 110, 120])
    duplicate = pd.to_datetime(
        ["2026-08-04T12:00:00Z", "2026-08-04T12:00:00Z"], utc=True
    )
    naive = pd.date_range("2026-08-04T12:00:00", periods=2, freq="1min")

    with pytest.raises(ValueError, match="unique increasing"):
        build_btc_ibit_creation_signals(history, duplicate)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_btc_ibit_creation_signals(history, naive)


def test_market_index_rejects_nonminute_labels() -> None:
    """Subminute labels cannot represent a one-minute-open decision boundary."""
    history = _history(pd.date_range("2026-08-01", periods=3), [100, 110, 120])
    market = pd.to_datetime(["2026-08-04T12:00:30Z"], utc=True)

    with pytest.raises(ValueError, match="exact minute labels"):
        build_btc_ibit_creation_signals(history, market)


def _history(dates: pd.DatetimeIndex, shares: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "as_of_date": dates,
            "nav_per_share": [30.0] * len(dates),
            "shares_outstanding": shares,
        }
    )


def _market(*values: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True)).sort_values()


def _entry_times(frame: pd.DataFrame) -> tuple[str, ...]:
    return tuple(
        timestamp.isoformat() for timestamp in frame.index[frame["long_entry"]]
    )
