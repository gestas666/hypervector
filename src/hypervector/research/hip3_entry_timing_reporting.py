"""Honest reporting for HIP-3 entry-timing lifecycle challengers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from hypervector.research.hip3_entry_timing import Hip3EntryTimingMode
from hypervector.research.hip3_entry_timing_evaluation import Hip3EntryTimingCell
from hypervector.research.hip3_swing_transfer import Hip3TransferWindows
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)
from hypervector.research.swing_ha_signals import EntryMode


def build_hip3_entry_timing_report(
    *,
    strategy_id: str,
    provider_entry_mode: EntryMode,
    cells: Sequence[Hip3EntryTimingCell],
    windows: Hip3TransferWindows,
) -> dict[str, object]:
    """Build a complete report with no execution or automatic-promotion authority."""
    if not strategy_id.strip():
        raise ValueError("HIP-3 timing strategy_id must be non-empty")
    if provider_entry_mode not in {"state", "onset"}:
        raise ValueError("HIP-3 timing provider entry mode must be state or onset")
    indexed, symbols = _index_cells(cells)
    return {
        "strategy_id": strategy_id,
        "provider_entry_mode": provider_entry_mode,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "timing_contract": _timing_contract(),
        "windows": {
            "development_start_utc": windows.development_start_utc.isoformat(),
            "development_end_utc": windows.development_end_utc.isoformat(),
            "validation_end_utc": windows.validation_end_utc.isoformat(),
            "holdout_end_utc": windows.holdout_end_utc.isoformat(),
        },
        "results": _results(indexed, symbols),
        "aggregates": _aggregates(indexed),
        "holdout": {
            "status": "sealed_not_evaluated",
            "start_utc": windows.validation_end_utc.isoformat(),
            "end_utc": windows.holdout_end_utc.isoformat(),
            "metrics_accessed": False,
        },
        "limitations": _limitations(),
    }


def timing_trade_records(
    strategy_id: str,
    cells: Sequence[Hip3EntryTimingCell],
) -> list[dict[str, object]]:
    """Return attributed after-cost trades for an immutable sidecar."""
    return [
        {
            "strategy_id": strategy_id,
            "symbol": cell.symbol,
            "phase": cell.phase,
            "friction": cell.friction,
            "timing_mode": cell.timing_mode.value,
            **trade.__dict__,
        }
        for cell in cells
        for trade in cell.report.trades
    ]


def _index_cells(
    cells: Sequence[Hip3EntryTimingCell],
) -> tuple[
    Mapping[tuple[str, str, Hip3EntryTimingMode, str], Hip3EntryTimingCell],
    tuple[str, ...],
]:
    symbols = tuple(sorted({cell.symbol for cell in cells}))
    if not symbols:
        raise ValueError("HIP-3 timing report requires cells")
    indexed = {
        (cell.phase, cell.friction, cell.timing_mode, cell.symbol): cell
        for cell in cells
    }
    expected = {
        (phase, friction, mode, symbol)
        for phase in ("development", "validation")
        for friction in ("nominal", "stress")
        for mode in Hip3EntryTimingMode
        for symbol in symbols
    }
    if len(indexed) != len(cells) or set(indexed) != expected:
        raise ValueError("HIP-3 timing cells lack exact phase/friction/mode coverage")
    return indexed, symbols


def _results(
    indexed: Mapping[tuple[str, str, Hip3EntryTimingMode, str], Hip3EntryTimingCell],
    symbols: tuple[str, ...],
) -> dict[str, object]:
    return {
        phase: {
            friction: {
                mode.value: {
                    symbol: _cell_summary(indexed[(phase, friction, mode, symbol)])
                    for symbol in symbols
                }
                for mode in Hip3EntryTimingMode
            }
            for friction in ("nominal", "stress")
        }
        for phase in ("development", "validation")
    }


def _cell_summary(cell: Hip3EntryTimingCell) -> dict[str, object]:
    report = cell.report
    capture = (
        cell.timing_entry_signals / cell.anchor_signals if cell.anchor_signals else None
    )
    return {
        **_report_metrics(report),
        "provider_entry_signals": cell.provider_entry_signals,
        "anchor_signals": cell.anchor_signals,
        "timing_entry_signals": cell.timing_entry_signals,
        "missed_anchor_signals": max(
            cell.anchor_signals - cell.timing_entry_signals,
            0,
        ),
        "signal_capture_ratio": capture,
        "tail_suppressed_entries": cell.tail_suppressed_entries,
        "gap_crossing_trades": cell.gap_crossing_trades,
        "directions": {
            side: _trade_group(
                [trade for trade in report.trades if trade.direction == side]
            )
            for side in ("long", "short")
        },
        "exit_reasons": dict(Counter(trade.exit_reason for trade in report.trades)),
        "concentration": _concentration(report.trades),
        "execution_authority": "none",
    }


def _report_metrics(report: SharedPortfolioReport) -> dict[str, object]:
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_pnl_usd": report.net_pnl_usd,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "gross_profit_usd": report.gross_profit_usd,
        "gross_loss_usd": report.gross_loss_usd,
        "total_fees_usd": report.total_fees_usd,
        "funding_cashflow_usd": report.funding_cashflow_usd,
        "liquidations": report.liquidations,
        "forced_end_exits": report.forced_end_exits,
    }


def _trade_group(trades: Sequence[SharedPortfolioTrade]) -> dict[str, object]:
    gross_profit = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    gross_loss = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    return {
        "trades": len(trades),
        "wins": sum(trade.net_pnl_usd > 0.0 for trade in trades),
        "losses": sum(trade.net_pnl_usd < 0.0 for trade in trades),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in trades),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
    }


def _concentration(trades: Sequence[SharedPortfolioTrade]) -> dict[str, object]:
    profits = [trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0]
    losses = [-trade.net_pnl_usd for trade in trades if trade.net_pnl_usd < 0.0]
    largest = max(profits, default=0.0)
    gross_profit = sum(profits)
    gross_profit_ex_largest = max(gross_profit - largest, 0.0)
    gross_loss = sum(losses)
    return {
        "largest_winner_usd": largest,
        "largest_winner_share_of_gross_profit": (
            largest / gross_profit if gross_profit else None
        ),
        "net_pnl_ex_largest_winner_usd": gross_profit_ex_largest - gross_loss,
        "profit_factor_ex_largest_winner": (
            gross_profit_ex_largest / gross_loss if gross_loss else None
        ),
    }


def _aggregates(
    indexed: Mapping[tuple[str, str, Hip3EntryTimingMode, str], Hip3EntryTimingCell],
) -> dict[str, object]:
    return {
        phase: {
            friction: {
                mode.value: _aggregate(
                    [
                        cell.report
                        for (
                            cell_phase,
                            cell_friction,
                            cell_mode,
                            _,
                        ), cell in indexed.items()
                        if (cell_phase, cell_friction, cell_mode)
                        == (phase, friction, mode)
                    ]
                )
                for mode in Hip3EntryTimingMode
            }
            for friction in ("nominal", "stress")
        }
        for phase in ("development", "validation")
    }


def _aggregate(reports: Sequence[SharedPortfolioReport]) -> dict[str, object]:
    trades = tuple(trade for report in reports for trade in report.trades)
    gross_profit = sum(report.gross_profit_usd for report in reports)
    gross_loss = sum(report.gross_loss_usd for report in reports)
    return {
        "completed_trades": sum(report.completed_trades for report in reports),
        "net_pnl_usd": sum(report.net_pnl_usd for report in reports),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "worst_independent_asset_drawdown_pct": min(
            report.maximum_drawdown_pct for report in reports
        ),
        "concentration": _concentration(trades),
    }


def _timing_contract() -> dict[str, object]:
    return {
        "provider_exact": "unchanged production-provider entry rows",
        "alignment_onset": "first eligible row of each provider state episode",
        "next_bar_confirmation": (
            "one completed bar after onset only while native alignment persists"
        ),
        "first_fast_ema_pullback": (
            "first later completed bar touching fast EMA while alignment persists"
        ),
        "fill_clock": "signal_on_completed_bar_then_next_bar_open",
        "comparison_scope": "development_and_validation_only",
    }


def _limitations() -> list[str]:
    return [
        "Results are independent-asset 15-minute approximations, not shared-router replay.",
        "Fast-EMA touches use completed raw OHLC while native identity uses HA signals.",
        "Visible-book and latency friction are modeled from archived measurements.",
        "The sealed holdout is not read and no arm has automatic promotion authority.",
    ]
