"""Tests for tracker-only source exit proxy reconstruction."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hypervelocity_source_exit_proxy import (
    build_tracker_exit_proxies,
    summarize_tracker_exit_proxies,
)


def _logical() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_ts": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:02:00Z"],
                utc=True,
            ),
            "close_ts": pd.to_datetime(
                ["2026-01-01T00:01:30Z", "2026-01-01T00:03:30Z"],
                utc=True,
            ),
            "side": ["long", "short"],
            "entry_price": [100.0, 100.0],
            "timestamp_provenance": ["tracker_only", "tracker_only"],
        }
    )


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:01:00Z",
                "2026-01-01T00:01:40Z",
                "2026-01-01T00:03:00Z",
                "2026-01-01T00:03:40Z",
            ],
            "mark_price": [101.0, 102.0, 101.0, 99.0],
        }
    )


def test_tracker_exit_proxies_preserve_backward_and_nearest_mark_semantics() -> None:
    proxies = build_tracker_exit_proxies(_logical(), _prices(), leverage=40.0)

    assert proxies["backward_mark_price"].tolist() == [101.0, 101.0]
    assert proxies["nearest_mark_price"].tolist() == [102.0, 99.0]
    assert proxies["backward_mark_age_seconds"].tolist() == [30.0, 30.0]
    assert proxies["nearest_mark_offset_seconds"].tolist() == [10.0, 10.0]
    assert proxies["backward_gross_margin_pct"].tolist() == [40.0, -40.0]
    assert proxies["nearest_gross_margin_pct"].tolist() == [80.0, 40.0]


def test_tracker_exit_proxy_summary_counts_directional_outcomes() -> None:
    proxies = build_tracker_exit_proxies(_logical(), _prices(), leverage=1.0)

    summary = summarize_tracker_exit_proxies(proxies)

    assert summary["positions"] == 2
    assert summary["nearest_positive"] == 2
    assert summary["nearest_negative"] == 0
    assert summary["backward_positive"] == 1
    assert summary["backward_negative"] == 1


def test_tracker_exit_proxies_fail_when_no_closed_tracker_rows_exist() -> None:
    logical = _logical()
    logical["timestamp_provenance"] = "trade_backed"

    with pytest.raises(ValueError, match="closed tracker-only"):
        build_tracker_exit_proxies(logical, _prices())
