"""Honest reporting for the v25 HIP-3 15-minute lifecycle approximation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleCell,
    Hip3DeployedLifecycleSpec,
)
from hypervector.research.hip3_swing_transfer import Hip3TransferWindows
from hypervector.research.shared_portfolio_models import SharedPortfolioReport
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

Record = Mapping[str, object]
Recipe = SwingHaSignalConfig | Hip3BreakoutPressureConfig


def deployed_lifecycle_case_report(
    *,
    strategy_id: str,
    source_report: Record,
    source_evidence: Record,
    production_recipe: Recipe,
    cells: Sequence[Hip3DeployedLifecycleCell],
    windows: Hip3TransferWindows,
    spec: Hip3DeployedLifecycleSpec | None = None,
) -> dict[str, object]:
    """Compare prior lifecycle evidence with a production-recipe bar diagnostic."""
    lifecycle = spec or Hip3DeployedLifecycleSpec()
    recipe = asdict(production_recipe)
    selected = _selected_recipe(source_report)
    if selected != recipe:
        raise ValueError("source selected config does not match production recipe")
    _validate_source_contract(source_report)
    symbols = _text_list(source_report.get("symbols"), "source symbols")
    indexed = _index_cells(cells, symbols)
    results = _result_tree(indexed, symbols)
    return {
        "strategy_id": strategy_id,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "source_report": dict(source_evidence),
        "recipe_parity": {
            "exact_match": True,
            "source_selected": selected,
            "production_recipe": recipe,
        },
        "bar_diagnostic_contract": _contract(lifecycle),
        "windows": _windows(windows),
        "results": results,
        "aggregates": _aggregates(indexed),
        "validation_comparison": _validation_comparison(
            source_report,
            indexed,
            symbols,
        ),
        "holdout": {
            "status": "sealed_not_evaluated",
            "start_utc": windows.validation_end_utc.isoformat(),
            "end_utc": windows.holdout_end_utc.isoformat(),
            "metrics_accessed": False,
        },
        "limitations": _limitations(),
    }


def lifecycle_trade_records(
    strategy_id: str,
    cells: Sequence[Hip3DeployedLifecycleCell],
) -> list[dict[str, object]]:
    """Return attributed trade rows for an immutable sidecar."""
    return [
        {
            "strategy_id": strategy_id,
            "symbol": cell.symbol,
            "phase": cell.phase,
            "friction": cell.friction,
            **asdict(trade),
        }
        for cell in cells
        for trade in cell.report.trades
    ]


def _selected_recipe(source: Record) -> dict[str, object]:
    value = source.get("selected_frozen_config", source.get("selected_config"))
    return dict(_mapping(value, "source selected config"))


def _validate_source_contract(source: Record) -> None:
    if source.get("execution_authority") != "none":
        raise ValueError("source report must have no execution authority")
    holdout = _mapping(source.get("holdout"), "source holdout")
    if (
        holdout.get("status") != "sealed_not_evaluated"
        or holdout.get("metrics_accessed") is not False
    ):
        raise ValueError("source holdout must remain sealed and unread")


def _index_cells(
    cells: Sequence[Hip3DeployedLifecycleCell],
    symbols: tuple[str, ...],
) -> dict[tuple[str, str, str], Hip3DeployedLifecycleCell]:
    indexed = {(cell.phase, cell.friction, cell.symbol): cell for cell in cells}
    expected = {
        (phase, friction, symbol)
        for phase in ("development", "validation")
        for friction in ("nominal", "stress")
        for symbol in symbols
    }
    if len(indexed) != len(cells) or set(indexed) != expected:
        raise ValueError("lifecycle cells do not cover each phase/friction/symbol once")
    return indexed


def _result_tree(
    indexed: Mapping[tuple[str, str, str], Hip3DeployedLifecycleCell],
    symbols: tuple[str, ...],
) -> dict[str, object]:
    return {
        phase: {
            friction: {
                symbol: _cell_summary(indexed[(phase, friction, symbol)])
                for symbol in symbols
            }
            for friction in ("nominal", "stress")
        }
        for phase in ("development", "validation")
    }


def _cell_summary(cell: Hip3DeployedLifecycleCell) -> dict[str, object]:
    report = cell.report
    exits = Counter(trade.exit_reason for trade in report.trades)
    directions = {
        side: {
            "trades": sum(trade.direction == side for trade in report.trades),
            "net_pnl_usd": sum(
                trade.net_pnl_usd for trade in report.trades if trade.direction == side
            ),
        }
        for side in ("long", "short")
    }
    return {
        **_report_metrics(report),
        "exit_reasons": dict(sorted(exits.items())),
        "directions": directions,
        "tail_suppressed_entries": cell.tail_suppressed_entries,
        "gap_crossing_trades": cell.gap_crossing_trades,
        "bar_timer_alignment": (
            "regular_bar_approximation"
            if cell.gap_crossing_trades == 0 and report.forced_end_exits == 0
            else "not_aligned"
        ),
        "execution_authority": "none",
    }


def _report_metrics(report: SharedPortfolioReport) -> dict[str, object]:
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_pnl_usd": report.net_pnl_usd,
        "return_pct": report.return_pct,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "gross_profit_usd": report.gross_profit_usd,
        "gross_loss_usd": report.gross_loss_usd,
        "total_fees_usd": report.total_fees_usd,
        "funding_cashflow_usd": report.funding_cashflow_usd,
        "liquidations": report.liquidations,
        "forced_end_exits": report.forced_end_exits,
    }


def _aggregates(
    indexed: Mapping[tuple[str, str, str], Hip3DeployedLifecycleCell],
) -> dict[str, object]:
    return {
        phase: {
            friction: _aggregate(
                [
                    cell.report
                    for (cell_phase, cell_friction, _), cell in indexed.items()
                    if cell_phase == phase and cell_friction == friction
                ]
            )
            for friction in ("nominal", "stress")
        }
        for phase in ("development", "validation")
    }


def _aggregate(reports: Sequence[SharedPortfolioReport]) -> dict[str, object]:
    gross_profit = sum(report.gross_profit_usd for report in reports)
    gross_loss = sum(report.gross_loss_usd for report in reports)
    return {
        "completed_trades": sum(report.completed_trades for report in reports),
        "wins": sum(report.wins for report in reports),
        "losses": sum(report.losses for report in reports),
        "net_pnl_usd": sum(report.net_pnl_usd for report in reports),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "total_fees_usd": sum(report.total_fees_usd for report in reports),
        "funding_cashflow_usd": sum(report.funding_cashflow_usd for report in reports),
        "liquidations": sum(report.liquidations for report in reports),
        "worst_independent_asset_drawdown_pct": min(
            report.maximum_drawdown_pct for report in reports
        ),
    }


def _validation_comparison(
    source: Record,
    indexed: Mapping[tuple[str, str, str], Hip3DeployedLifecycleCell],
    symbols: tuple[str, ...],
) -> dict[str, object]:
    validation = _mapping(source.get("validation"), "source validation")
    return {
        friction: {
            symbol: _comparison(
                _prior_row(validation, friction, symbol),
                indexed[("validation", friction, symbol)].report,
            )
            for symbol in symbols
        }
        for friction in ("nominal", "stress")
    }


def _prior_row(validation: Record, friction: str, symbol: str) -> Record:
    rows = _record_list(validation.get(friction), f"source {friction} validation")
    matches = [row for row in rows if row.get("symbol") == symbol]
    if len(matches) != 1:
        raise ValueError(f"source validation missing exact {friction}/{symbol} row")
    return matches[0]


def _comparison(prior: Record, deployed: SharedPortfolioReport) -> dict[str, object]:
    prior_net = _number(prior.get("net_pnl_usd"), "prior net_pnl_usd")
    prior_trades = _integer(prior.get("completed_trades"), "prior completed_trades")
    current = _report_metrics(deployed)
    return {
        "prior_modeled_lifecycle": {
            "completed_trades": prior_trades,
            "net_pnl_usd": prior_net,
            "profit_factor": prior.get("profit_factor"),
        },
        "deployed_lifecycle": current,
        "delta": {
            "completed_trades": deployed.completed_trades - prior_trades,
            "net_pnl_usd": deployed.net_pnl_usd - prior_net,
        },
    }


def _contract(spec: Hip3DeployedLifecycleSpec) -> dict[str, object]:
    return {
        "scope": "single_provider_independent_asset_15m_approximation",
        "entry_recipe": "exact_live_production_object",
        "entry_liquidity": "historical_next_bar_bbo_plus_modeled_slippage",
        "stop_policy": "fixed_bps",
        "stop_bps": spec.stop_bps,
        "target_policy": "none",
        "maximum_hold_seconds": spec.maximum_hold_seconds,
        "maximum_hold_bars": spec.maximum_hold_bars,
        "signal_exit_policy": spec.signal_exit_policy,
        "signal_exit_columns_ignored": spec.signal_exit_policy == "ignore",
        "signal_exit_max_age_bars": (
            spec.early_exit_max_bars
            if spec.signal_exit_policy == "early_adverse"
            else None
        ),
        "signal_exit_max_mfe_bps": (
            spec.early_exit_max_mfe_bps
            if spec.signal_exit_policy == "early_adverse"
            else None
        ),
        "signal_exit_min_adverse_bps": (
            spec.early_exit_min_adverse_bps
            if spec.signal_exit_policy == "early_adverse"
            else None
        ),
        "opposite_entry_closes": True,
        "same_side_reset_required": False,
        "performance_gate": False,
        "automatic_promotion": False,
        "execution_authority": "none",
    }


def _windows(value: Hip3TransferWindows) -> dict[str, object]:
    return {
        "development_start_utc": value.development_start_utc.isoformat(),
        "development_end_utc": value.development_end_utc.isoformat(),
        "validation_end_utc": value.validation_end_utc.isoformat(),
        "holdout_end_utc": value.holdout_end_utc.isoformat(),
    }


def _limitations() -> list[str]:
    return [
        "not live parity: each provider and asset is evaluated independently",
        "combined Swing/Breakout priority routing and shared account sizing are omitted",
        "15m bar timing approximates the live wall-clock timer and 1m IOC close",
        "gap-crossing trades and forced terminal closes are explicitly reported as unaligned",
        "quantities and stop triggers are not rounded to historical venue increments",
        "midpoint OHLC cannot prove the venue trigger reference or same-bar event order",
        "current fee inputs are sensitivities; GOLD historical fee state is unresolved",
        "the final chronological holdout remains sealed",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _record_list(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} must be an array of non-empty strings")
    return tuple(str(item) for item in value)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value
