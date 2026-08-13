"""Tests for sampled Hyperliquid mark-price stop bounds."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.mark_stop_trigger import (
    MarkQueryGapError,
    SampledMarkSeries,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_ms": [1_000, 2_000, 3_000, 4_000],
            "mark_price": [100.0, 99.0, 101.0, 98.0],
        }
    )


def test_mark_series_returns_first_long_stop_crossing() -> None:
    """A long stop uses the first sampled mark at or below its barrier."""
    crossing = SampledMarkSeries(_frame(), maximum_gap_ms=1_000).first_crossing(
        "long", 99.5, 1_000, 4_001
    )

    assert crossing is not None
    assert crossing.timestamp_ms == 2_000
    assert crossing.mark_price == pytest.approx(99.0)


def test_mark_series_returns_first_short_stop_crossing() -> None:
    """A short stop uses the first sampled mark at or above its barrier."""
    crossing = SampledMarkSeries(_frame(), maximum_gap_ms=1_000).first_crossing(
        "short", 100.5, 1_000, 4_001
    )

    assert crossing is not None
    assert crossing.timestamp_ms == 3_000


def test_mark_series_uses_half_open_trigger_window() -> None:
    """A mark at the planned exit time belongs to the planned exit path."""
    crossing = SampledMarkSeries(_frame(), maximum_gap_ms=1_000).first_crossing(
        "long", 99.5, 1_000, 2_000
    )

    assert crossing is None


def test_mark_series_returns_bounded_observations() -> None:
    """Drawdown consumers must receive only the requested half-open mark path."""
    observations = SampledMarkSeries(_frame(), maximum_gap_ms=1_000).observations(
        2_000, 4_000
    )

    assert [(item.timestamp_ms, item.mark_price) for item in observations] == [
        (2_000, 99.0),
        (3_000, 101.0),
    ]


def test_mark_series_rejects_gap_larger_than_contract() -> None:
    """Sparse marks must not masquerade as continuous trigger evidence."""
    with pytest.raises(ValueError, match="gap"):
        SampledMarkSeries(_frame(), maximum_gap_ms=999)


def test_query_scoped_series_ignores_flat_gaps_but_rejects_active_gaps() -> None:
    """Sparse flat periods may pass, but an active query crossing one must fail."""
    frame = pd.DataFrame(
        {
            "ts_ms": [0, 60_000, 600_000, 660_000],
            "mark_price": [100.0, 99.0, 101.0, 98.0],
        }
    )
    marks = SampledMarkSeries(
        frame,
        maximum_gap_ms=60_000,
        query_scoped=True,
    )

    assert len(marks.observations(0, 60_001)) == 2
    with pytest.raises(MarkQueryGapError, match="query gap"):
        marks.observations(0, 660_001)


def test_first_crossing_ignores_archive_gap_after_causal_exit() -> None:
    """Missing marks after an observed stop cannot censor the earlier exit."""
    marks = SampledMarkSeries(
        pd.DataFrame(
            {
                "ts_ms": [0, 60_000, 600_000, 660_000],
                "mark_price": [100.0, 98.0, 101.0, 102.0],
            }
        ),
        maximum_gap_ms=60_000,
        query_scoped=True,
    )

    crossing = marks.first_crossing("long", 99.0, 0, 660_001)

    assert crossing is not None
    assert crossing.timestamp_ms == 60_000


def test_first_crossing_rejects_archive_gap_before_candidate_exit() -> None:
    """A sampled crossing after an unobserved interval remains censored."""
    marks = SampledMarkSeries(
        pd.DataFrame(
            {
                "ts_ms": [0, 60_000, 600_000, 660_000],
                "mark_price": [100.0, 100.0, 98.0, 97.0],
            }
        ),
        maximum_gap_ms=60_000,
        query_scoped=True,
    )

    with pytest.raises(MarkQueryGapError, match="query gap"):
        marks.first_crossing("long", 99.0, 0, 660_001)


def test_short_empty_query_uses_enclosing_sample_gap_contract() -> None:
    """An interval between nearby samples is empty, not an archive outage."""
    marks = SampledMarkSeries(
        pd.DataFrame({"ts_ms": [1_000, 2_000], "mark_price": [100.0, 101.0]}),
        maximum_gap_ms=1_000,
        query_scoped=True,
    )

    assert marks.observations(1_200, 1_300) == ()


def test_empty_query_inside_large_sample_gap_remains_censored() -> None:
    """An empty interval inside an excessive enclosing gap must fail closed."""
    marks = SampledMarkSeries(
        pd.DataFrame({"ts_ms": [1_000, 3_000], "mark_price": [100.0, 101.0]}),
        maximum_gap_ms=1_000,
        query_scoped=True,
    )

    with pytest.raises(MarkQueryGapError, match="query gap"):
        marks.observations(1_500, 1_600)


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"ts_ms": [1_000, 1_000], "mark_price": [100.0, 99.0]}),
        pd.DataFrame({"ts_ms": [2_000, 1_000], "mark_price": [100.0, 99.0]}),
        pd.DataFrame({"ts_ms": [1_000], "mark_price": [0.0]}),
    ],
)
def test_mark_series_rejects_invalid_observations(frame: pd.DataFrame) -> None:
    """Duplicate, unordered, or invalid mark observations fail closed."""
    with pytest.raises(ValueError):
        SampledMarkSeries(frame, maximum_gap_ms=1_000)
