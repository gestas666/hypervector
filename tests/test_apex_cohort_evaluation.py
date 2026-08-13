"""Business-logic contracts for bounded Apex cohort evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.apex_cohort_evaluation import (
    _directional_signals,
    _load_funding,
    _market_maker_sessions,
    _oi_coverage_status,
)


def test_funding_loader_requires_every_hour_and_maps_exact_settlements(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 3, tzinfo=UTC)
    funding_path = tmp_path / "funding.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.date_range(start, end, freq="h", inclusive="left"),
            "funding_rate": [0.001, -0.002, 0.003],
            "source": ["hl_funding_history"] * 3,
        }
    ).to_parquet(funding_path, index=False)
    bars = pd.date_range(start, end, freq="5min", inclusive="left")

    rates = _load_funding(funding_path, start, end, bars)

    assert rates.ne(0.0).sum() == 3
    assert rates.loc[pd.Timestamp("2026-01-01T01:00:00Z")] == -0.002


def test_funding_loader_rejects_missing_hour(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 3, tzinfo=UTC)
    funding_path = tmp_path / "funding.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z"]
            ),
            "funding_rate": [0.001, 0.003],
            "source": ["hl_funding_history"] * 2,
        }
    ).to_parquet(funding_path, index=False)
    bars = pd.date_range(start, end, freq="5min", inclusive="left")

    with pytest.raises(ValueError, match="missing 1 hourly"):
        _load_funding(funding_path, start, end, bars)


def test_directional_signal_adapter_combines_explicit_exit_reasons() -> None:
    index = pd.date_range("2026-01-01", periods=2, freq="5min", tz="UTC")
    source = pd.DataFrame(
        {
            "long_entry": [True, False],
            "short_entry": [False, True],
            "long_exit_mean": [False, True],
            "long_exit_invalidation": [True, False],
            "short_exit_mean": [False, False],
            "short_exit_invalidation": [False, True],
        },
        index=index,
    )

    signals = _directional_signals(source, "apex_mean_reversion_v2", False)

    assert signals["long_exit"].tolist() == [True, True]
    assert signals["short_exit"].tolist() == [False, True]
    assert signals["signal_name"].eq("apex_mean_reversion_v2").all()


def test_robustness_adapter_delays_directional_decisions_one_extra_bar() -> None:
    index = pd.date_range("2026-01-01", periods=2, freq="5min", tz="UTC")
    source = pd.DataFrame(
        {
            "long_entry": [True, False],
            "short_entry": [False, False],
            "long_exit_mean": [False, False],
            "long_exit_invalidation": [False, False],
            "short_exit_mean": [False, False],
            "short_exit_invalidation": [False, False],
        },
        index=index,
    )

    signals = _directional_signals(source, "apex_mean_reversion_v2", True)

    assert signals["long_entry"].tolist() == [False, True]


def test_oi_history_below_ninety_percent_remains_observer_only() -> None:
    coverage = _oi_coverage_status(covered_bars=100, expected_bars=10_000)

    assert coverage["status"] == "observer_only_insufficient_history"
    assert coverage["coverage_fraction"] == pytest.approx(0.01)


def test_market_maker_sessions_are_fixed_intrahour_samples() -> None:
    start = datetime(2026, 1, 28, tzinfo=UTC)
    end = datetime(2026, 4, 28, tzinfo=UTC)

    sessions = _market_maker_sessions(start, end)

    assert len(sessions) == 12
    assert all(session_start.day == 7 for session_start, _ in sessions)
    assert all(session_start.minute == 5 for session_start, _ in sessions)
    assert all(
        (session_end - session_start).total_seconds() == 1_800
        for session_start, session_end in sessions
    )
    assert all(
        start <= session_start < session_end <= end
        for session_start, session_end in sessions
    )
