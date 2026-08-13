"""Development-only MU technical path diagnostic contracts."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveTrack
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.mu_hip3_development_path_diagnostic import (
    development_path_threshold_diagnostic,
    hip3_development_path_threshold_diagnostic,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def _trade(direction: str, entry_position: int) -> SharedPortfolioTrade:
    index = pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC")
    return SharedPortfolioTrade(
        "hip3_breakout_pressure",
        direction,
        index[entry_position - 1].isoformat(),
        index[entry_position].isoformat(),
        index[entry_position + 1].isoformat(),
        entry_position - 1,
        entry_position,
        entry_position + 1,
        100.0,
        101.0 if direction == "long" else 99.0,
        None,
        99.2 if direction == "long" else 100.8,
        82.0 if direction == "long" else 118.0,
        1.0,
        20.0,
        100.0,
        5.0,
        1.0,
        0.0,
        0.0,
        1.0,
        500.0,
        501.0,
        "signal",
        False,
    )


def _report() -> SharedPortfolioReport:
    trades = (_trade("long", 1), _trade("short", 2))
    return SharedPortfolioReport(
        500.0,
        502.0,
        2.0,
        0.4,
        -0.2,
        2,
        2,
        0,
        2.0,
        0.0,
        None,
        0,
        0.0,
        0.0,
        0,
        1,
        0,
        0,
        False,
        {},
        (),
        trades,
    )


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC")
    gaps = [4_000.0, 5_500.0, 7_000.0, 16_000.0]
    return pd.DataFrame(
        {
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": [True, False, False, False],
            "maximum_mark_interval_ms": gaps,
            "mark_snapshot_count": 100,
            "trade_bundle_complete": True,
            "entry_mark_path_complete": [True, False, False, False],
            "entry_maximum_mark_interval_ms": gaps,
            "entry_mark_snapshot_count": 100,
            "first_boundary_delay_ms": 100.0,
            "maximum_snapshot_interval_ms": 100.0,
            "end_boundary_age_ms": 100.0,
            "source_snapshot_count": 100,
        },
        index=index,
    )


def _partition(name: str = "development") -> MuPartitionResult:
    report = _report()
    index = _bars().index
    return MuPartitionResult(
        name, index[0], index[-1] + pd.Timedelta(minutes=15), report, report
    )


def _track() -> MuArchiveTrack:
    return MuArchiveTrack(
        "15m",
        "breakout_pressure",
        "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
        "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
        Hip3BreakoutPressureConfig(32, 9, 21, 0.1, 80.0),
    )


def _windows() -> MuChronologicalWindows:
    partition = _partition()
    span = partition.end_utc - partition.start_utc
    return MuChronologicalWindows(
        partition.start_utc,
        partition.end_utc,
        partition.end_utc + span,
        partition.end_utc + 2 * span,
        ((partition.start_utc, partition.end_utc),),
    )


def test_threshold_diagnostic_is_monotone_and_retains_both_sides() -> None:
    result = development_path_threshold_diagnostic(
        _bars(),
        _partition(),
        track=_track(),
        windows=_windows(),
    )

    assert result["status"] == "unresolved"
    assert result["qualification_authority"] == "none"
    thresholds = result["cumulative_thresholds_ms"]
    assert thresholds["5000"]["nominal"]["affected_trades"] == 2
    assert thresholds["6000"]["nominal"]["affected_trades"] == 1
    assert thresholds["7500"]["nominal"]["affected_trades"] == 0
    assert thresholds["5000"]["nominal"]["by_side"]["long"] == 1
    assert thresholds["5000"]["nominal"]["by_side"]["short"] == 1
    assert len(thresholds["5000"]["unresolved_lifecycles"]["nominal"]) == 2
    unresolved = result["unresolved_lifecycles_5000ms"]["nominal"]
    assert len(unresolved) == 2
    assert unresolved[0]["lifecycle_key"].startswith("long|2026-01-01")
    assert unresolved[0]["mark_path_unresolved"] is True
    assert result["monotonicity_verified"] is True


def test_diagnostic_rejects_any_non_development_partition() -> None:
    with pytest.raises(ValueError, match="development-only"):
        development_path_threshold_diagnostic(
            _bars(),
            replace(_partition(), name="validation"),
            track=_track(),
            windows=_windows(),
        )


def test_diagnostic_ignores_rows_outside_frozen_development_bounds() -> None:
    bars = _bars()
    outside = bars.iloc[[-1]].copy()
    outside.index = outside.index + pd.Timedelta(minutes=15)
    outside["maximum_mark_interval_ms"] = 999_999.0
    outside["entry_maximum_mark_interval_ms"] = 999_999.0

    baseline = development_path_threshold_diagnostic(
        bars,
        _partition(),
        track=_track(),
        windows=_windows(),
    )
    appended = development_path_threshold_diagnostic(
        pd.concat([bars, outside]),
        _partition(),
        track=_track(),
        windows=_windows(),
    )

    assert appended == baseline


def test_diagnostic_rejects_any_other_track_identity() -> None:
    wrong = replace(_track(), timeframe="5m")

    with pytest.raises(ValueError, match="frozen selected track"):
        development_path_threshold_diagnostic(
            _bars(),
            _partition(),
            track=wrong,
            windows=_windows(),
        )


def test_diagnostic_rejects_shifted_self_asserted_development_bounds() -> None:
    shifted = replace(
        _partition(),
        start_utc=_partition().start_utc + pd.Timedelta(days=1),
        end_utc=_partition().end_utc + pd.Timedelta(days=1),
    )

    with pytest.raises(ValueError, match="canonical development window"):
        development_path_threshold_diagnostic(
            _bars(),
            shifted,
            track=_track(),
            windows=_windows(),
        )


def test_generic_diagnostic_accepts_an_exact_non_mu_selected_track() -> None:
    track = replace(
        _track(),
        provider_id="hip3_skhx_full_l2_breakout_pressure_bidirectional_15m_v1",
        profile_id="skhx_full_l2_breakout_pressure_bidirectional_15m_research_v1",
        config=Hip3BreakoutPressureConfig(16, 21, 55, 0.5, 40.0),
    )

    result = hip3_development_path_threshold_diagnostic(
        _bars(),
        _partition(),
        track=track,
        windows=_windows(),
    )

    assert result["track"]["provider_id"] == track.provider_id
    assert result["qualification_authority"] == "none"


def test_generic_diagnostic_uses_the_selected_five_minute_interval() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="5min", tz="UTC")
    bars = _bars().set_axis(index)
    bars["maximum_mark_interval_ms"] = 100.0
    bars["entry_maximum_mark_interval_ms"] = 100.0
    bars["mark_path_complete"] = True
    bars["entry_mark_path_complete"] = True
    bars.loc[index[0], "mark_path_complete"] = False
    bars.loc[index[0], "maximum_mark_interval_ms"] = 16_000.0
    trade = replace(
        _trade("long", 1),
        signal_time_utc=index[0].isoformat(),
        entry_time_utc=index[1].isoformat(),
        exit_time_utc=index[2].isoformat(),
    )
    report = replace(_report(), completed_trades=1, trades=(trade,))
    partition = MuPartitionResult(
        "development", index[0], index[-1] + pd.Timedelta(minutes=5), report, report
    )
    span = partition.end_utc - partition.start_utc
    windows = MuChronologicalWindows(
        partition.start_utc,
        partition.end_utc,
        partition.end_utc + span,
        partition.end_utc + 2 * span,
        ((partition.start_utc, partition.end_utc),),
    )
    track = replace(
        _track(),
        timeframe="5m",
        provider_id="hip3_skhx_full_l2_breakout_pressure_bidirectional_5m_v1",
        profile_id="skhx_full_l2_breakout_pressure_bidirectional_5m_research_v1",
    )

    result = hip3_development_path_threshold_diagnostic(
        bars, partition, track=track, windows=windows
    )

    assert result["unresolved_lifecycles_5000ms"]["nominal"] == []
