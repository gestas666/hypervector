"""Tests for the immutable HYPE five-minute impulse research report."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_impulse_5m_candidate import (
    HypeImpulseReplay,
    HypeImpulseTrade,
)


def _study_module():
    from hypervector.research import hype_impulse_5m_study

    return hype_impulse_5m_study


def _bars(count: int = 125) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * count,
            "high": [100.1] * count,
            "low": [99.9] * count,
            "close": [100.0] * count,
            "volume": [10.0] * count,
            "contains_gap_fill": [False] * count,
        }
    )


def _trade(net_bps: float, position: int) -> HypeImpulseTrade:
    entry = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=position * 5)
    return HypeImpulseTrade(
        signal_time=entry - pd.Timedelta(minutes=5),
        entry_time=entry,
        exit_time=entry + pd.Timedelta(minutes=5),
        side="long",
        entry_price=100.0,
        exit_price=100.0,
        exit_reason="maximum_hold",
        holding_minutes=5,
        gross_bps=net_bps + 13.0,
        cost_bps=13.0,
        funding_bps=0.0,
        net_bps=net_bps,
    )


def test_chronological_windows_are_nonoverlapping_sixty_twenty_twenty() -> None:
    study = _study_module()
    bars = _bars(10)

    windows = study.chronological_windows(bars)

    assert [
        (item.name, item.start_position, item.end_position) for item in windows
    ] == [
        ("development", 0, 6),
        ("validation", 6, 8),
        ("holdout", 8, 10),
    ]
    assert windows[0].end == windows[1].start
    assert windows[1].end == windows[2].start


def test_replay_summary_reports_repeatability_and_drawdown() -> None:
    study = _study_module()
    replay = HypeImpulseReplay(
        trades=(_trade(10.0, 1), _trade(-5.0, 2), _trade(2.0, 3)),
        candidate_signals=3,
        gap_censored=0,
        boundary_censored=0,
    )

    summary = study.summarize_replay(replay)

    assert summary["closed_trades"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["net_bps"] == pytest.approx(7.0)
    assert summary["profit_factor"] == pytest.approx(2.4)
    assert summary["net_bps_excluding_largest_winner"] == pytest.approx(-3.0)
    assert summary["maximum_closed_sequence_drawdown_bps"] == pytest.approx(5.0)


def test_study_reports_both_temporal_interpretations_sides_and_costs() -> None:
    study = _study_module()
    report = study.build_study_report(
        _bars(),
        pd.Series(dtype=float),
        nominal_cost_bps=13.0,
        stress_cost_bps=26.0,
    )

    assert report["contract"] == {
        "automatic_promotion": False,
        "execution_authority": "none",
        "performance_gate": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    assert set(report["variants"]) == {"corrected_23m", "legacy_behavior_115m"}
    for variant in report["variants"].values():
        assert set(variant["sides"]) == {"long", "short"}
        for side in variant["sides"].values():
            assert set(side) == {"development", "validation", "holdout"}
            assert set(side["development"]) == {"nominal", "stress"}


def test_study_rejects_stress_cost_cheaper_than_nominal() -> None:
    study = _study_module()

    with pytest.raises(ValueError, match="stress cost"):
        study.build_study_report(
            _bars(),
            pd.Series(dtype=float),
            nominal_cost_bps=13.0,
            stress_cost_bps=12.0,
        )
