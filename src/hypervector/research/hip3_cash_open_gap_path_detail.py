"""Exact development path attribution for cash-open gap-reversal research."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    Hip3CashOpenGapDevelopmentResult,
)
from hypervector.research.mu_hip3_archive_reporting import (
    _evidence_at_or_before,
    _stale_exit_quote,
    _stale_l2_row,
    _verified_entry_risk_path_resolution,
    _verified_risk_path_resolution,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)

_INTERVAL = pd.Timedelta(minutes=15)


def build_cash_open_gap_path_detail(
    result: Hip3CashOpenGapDevelopmentResult,
    bars: pd.DataFrame,
) -> dict[str, object]:
    """Bind every unresolved development lifecycle to exact source bars."""
    scoped = _development_bars(result, bars)
    full = _verified_risk_path_resolution(scoped)
    entry = _verified_entry_risk_path_resolution(scoped, full)
    return {
        "schema_version": "hip3_cash_open_gap_path_detail_v2",
        "status": "unresolved"
        if _has_unresolved(result, scoped, full, entry)
        else "resolved",
        "qualification_authority": "none",
        "validation_accessed": False,
        "holdout_accessed": False,
        "development_start_utc": result.windows.development_start_utc.isoformat(),
        "development_end_utc": result.windows.development_end_utc.isoformat(),
        "nominal": _scenario(scoped, result.development.nominal, full, entry),
        "stress": _scenario(scoped, result.development.stress, full, entry),
    }


def _development_bars(
    result: Hip3CashOpenGapDevelopmentResult,
    bars: pd.DataFrame,
) -> pd.DataFrame:
    start = result.windows.development_start_utc
    end = result.windows.development_end_utc
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("cash-open path detail requires timezone-aware bars")
    scoped = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    if (
        scoped.empty
        or not scoped.index.is_unique
        or not scoped.index.is_monotonic_increasing
    ):
        raise ValueError("cash-open path detail requires ordered development bars")
    return scoped


def _has_unresolved(
    result: Hip3CashOpenGapDevelopmentResult,
    bars: pd.DataFrame,
    full: pd.Series,
    entry: pd.Series,
) -> bool:
    reports = (result.development.nominal, result.development.stress)
    return any(
        _trade_causes(bars, trade, full, entry)
        for report in reports
        for trade in report.trades
    )


def _scenario(
    bars: pd.DataFrame,
    report: SharedPortfolioReport,
    full: pd.Series,
    entry: pd.Series,
) -> dict[str, object]:
    lifecycles = [
        detail
        for trade in report.trades
        if (detail := _lifecycle_detail(bars, trade, full, entry)) is not None
    ]
    full_indices, entry_indices = _unresolved_bar_sets(bars, report.trades, full, entry)
    union_indices = sorted(full_indices | entry_indices)
    return {
        "completed_trades": report.completed_trades,
        "unresolved_full_path_bar_count": len(full_indices),
        "unresolved_entry_slice_bar_count": len(entry_indices),
        "unresolved_union_bar_count": len(union_indices),
        "unresolved_full_path_bars": _bar_details(bars, full, entry, full_indices),
        "unresolved_entry_slice_bars": _bar_details(bars, full, entry, entry_indices),
        "unresolved_lifecycles": lifecycles,
        "unresolved_bars": [
            _bar_detail(bars.loc[index], index, full, entry) for index in union_indices
        ],
    }


def _lifecycle_detail(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    full: pd.Series,
    entry: pd.Series,
) -> dict[str, object] | None:
    causes = _trade_causes(bars, trade, full, entry)
    if not causes:
        return None
    return {
        "lifecycle_key": _lifecycle_key(trade),
        "direction": trade.direction,
        "signal_time_utc": trade.signal_time_utc,
        "entry_time_utc": trade.entry_time_utc,
        "exit_time_utc": trade.exit_time_utc,
        **causes,
    }


def _trade_causes(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    full: pd.Series,
    entry: pd.Series,
) -> dict[str, bool]:
    entry_at = pd.Timestamp(trade.entry_time_utc)
    active = _active_rows(bars, trade)
    causes = {
        "full_mark_path_unresolved": bool((~full.loc[active]).any()),
        "entry_slice_unresolved": not _evidence_at_or_before(entry, entry_at),
        "stale_l2_entry": _stale_l2_row(bars, entry_at, "entry"),
        "stale_l2_exit": _stale_exit_quote(bars, trade),
        "data_gap_exit": trade.exit_reason == "data_gap",
    }
    return causes if any(causes.values()) else {}


def _unresolved_bar_sets(
    bars: pd.DataFrame,
    trades: Iterable[SharedPortfolioTrade],
    full: pd.Series,
    entry: pd.Series,
) -> tuple[set[pd.Timestamp], set[pd.Timestamp]]:
    full_indices: set[pd.Timestamp] = set()
    entry_indices: set[pd.Timestamp] = set()
    for trade in trades:
        active = _active_rows(bars, trade)
        full_indices.update(pd.Timestamp(value) for value in bars.index[active & ~full])
        entry_at = pd.Timestamp(trade.entry_time_utc)
        if not _evidence_at_or_before(entry, entry_at):
            candidates = bars.index[bars.index <= entry_at]
            if len(candidates):
                entry_indices.add(pd.Timestamp(candidates[-1]))
    return full_indices, entry_indices


def _bar_details(
    bars: pd.DataFrame,
    full: pd.Series,
    entry: pd.Series,
    indices: set[pd.Timestamp],
) -> list[dict[str, object]]:
    return [
        _bar_detail(bars.loc[index], index, full, entry) for index in sorted(indices)
    ]


def _active_rows(bars: pd.DataFrame, trade: SharedPortfolioTrade) -> pd.Series:
    entry = pd.Timestamp(trade.entry_time_utc)
    exit_at = pd.Timestamp(trade.exit_time_utc)
    return bars.index.to_series().lt(exit_at) & (bars.index + _INTERVAL > entry)


def _bar_detail(
    row: pd.Series,
    index: pd.Timestamp,
    full: pd.Series,
    entry: pd.Series,
) -> dict[str, object]:
    return {
        "bar_open_utc": index.isoformat(),
        "entry_slice_unresolved": not bool(entry.loc[index]),
        "full_mark_path_unresolved": not bool(full.loc[index]),
        "mark_snapshot_count": int(row["mark_snapshot_count"]),
        "maximum_mark_interval_ms": float(row["maximum_mark_interval_ms"]),
        "entry_mark_snapshot_count": int(row["entry_mark_snapshot_count"]),
        "entry_maximum_mark_interval_ms": float(row["entry_maximum_mark_interval_ms"]),
    }


def _lifecycle_key(trade: SharedPortfolioTrade) -> str:
    return (
        f"{trade.direction}|{trade.signal_time_utc}|"
        f"{trade.entry_time_utc}|{trade.exit_time_utc}"
    )
