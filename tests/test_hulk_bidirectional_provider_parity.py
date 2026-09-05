"""Exact research/live entry parity for the reused bidirectional Hulk route."""

from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest


def _module() -> object:
    try:
        return importlib.import_module(
            "hypervector.research.hulk_bidirectional_provider_parity"
        )
    except ModuleNotFoundError:
        pytest.fail("bidirectional Hulk provider parity is not implemented")


def test_same_raw_rows_produce_nonvacuous_exact_entry_parity() -> None:
    """Research and live paths must agree on one real short entry row."""
    report = _module().build_hulk_bidirectional_provider_parity(
        _five_minute_bars(),
        symbol="SOL",
        observed_at=pd.Timestamp("2026-08-01T01:30:00Z"),
        after_decision_time_ms=0,
        backtest_lab_root=Path("../backtest-lab/backtest_lab"),
        component_builder=_components,
        quality_builder=_quality,
    )

    assert report["historical_entries"] == report["live_entries"] == 1
    assert report["matched_entry_rows"] == 1
    assert report["mismatches"] == []
    assert report["technical_assessment"] == {
        "source_signal_parity_resolved": True,
        "decision_parity_non_vacuous": True,
    }
    assert report["contract"]["execution_authority"] == "none"


def test_changed_live_stop_anchor_falsifies_entry_parity() -> None:
    """A structural-risk mismatch must remain visible in the report."""
    module = _module()
    entry = module.HulkParityEntry(
        decision_time_ms=1_000,
        side="short",
        reference_price=100.0,
        score=9,
        trigger="squeeze_release",
        evidence=("squeeze_release", "adx_usable"),
        stop_anchor=100.8,
    )
    changed = module.HulkParityEntry(
        decision_time_ms=1_000,
        side="short",
        reference_price=100.0,
        score=9,
        trigger="squeeze_release",
        evidence=("squeeze_release", "adx_usable"),
        stop_anchor=101.0,
    )

    report = module.compare_hulk_bidirectional_entries((entry,), (changed,))

    assert report["exact_parity"] is False
    assert report["mismatches"] == [
        {
            "decision_time_ms": 1_000,
            "side": "short",
            "field": "stop_anchor",
            "historical": 100.8,
            "live": 101.0,
        }
    ]


def test_parity_applies_the_same_exclusive_restart_boundary() -> None:
    """Historical entries at the durable cursor must not reappear."""
    boundary = int(pd.Timestamp("2026-08-01T01:00:00Z").timestamp() * 1_000)

    report = _module().build_hulk_bidirectional_provider_parity(
        _five_minute_bars(),
        symbol="SOL",
        observed_at=pd.Timestamp("2026-08-01T01:30:00Z"),
        after_decision_time_ms=boundary,
        backtest_lab_root=Path("../backtest-lab/backtest_lab"),
        component_builder=_components,
        quality_builder=_two_release_quality,
    )

    assert report["historical_entries"] == report["live_entries"] == 1
    assert report["technical_assessment"]["source_signal_parity_resolved"] is True


def _five_minute_bars() -> pd.DataFrame:
    times = pd.date_range("2026-08-01T00:00:00Z", periods=18, freq="5min")
    close = [100.0 - index * 0.05 for index in range(len(times))]
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": [value + 0.02 for value in close],
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
            "volume": [10.0 + index for index in range(len(times))],
        }
    )


def _components(
    bars: pd.DataFrame,
    root: object,
    *,
    bar_minutes: int,
) -> pd.DataFrame:
    del root
    assert bar_minutes == 30
    index = pd.DatetimeIndex(bars["bar_open_at"])
    return pd.DataFrame(
        {
            "wt1": 0.0,
            "wave_cross": 0,
            "money_flow_direction": -1,
            "volume_ratio": 1.2,
            "ema_trend": -1,
            "krown_direction": -1,
            "krown_zone_context": -1,
        },
        index=index,
    )


def _quality(bars: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
    del kwargs
    release = [False] * len(bars)
    release[-1] = True
    return pd.DataFrame(
        {
            "supertrend_direction": -1,
            "adx": 20.0,
            "di_direction": -1,
            "squeeze_on": False,
            "squeeze_release": release,
            "ha_choppy": False,
        },
        index=bars.index,
    )


def _two_release_quality(bars: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
    frame = _quality(bars, **kwargs)
    frame.iloc[-2, frame.columns.get_loc("squeeze_release")] = True
    return frame
