"""JSON and trade-sidecar projections for HIP-3 breakout transfer research."""

from __future__ import annotations

from dataclasses import asdict
from typing import Mapping

import pandas as pd

from hypervector.research.hip3_breakout_pressure_transfer import (
    Hip3BreakoutTransferResult,
    Hip3BreakoutTrial,
    Hip3BreakoutValidation,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


def breakout_transfer_report(
    result: Hip3BreakoutTransferResult,
    *,
    source_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Return a complete report without exposing sealed holdout outcomes."""
    if result.holdout_status != "sealed_not_evaluated":
        raise ValueError("HIP-3 breakout holdout must remain sealed")
    selected = next(
        trial for trial in result.trials if trial.config == result.selected_config
    )
    return {
        "schema_version": "hip3_breakout_pressure_transfer_v1",
        "report_only": True,
        "execution_authority": result.execution_authority,
        "model_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "source_evidence": dict(source_evidence),
        "windows": _windows(result),
        "searched_trial_count": len(result.trials),
        "selection_policy": _selection_policy(),
        "development_trials": [
            _trial_summary(trial, result) for trial in result.trials
        ],
        "selected_config": asdict(result.selected_config),
        "selected_development": _trial_summary(selected, result),
        "validation": {
            "nominal": [
                _validation_summary(cell) for cell in result.validation_nominal
            ],
            "stress": [_validation_summary(cell) for cell in result.validation_stress],
        },
        "holdout": {
            "status": result.holdout_status,
            "start_utc": result.windows.validation_end_utc.isoformat(),
            "end_utc": result.windows.holdout_end_utc.isoformat(),
            "metrics_accessed": False,
        },
        "limitations": _limitations(),
    }


def breakout_transfer_trades(result: Hip3BreakoutTransferResult) -> pd.DataFrame:
    """Return selected development and validation lifecycles with provenance."""
    selected = next(
        trial for trial in result.trials if trial.config == result.selected_config
    )
    records: list[dict[str, object]] = []
    for symbol, report in selected.development:
        records.extend(_trade_records(report, "development", symbol, "nominal"))
    for cell in (*result.validation_nominal, *result.validation_stress):
        records.extend(
            _trade_records(cell.report, "validation", cell.symbol, cell.friction)
        )
    return pd.DataFrame.from_records(records)


def _trial_summary(
    trial: Hip3BreakoutTrial,
    result: Hip3BreakoutTransferResult,
) -> dict[str, object]:
    fold_windows = result.windows.development_folds
    fold_count = len(fold_windows)
    folds = [
        {
            "symbol": symbol,
            "fold": position % fold_count,
            "start_utc": fold_windows[position % fold_count][0].isoformat(),
            "end_utc": fold_windows[position % fold_count][1].isoformat(),
            **_report_summary(report),
        }
        for position, (symbol, report) in enumerate(trial.folds)
    ]
    return {
        "config": asdict(trial.config),
        "positive_fold_count": trial.positive_fold_count,
        "active_fold_count": trial.active_fold_count,
        "completed_fold_trades": trial.completed_fold_trades,
        "minimum_fold_net_pnl_usd": trial.minimum_fold_net_pnl,
        "pooled_fold_net_pnl_usd": trial.pooled_fold_net_pnl,
        "development": [
            {"symbol": symbol, **_report_summary(report)}
            for symbol, report in trial.development
        ],
        "folds": folds,
    }


def _validation_summary(cell: Hip3BreakoutValidation) -> dict[str, object]:
    return {
        "symbol": cell.symbol,
        "friction": cell.friction,
        **_report_summary(cell.report),
    }


def _report_summary(report: SharedPortfolioReport) -> dict[str, object]:
    direction_trades = {"long": 0, "short": 0}
    direction_net = {"long": 0.0, "short": 0.0}
    exits: dict[str, int] = {}
    for trade in report.trades:
        direction_trades[trade.direction] += 1
        direction_net[trade.direction] += trade.net_pnl_usd
        exits[trade.exit_reason] = exits.get(trade.exit_reason, 0) + 1
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_pnl_usd": report.net_pnl_usd,
        "return_pct": report.return_pct,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "total_fees_usd": report.total_fees_usd,
        "funding_cashflow_usd": report.funding_cashflow_usd,
        "liquidations": report.liquidations,
        "forced_end_exits": report.forced_end_exits,
        "barrier_invalidated_entries": report.barrier_invalidated_entries,
        "direction_trades": direction_trades,
        "direction_net_pnl_usd": direction_net,
        "exit_reasons": exits,
    }


def _trade_records(
    report: SharedPortfolioReport,
    phase: str,
    symbol: str,
    friction: str,
) -> list[dict[str, object]]:
    return [
        {
            "phase": phase,
            "symbol": symbol,
            "friction": friction,
            **asdict(trade),
        }
        for trade in report.trades
    ]


def _windows(result: Hip3BreakoutTransferResult) -> dict[str, object]:
    windows = result.windows
    return {
        "development_start_utc": windows.development_start_utc.isoformat(),
        "development_end_utc": windows.development_end_utc.isoformat(),
        "validation_end_utc": windows.validation_end_utc.isoformat(),
        "holdout_end_utc": windows.holdout_end_utc.isoformat(),
        "development_folds": [
            {"start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for start, end in windows.development_folds
        ],
    }


def _selection_policy() -> dict[str, object]:
    return {
        "ordering": [
            "positive_fold_count",
            "active_fold_count",
            "minimum_fold_net_pnl_usd",
            "pooled_fold_net_pnl_usd",
            "completed_fold_trades",
        ],
        "uses_development": True,
        "uses_validation": False,
        "uses_holdout": False,
    }


def _limitations() -> list[str]:
    return [
        "L2 midpoint OHLC is a validated price-path proxy, not public-trade OHLC",
        "entries and scheduled exits use observed next-bar executable bid/ask quotes",
        "latency and current HIP-3 fees are explicit; queue position is not inferred",
        "stress adds the measured p99-minus-p90 visible-cost delta per side",
        "each asset is screened independently before any shared-capital portfolio test",
        "the final chronological holdout remains sealed",
    ]
