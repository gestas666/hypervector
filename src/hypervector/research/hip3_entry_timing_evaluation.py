"""After-cost lifecycle evaluation for causal HIP-3 entry clocks."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleCell,
    Hip3DeployedLifecycleSpec,
    evaluate_deployed_lifecycle,
)
from hypervector.research.hip3_entry_timing import (
    Hip3EntryTimingMode,
    build_hip3_entry_timing_signals,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport
from hypervector.research.swing_ha_signals import EntryMode


@dataclass(frozen=True)
class Hip3EntryTimingCell:
    """One symbol, phase, friction, and causal entry-clock outcome."""

    symbol: str
    phase: str
    friction: str
    timing_mode: Hip3EntryTimingMode
    report: SharedPortfolioReport
    provider_entry_signals: int
    anchor_signals: int
    timing_entry_signals: int
    tail_suppressed_entries: int
    gap_crossing_trades: int
    execution_authority: str = "none"


def evaluate_hip3_entry_timing(
    asset: Hip3TransferAsset,
    friction: Hip3ExecutionFriction,
    provider_signals: pd.DataFrame,
    windows: Hip3TransferWindows,
    *,
    provider_entry_mode: EntryMode,
    spec: Hip3DeployedLifecycleSpec | None = None,
) -> tuple[Hip3EntryTimingCell, ...]:
    """Evaluate all timing modes without reading the sealed holdout window."""
    lifecycle = spec or Hip3DeployedLifecycleSpec()
    output: list[Hip3EntryTimingCell] = []
    for mode in Hip3EntryTimingMode:
        signals = build_hip3_entry_timing_signals(
            asset.bars,
            provider_signals,
            mode,
            provider_entry_mode=provider_entry_mode,
        )
        cells = evaluate_deployed_lifecycle(
            asset,
            friction,
            signals,
            windows,
            spec=lifecycle,
        )
        output.extend(_wrap_cell(cell, signals, mode, windows) for cell in cells)
    return tuple(output)


def _wrap_cell(
    cell: Hip3DeployedLifecycleCell,
    signals: pd.DataFrame,
    mode: Hip3EntryTimingMode,
    windows: Hip3TransferWindows,
) -> Hip3EntryTimingCell:
    phase = cell.phase
    start, end = _phase_bounds(phase, windows)
    selected = signals.index.to_series().ge(start)
    selected &= signals.index.to_series().lt(end)
    phase_signals = signals.loc[selected]
    return Hip3EntryTimingCell(
        symbol=cell.symbol,
        phase=phase,
        friction=cell.friction,
        timing_mode=mode,
        report=cell.report,
        provider_entry_signals=_entry_count(
            phase_signals,
            "provider_long_entry",
            "provider_short_entry",
        ),
        anchor_signals=_entry_count(
            phase_signals,
            "timing_long_anchor",
            "timing_short_anchor",
        ),
        timing_entry_signals=_entry_count(
            phase_signals,
            "long_entry",
            "short_entry",
        ),
        tail_suppressed_entries=cell.tail_suppressed_entries,
        gap_crossing_trades=cell.gap_crossing_trades,
    )


def _phase_bounds(
    phase: str,
    windows: Hip3TransferWindows,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if phase == "development":
        return windows.development_start_utc, windows.development_end_utc
    if phase == "validation":
        return windows.development_end_utc, windows.validation_end_utc
    raise ValueError(f"unsupported HIP-3 timing phase: {phase}")


def _entry_count(frame: pd.DataFrame, long_column: str, short_column: str) -> int:
    return int(frame[[long_column, short_column]].to_numpy(dtype=bool).sum())
