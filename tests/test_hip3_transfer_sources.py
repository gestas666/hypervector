"""HIP-3 funding attachment and midpoint-proxy validation contracts."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_transfer_sources import (
    attach_official_funding,
    compare_midpoint_proxy_to_official,
)


def _bars() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        ["2026-01-01T00:00:00Z", "2026-01-01T00:15:00Z", "2026-01-01T02:00:00Z"]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 103.0],
            "high": [101.0, 102.0, 104.0],
            "low": [99.0, 100.0, 102.0],
            "close": [100.5, 101.5, 103.5],
        },
        index=index,
    )


def _funding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC"),
            "funding_rate": [0.001, 0.002, -0.001],
            "source": ["hl_funding_history"] * 3,
        }
    )


def test_attaches_elapsed_funding_to_first_observed_bar() -> None:
    funded, evidence = attach_official_funding(_bars(), _funding())

    assert funded["funding_rate"].tolist() == [0.001, 0.0, 0.001]
    assert evidence.funding_events == 3
    assert evidence.assigned_event_count == 3
    assert evidence.pre_window_event_count == 0
    assert evidence.post_window_event_count == 0
    assert evidence.delayed_event_count == 1
    assert evidence.maximum_assignment_delay_seconds == 3_600.0
    assert evidence.unassigned_event_count == 0


def test_rejects_internal_hourly_funding_gap() -> None:
    funding = _funding().drop(index=1)

    with pytest.raises(ValueError, match="missing 1 internal hourly rows"):
        attach_official_funding(_bars(), funding)


def test_excludes_complete_funding_prefix_before_first_observed_bar() -> None:
    prefix = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2025-12-31T23:00:00Z")],
            "funding_rate": [0.004],
            "source": ["hl_funding_history"],
        }
    )
    funding = pd.concat([prefix, _funding()], ignore_index=True)

    funded, evidence = attach_official_funding(_bars(), funding)

    assert funded["funding_rate"].tolist() == [0.001, 0.0, 0.001]
    assert evidence.funding_events == 4
    assert evidence.assigned_event_count == 3
    assert evidence.pre_window_event_count == 1
    assert evidence.post_window_event_count == 0
    assert evidence.unassigned_event_count == 1


def test_reports_complete_funding_suffix_after_last_observed_bar() -> None:
    suffix = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01T03:00:00Z")],
            "funding_rate": [0.004],
            "source": ["hl_funding_history"],
        }
    )
    funding = pd.concat([_funding(), suffix], ignore_index=True)

    funded, evidence = attach_official_funding(_bars(), funding)

    assert funded["funding_rate"].tolist() == [0.001, 0.0, 0.001]
    assert evidence.assigned_event_count == 3
    assert evidence.pre_window_event_count == 0
    assert evidence.post_window_event_count == 1
    assert evidence.unassigned_event_count == 1


def test_proxy_validation_reports_ohlc_errors_and_direction_agreement() -> None:
    proxy = _bars().copy()
    official = proxy.reset_index(names="timestamp")
    official.loc[1, "close"] = 101.0
    official.loc[2, "close"] = 104.0

    result = compare_midpoint_proxy_to_official(proxy, official)

    assert result.matched_bars == 3
    assert result.proxy_bars == 3
    assert result.official_bars == 3
    assert result.absolute_error_bps["open"].p50 == pytest.approx(0.0)
    assert result.absolute_error_bps["close"].p90 is not None
    assert result.return_correlation == pytest.approx(1.0)
    assert result.direction_agreement == pytest.approx(1.0)
