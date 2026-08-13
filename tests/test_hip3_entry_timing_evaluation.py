"""After-cost evaluation contract for HIP-3 entry-timing challengers."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from hypervector.research.hip3_deployed_lifecycle import Hip3DeployedLifecycleSpec
from hypervector.research.hip3_entry_timing import Hip3EntryTimingMode
from hypervector.research.hip3_entry_timing_evaluation import (
    evaluate_hip3_entry_timing,
)
from hypervector.research.hip3_entry_timing_reporting import (
    build_hip3_entry_timing_report,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=20, freq="15min", tz="UTC")
    close = [100.0 + (position % 4) * 0.05 for position in range(20)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
            "entry_bid": [value - 0.01 for value in close],
            "entry_ask": [value + 0.01 for value in close],
            "decision_bid": [value - 0.01 for value in close],
            "decision_ask": [value + 0.01 for value in close],
            "gap_before_bars": [0] * 20,
            "funding_rate": [0.0] * 20,
        },
        index=index,
    )


def _signals() -> pd.DataFrame:
    bars = _bars()
    long_alignment = [False] * 20
    short_alignment = [False] * 20
    for position in (0, 1, 2, 3, 10, 11, 12, 13):
        long_alignment[position] = True
    for position in (5, 6, 7, 8, 15, 16, 17):
        short_alignment[position] = True
    return pd.DataFrame(
        {
            "long_alignment": long_alignment,
            "short_alignment": short_alignment,
            "long_entry": long_alignment,
            "short_entry": short_alignment,
            "long_exit": [False] * 20,
            "short_exit": [False] * 20,
            "ema_fast": [100.0] * 20,
        },
        index=bars.index,
    )


def _windows() -> Hip3TransferWindows:
    index = _bars().index
    return Hip3TransferWindows(
        development_start_utc=index[0],
        development_end_utc=index[10],
        validation_end_utc=index[18],
        holdout_end_utc=index[-1] + pd.Timedelta(minutes=15),
        development_folds=((index[0], index[10]),),
    )


def test_evaluation_covers_every_mode_phase_and_friction_without_holdout() -> None:
    asset = Hip3TransferAsset("xyz:SPCX", 5.0, _bars())
    friction = Hip3ExecutionFriction(75.0, 0.0001, 1.0, 0.0, 4.0, 1.0)
    spec = Hip3DeployedLifecycleSpec(maximum_hold_seconds=1_800)

    cells = evaluate_hip3_entry_timing(
        asset,
        friction,
        _signals(),
        _windows(),
        provider_entry_mode="state",
        spec=spec,
    )

    assert len(cells) == 16
    assert {cell.timing_mode for cell in cells} == set(Hip3EntryTimingMode)
    assert {(cell.phase, cell.friction) for cell in cells} == {
        ("development", "nominal"),
        ("development", "stress"),
        ("validation", "nominal"),
        ("validation", "stress"),
    }
    assert all(cell.execution_authority == "none" for cell in cells)
    assert all(
        trade.exit_time_utc < _windows().validation_end_utc.isoformat()
        for cell in cells
        for trade in cell.report.trades
    )


def test_report_exposes_capture_after_cost_side_and_concentration_metrics() -> None:
    asset = Hip3TransferAsset("xyz:SPCX", 5.0, _bars())
    friction = Hip3ExecutionFriction(75.0, 0.0001, 1.0, 0.0, 4.0, 1.0)
    cells = evaluate_hip3_entry_timing(
        asset,
        friction,
        _signals(),
        _windows(),
        provider_entry_mode="state",
        spec=Hip3DeployedLifecycleSpec(maximum_hold_seconds=1_800),
    )

    second_asset = tuple(
        replace(
            cell,
            symbol="xyz:SP500",
            report=replace(cell.report, maximum_drawdown_pct=-5.0),
        )
        for cell in cells
    )
    all_cells = (*cells, *second_asset)
    report = build_hip3_entry_timing_report(
        strategy_id="hip3_swing_test",
        provider_entry_mode="state",
        cells=all_cells,
        windows=_windows(),
    )

    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["holdout"]["metrics_accessed"] is False
    assert report["windows"] == {
        "development_start_utc": _windows().development_start_utc.isoformat(),
        "development_end_utc": _windows().development_end_utc.isoformat(),
        "validation_end_utc": _windows().validation_end_utc.isoformat(),
        "holdout_end_utc": _windows().holdout_end_utc.isoformat(),
    }
    result = report["results"]["validation"]["nominal"][
        Hip3EntryTimingMode.FIRST_FAST_EMA_PULLBACK.value
    ]["xyz:SPCX"]
    assert 0.0 <= result["signal_capture_ratio"] <= 1.0
    assert set(result["directions"]) == {"long", "short"}
    assert "net_pnl_ex_largest_winner_usd" in result["concentration"]
    assert "profit_factor_ex_largest_winner" in result["concentration"]
    validation_nominal = [
        cell.report.maximum_drawdown_pct
        for cell in all_cells
        if cell.phase == "validation"
        and cell.friction == "nominal"
        and cell.timing_mode is Hip3EntryTimingMode.PROVIDER_EXACT
    ]
    aggregate = report["aggregates"]["validation"]["nominal"]["provider_exact"]
    assert aggregate["worst_independent_asset_drawdown_pct"] == min(validation_nominal)
