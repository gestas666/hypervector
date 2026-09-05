"""Immutable result assembly for the crypto bull-participation experiment."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Literal

from hypervector.research.crypto_bull_participation_models import (
    CryptoBullPortfolioReport,
    CryptoBullTrade,
)

PartitionName = Literal["development", "validation", "pseudo_holdout"]
ScenarioName = Literal["nominal", "stress"]

_PARTITIONS: tuple[PartitionName, ...] = (
    "development",
    "validation",
    "pseudo_holdout",
)
_SCENARIOS: tuple[ScenarioName, ...] = ("nominal", "stress")


@dataclass(frozen=True)
class CryptoBullExperimentCell:
    """Candidate and continuous-long results for one registered cell."""

    partition: PartitionName
    scenario: ScenarioName
    candidate: CryptoBullPortfolioReport
    continuous_long: CryptoBullPortfolioReport


@dataclass(frozen=True)
class CryptoBullExperimentResult:
    """JSON-ready report and complete candidate trade sidecar rows."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_crypto_bull_experiment_report(
    cells: list[CryptoBullExperimentCell],
) -> CryptoBullExperimentResult:
    """Publish all registered cells and evaluate frozen support criteria."""
    cell_map = _validated_cell_map(cells)
    rows = _summary_rows(cell_map)
    failed = _failed_support_checks(cell_map)
    report: dict[str, object] = {
        "schema_version": "v58_crypto_bull_participation_result_v1",
        "authority": {
            "execution_authority": "none",
            "automatic_live_change": False,
            "orders_supported": False,
        },
        "integrity": {
            "registered_cell_count": len(cell_map),
            "performance_abort_applied": False,
            "opened_partitions_disclosed": True,
        },
        "summary_rows": rows,
        "acceptance": {
            "historical_support": not failed,
            "failed_checks": list(failed),
        },
    }
    return CryptoBullExperimentResult(
        report=report,
        trade_rows=_candidate_trade_rows(cell_map),
    )


def _validated_cell_map(
    cells: list[CryptoBullExperimentCell],
) -> dict[tuple[PartitionName, ScenarioName], CryptoBullExperimentCell]:
    expected = {
        (partition, scenario) for partition in _PARTITIONS for scenario in _SCENARIOS
    }
    output = {(cell.partition, cell.scenario): cell for cell in cells}
    if len(output) != len(cells):
        raise ValueError("experiment cells contain duplicate partition/scenario keys")
    if set(output) != expected:
        raise ValueError("experiment requires exactly the six registered cells")
    return output


def _summary_rows(
    cells: dict[tuple[PartitionName, ScenarioName], CryptoBullExperimentCell],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for partition in _PARTITIONS:
        for scenario in _SCENARIOS:
            cell = cells[(partition, scenario)]
            rows.append(_summarize(partition, scenario, "candidate", cell.candidate))
            rows.append(
                _summarize(
                    partition,
                    scenario,
                    "continuous_long",
                    cell.continuous_long,
                )
            )
            rows.append(_cash_summary(partition, scenario, cell.candidate))
    return rows


def _summarize(
    partition: PartitionName,
    scenario: ScenarioName,
    strategy: str,
    report: CryptoBullPortfolioReport,
) -> dict[str, object]:
    trades = report.trades
    gross_wins = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    gross_losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    largest_winner = max((trade.net_pnl_usd for trade in trades), default=0.0)
    return {
        "partition": partition,
        "scenario": scenario,
        "strategy": strategy,
        "completed_trades": len(trades),
        "wins": sum(trade.net_pnl_usd > 0.0 for trade in trades),
        "losses": sum(trade.net_pnl_usd <= 0.0 for trade in trades),
        "net_pnl_usd": report.net_pnl_usd,
        "profit_factor": _profit_factor(gross_wins, gross_losses),
        "net_pnl_excluding_largest_winner_usd": report.net_pnl_usd
        - max(largest_winner, 0.0),
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "fees_usd": sum(trade.fees_usd for trade in trades),
        "funding_usd": sum(trade.funding_cashflow_usd for trade in trades),
        "slippage_cost_usd": sum(trade.slippage_cost_usd for trade in trades),
        "turnover_usd": report.turnover_usd,
        "median_holding_hours": median(
            [trade.holding_minutes / 60.0 for trade in trades]
        )
        if trades
        else 0.0,
        "maximum_holding_hours": max(
            (trade.holding_minutes / 60.0 for trade in trades), default=0.0
        ),
        "exposure_time_pct": 100.0 * report.exposure_minutes / report.available_minutes,
        "maximum_concurrent_positions": report.maximum_concurrent_positions,
        "maximum_margin_fraction": report.maximum_margin_fraction,
        "simultaneous_stop_wave_loss_usd": report.simultaneous_stop_wave_loss_usd,
        "liquidations": sum(trade.exit_reason == "liquidation" for trade in trades),
        "by_symbol_economics": _group_economics(trades, "symbol"),
        "by_exit_reason_economics": _group_economics(trades, "exit_reason"),
        "monthly_economics": _monthly_economics(trades),
        "entry_cadence": _entry_cadence(trades),
    }


def _cash_summary(
    partition: PartitionName,
    scenario: ScenarioName,
    reference: CryptoBullPortfolioReport,
) -> dict[str, object]:
    empty = CryptoBullPortfolioReport(
        initial_equity_usd=reference.initial_equity_usd,
        final_equity_usd=reference.initial_equity_usd,
        net_pnl_usd=0.0,
        maximum_drawdown_pct=0.0,
        maximum_concurrent_positions=0,
        maximum_margin_fraction=0.0,
        simultaneous_stop_wave_loss_usd=0.0,
        turnover_usd=0.0,
        exposure_minutes=0,
        available_minutes=reference.available_minutes,
        trades=(),
    )
    return _summarize(partition, scenario, "no_action", empty)


def _failed_support_checks(
    cells: dict[tuple[PartitionName, ScenarioName], CryptoBullExperimentCell],
) -> tuple[str, ...]:
    failures: list[str] = []
    for partition in ("validation", "pseudo_holdout"):
        for scenario in _SCENARIOS:
            report = cells[(partition, scenario)].candidate
            prefix = f"{partition}_{scenario}"
            failures.extend(_cell_failures(prefix, report))
    return tuple(failures)


def _cell_failures(prefix: str, report: CryptoBullPortfolioReport) -> list[str]:
    summary = _summarize("validation", "nominal", "candidate", report)
    failures: list[str] = []
    if report.net_pnl_usd <= 0.0:
        failures.append(f"{prefix}_net_not_positive")
    if float(summary["profit_factor"]) <= 1.0:
        failures.append(f"{prefix}_profit_factor_not_above_one")
    if float(summary["net_pnl_excluding_largest_winner_usd"]) <= 0.0:
        failures.append(f"{prefix}_ex_largest_not_positive")
    symbol_pnl = _pnl_by_symbol(report.trades)
    if sum(value > 0.0 for value in symbol_pnl.values()) < 3:
        failures.append(f"{prefix}_fewer_than_three_positive_symbols")
    if any(trade.exit_reason == "liquidation" for trade in report.trades):
        failures.append(f"{prefix}_liquidation")
    if report.maximum_drawdown_pct < -10.0:
        failures.append(f"{prefix}_drawdown_worse_than_ten_percent")
    if len(report.trades) < 12:
        failures.append(f"{prefix}_fewer_than_twelve_trades")
    return failures


def _profit_factor(gross_wins: float, gross_losses: float) -> float:
    if gross_losses > 0.0:
        return gross_wins / gross_losses
    return float("inf") if gross_wins > 0.0 else 0.0


def _pnl_by_symbol(trades: tuple[CryptoBullTrade, ...]) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in trades:
        output[trade.symbol] = output.get(trade.symbol, 0.0) + trade.net_pnl_usd
    return output


def _group_economics(
    trades: tuple[CryptoBullTrade, ...], field: Literal["symbol", "exit_reason"]
) -> list[dict[str, object]]:
    grouped: dict[str, list[CryptoBullTrade]] = {}
    for trade in trades:
        grouped.setdefault(str(getattr(trade, field)), []).append(trade)
    return [
        {
            field: key,
            "trades": len(values),
            "net_pnl_usd": sum(trade.net_pnl_usd for trade in values),
        }
        for key, values in sorted(grouped.items())
    ]


def _monthly_economics(trades: tuple[CryptoBullTrade, ...]) -> list[dict[str, object]]:
    grouped: dict[str, list[CryptoBullTrade]] = {}
    for trade in trades:
        grouped.setdefault(trade.exit_time_utc[:7], []).append(trade)
    return [
        {
            "month_utc": month,
            "trades": len(values),
            "net_pnl_usd": sum(trade.net_pnl_usd for trade in values),
        }
        for month, values in sorted(grouped.items())
    ]


def _entry_cadence(trades: tuple[CryptoBullTrade, ...]) -> dict[str, object]:
    ordered = sorted(trade.entry_time_utc for trade in trades)
    if len(ordered) < 2:
        return {"entry_count": len(ordered), "median_interarrival_hours": None}
    from pandas import Timestamp

    timestamps = [Timestamp(value) for value in ordered]
    intervals = [
        (current - previous).total_seconds() / 3_600.0
        for previous, current in zip(timestamps, timestamps[1:])
    ]
    return {
        "entry_count": len(ordered),
        "median_interarrival_hours": median(intervals),
    }


def _candidate_trade_rows(
    cells: dict[tuple[PartitionName, ScenarioName], CryptoBullExperimentCell],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for partition in _PARTITIONS:
        for scenario in _SCENARIOS:
            for trade in cells[(partition, scenario)].candidate.trades:
                rows.append(
                    {"partition": partition, "scenario": scenario, **trade.to_dict()}
                )
    return tuple(rows)
