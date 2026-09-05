"""Shared chronological partition evaluation for HIP-3 development studies."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


PortfolioBuilder = Callable[[bool], SharedPortfolioConfig]


def evaluate_hip3_development_partitions(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    windows: MuChronologicalWindows,
    portfolio_builder: PortfolioBuilder,
) -> tuple[MuPartitionResult, tuple[MuPartitionResult, ...]]:
    """Evaluate only the frozen development interval and its folds."""
    _validate_inputs(bars, signals, windows)
    development = _partition(
        "development",
        bars,
        signals,
        windows.development_start_utc,
        windows.development_end_utc,
        portfolio_builder,
    )
    folds = tuple(
        _partition(
            f"development_fold_{position}",
            bars,
            signals,
            start,
            end,
            portfolio_builder,
        )
        for position, (start, end) in enumerate(windows.development_folds, start=1)
    )
    return development, folds


def _partition(
    name: str,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    portfolio_builder: PortfolioBuilder,
) -> MuPartitionResult:
    """Evaluate nominal and stress scenarios on one half-open interval."""
    selected = bars.index.to_series().ge(start) & bars.index.to_series().lt(end)
    scoped_bars = bars.loc[selected].copy()
    scoped_signals = signals.loc[selected].copy()
    nominal = evaluate_shared_bar_portfolio(
        scoped_bars, scoped_signals, portfolio_builder(False)
    )
    stress = evaluate_shared_bar_portfolio(
        scoped_bars, scoped_signals, portfolio_builder(True)
    )
    return MuPartitionResult(name, start, end, nominal, stress)


def _validate_inputs(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    windows: MuChronologicalWindows,
) -> None:
    """Reject misaligned frames or folds outside development."""
    if bars.empty or not bars.index.equals(signals.index):
        raise ValueError("HIP-3 development bars and signals must align exactly")
    start = windows.development_start_utc
    end = windows.development_end_utc
    has_development_row = bars.index.to_series().lt(end).any()
    if start >= end or bars.index.min() > start or not has_development_row:
        raise ValueError("HIP-3 development window is outside source bars")
    if not windows.development_folds:
        raise ValueError("HIP-3 development requires frozen chronological folds")
    invalid = any(
        fold_start < start or fold_end > end or fold_start >= fold_end
        for fold_start, fold_end in windows.development_folds
    )
    if invalid:
        raise ValueError("HIP-3 development fold is outside development")
