"""Chronological orchestration for the frozen BTC trend-pullback replay."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict

import pandas as pd

from hypervector.research.btc_sweep_primary_relaxation_historical import (
    BtcSweepHistoricalPartition,
    frozen_btc_sweep_historical_partitions,
)
from hypervector.research.btc_sweep_primary_relaxation_replay import (
    evaluate_btc_sweep_primary_relaxation,
)
from hypervector.research.btc_trend_pullback_experiment import (
    BtcTrendPullbackCell,
    BtcTrendPullbackExperimentResult,
    build_btc_trend_pullback_report,
)
from hypervector.research.btc_trend_pullback_reacceleration_replay import (
    evaluate_btc_trend_pullback_reacceleration,
)
from hypervector.research.btc_trend_pullback_route_competition import (
    BtcRouteCase,
    BtcRouteComparison,
    BtcRouteEvent,
    compare_btc_route_cases,
    evaluate_btc_route_case,
    identity_unavailable,
)


BtcTrendPullbackPartition = BtcSweepHistoricalPartition
_PARTITION_NAMES = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {"nominal": 2.0, "stress": 5.0}
_WARMUP = pd.Timedelta(hours=55)
_MINUTE = pd.Timedelta(minutes=1)


def frozen_btc_trend_pullback_partitions() -> tuple[BtcTrendPullbackPartition, ...]:
    """Return the exact preregistered chronological partitions."""
    return frozen_btc_sweep_historical_partitions()


def run_btc_trend_pullback_historical(
    minute_bars: pd.DataFrame,
    partitions: tuple[BtcTrendPullbackPartition, ...] | None = None,
    *,
    hulk_events: tuple[BtcRouteEvent, ...] | None = None,
    hulk_source_identity: dict[str, object] | None = None,
) -> BtcTrendPullbackExperimentResult:
    """Run all partitions and costs without performance aborts."""
    selected = _validated_partitions(
        partitions or frozen_btc_trend_pullback_partitions()
    )
    _validate_source_coverage(minute_bars, selected)
    cells: list[BtcTrendPullbackCell] = []
    for partition in selected:
        segment = _partition_bars(minute_bars, partition)
        days = (partition.end_utc - partition.start_utc).total_seconds() / 86_400.0
        cells.extend(_partition_cells(segment, partition, days))
    standalone = build_btc_trend_pullback_report(cells)
    route, route_trades = _route_competition(
        minute_bars,
        selected,
        cells,
        hulk_events,
        hulk_source_identity,
    )
    report = {**standalone.report, "route_competition": route}
    report["acceptance"] = _acceptance_with_routes(report["acceptance"], route)
    return BtcTrendPullbackExperimentResult(
        report, (*standalone.trade_rows, *route_trades)
    )


def _route_competition(
    bars: pd.DataFrame,
    partitions: tuple[BtcTrendPullbackPartition, ...],
    cells: list[BtcTrendPullbackCell],
    hulk_events: tuple[BtcRouteEvent, ...] | None,
    source_identity: dict[str, object] | None,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    if hulk_events is None or source_identity is None:
        unavailable = identity_unavailable(
            ("hulk_expansion_short_robust_v3", "hulk_expansion_short_tuned_v2")
        )
        return {**unavailable, "execution_authority": "none"}, ()
    comparisons: list[dict[str, object]] = []
    v51_rows: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    partition_by_name = {value.name: value for value in partitions}
    for cell in cells:
        partition = partition_by_name[cell.partition]
        segment = _partition_bars(bars, partition)
        produced = _route_cell(segment, partition, cell, hulk_events)
        comparisons.extend(produced[0])
        v51_rows.append(produced[1])
        trades.extend(produced[2])
    return (
        {
            "status": "complete",
            "execution_authority": "none",
            "hulk_source_identity": source_identity,
            "comparison_rows": comparisons,
            "v51_baseline_rows": v51_rows,
        },
        tuple(trades),
    )


def _route_cell(
    bars: pd.DataFrame,
    partition: BtcTrendPullbackPartition,
    cell: BtcTrendPullbackCell,
    hulk_events: tuple[BtcRouteEvent, ...],
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]]]:
    sweep = _fixed_events(
        "liquidity_sweep_long_1h_stop60_target60_v2",
        10,
        cell.control_signal_times_utc,
    )
    candidate = _fixed_events(
        "btc_trend_pullback_reacceleration_long_v1",
        9,
        cell.candidate.signal_times_utc,
    )
    hulk = _partition_events(hulk_events, partition)
    robust = tuple(
        value for value in hulk if value.strategy_id == "hulk_expansion_short_robust_v3"
    )
    long_case = compare_btc_route_cases(
        bars, sweep, candidate, _SCENARIOS[cell.scenario]
    )
    current = compare_btc_route_cases(
        bars, (*hulk, *sweep), candidate, _SCENARIOS[cell.scenario]
    )
    v51 = evaluate_btc_route_case(bars, (*robust, *sweep), _SCENARIOS[cell.scenario])
    identity = {"partition": cell.partition, "scenario": cell.scenario}
    rows = [
        _comparison_row(identity, "candidate_plus_sweep_control", long_case),
        _comparison_row(identity, "candidate_plus_current_v58_btc_routes", current),
    ]
    v51_row = {**identity, "scope": "exact_v51_btc_routes", **_case_summary(v51)}
    trades = _route_trade_rows(identity, "long_routes", long_case)
    trades.extend(_route_trade_rows(identity, "current_v58", current))
    trades.extend(_case_trade_rows(identity, "v51", "baseline", v51))
    return rows, v51_row, trades


def _comparison_row(
    identity: dict[str, str], scope: str, value: BtcRouteComparison
) -> dict[str, object]:
    return {
        **identity,
        "scope": scope,
        "baseline": _case_summary(value.baseline),
        "candidate": _case_summary(value.candidate),
        "incremental_net_pnl_usd": value.incremental_net_pnl_usd,
        "incremental_maximum_drawdown_pct": (value.incremental_maximum_drawdown_pct),
    }


def _case_summary(value: BtcRouteCase) -> dict[str, object]:
    report = value.report
    winner = max(
        (trade.net_pnl_usd for trade in report.trades if trade.net_pnl_usd > 0.0),
        default=None,
    )
    fills = Counter(trade.signal_name for trade in report.trades)
    return {
        "raw_events": value.raw_events,
        "scheduled_events": value.scheduled_events,
        "completed_trades": report.completed_trades,
        "net_pnl_usd": report.net_pnl_usd,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "fees_usd": report.total_fees_usd,
        "funding_usd": report.funding_cashflow_usd,
        "largest_winner_usd": winner,
        "net_pnl_excluding_largest_winner_usd": (
            report.net_pnl_usd - winner if winner is not None else report.net_pnl_usd
        ),
        "route_fills": dict(sorted(fills.items())),
        "same_minute_priority_displacements": (
            value.same_minute_priority_displacements
        ),
        "occupancy_displacements": value.occupancy_displacements,
        "maximum_concurrent_positions": report.maximum_concurrent_positions,
        "liquidations": report.liquidations,
    }


def _fixed_events(
    strategy_id: str, priority: int, signal_times: tuple[str, ...]
) -> tuple[BtcRouteEvent, ...]:
    return tuple(
        BtcRouteEvent.fixed(strategy_id, "long", priority, pd.Timestamp(timestamp))
        for timestamp in signal_times
    )


def _partition_events(
    events: tuple[BtcRouteEvent, ...], partition: BtcTrendPullbackPartition
) -> tuple[BtcRouteEvent, ...]:
    return tuple(
        event
        for event in events
        if partition.start_utc <= event.signal_time < partition.end_utc
    )


def _route_trade_rows(
    identity: dict[str, str], scope: str, value: BtcRouteComparison
) -> list[dict[str, object]]:
    rows = _case_trade_rows(identity, scope, "baseline", value.baseline)
    rows.extend(_case_trade_rows(identity, scope, "candidate", value.candidate))
    return rows


def _case_trade_rows(
    identity: dict[str, str], scope: str, case: str, value: BtcRouteCase
) -> list[dict[str, object]]:
    return [
        {
            **identity,
            "arm": "route_competition",
            "scope": scope,
            "case": case,
            **asdict(trade),
        }
        for trade in value.report.trades
    ]


def _acceptance_with_routes(
    standalone: object, route: dict[str, object]
) -> dict[str, object]:
    if not isinstance(standalone, dict):
        raise ValueError("BTC standalone acceptance must be an object")
    failures = list(standalone["failed_checks"])
    if route.get("status") != "complete":
        failures.append("shared_current_v58_route_identity_unavailable")
    else:
        _check_shared_current_rows(route["comparison_rows"], failures)
    return {
        **standalone,
        "candidate_supported": not failures,
        "failed_checks": failures,
    }


def _check_shared_current_rows(rows: object, failures: list[str]) -> None:
    if not isinstance(rows, list):
        raise ValueError("BTC shared route rows must be a list")
    selected = [
        row
        for row in rows
        if row["scope"] == "candidate_plus_current_v58_btc_routes"
        and row["partition"] in {"validation", "pseudo_holdout"}
    ]
    if len(selected) != 4:
        raise ValueError("BTC shared current V58 comparison is incomplete")
    for row in selected:
        prefix = f"{row['partition']}_{row['scenario']}_shared_current_v58"
        if float(row["incremental_net_pnl_usd"]) <= 0.0:
            failures.append(f"{prefix}_positive_incremental_net")
        if float(row["incremental_maximum_drawdown_pct"]) < 0.0:
            failures.append(f"{prefix}_no_worse_drawdown")


def _partition_cells(
    bars: pd.DataFrame,
    partition: BtcTrendPullbackPartition,
    days: float,
) -> list[BtcTrendPullbackCell]:
    cells: list[BtcTrendPullbackCell] = []
    for scenario, slippage in _SCENARIOS.items():
        candidate = evaluate_btc_trend_pullback_reacceleration(
            bars,
            slippage,
            entry_start_utc=partition.start_utc,
            entry_end_utc=partition.end_utc,
        )
        sweep = evaluate_btc_sweep_primary_relaxation(
            bars,
            slippage,
            entry_start_utc=partition.start_utc,
            entry_end_utc=partition.end_utc,
        )
        cells.append(
            BtcTrendPullbackCell(
                partition.name,
                scenario,
                days,
                candidate,
                sweep.control,
                sweep.control_signal_count,
                sweep.control_signal_times_utc,
            )
        )
    return cells


def _validated_partitions(
    partitions: tuple[BtcTrendPullbackPartition, ...],
) -> tuple[BtcTrendPullbackPartition, ...]:
    if tuple(partition.name for partition in partitions) != _PARTITION_NAMES:
        raise ValueError("BTC trend-pullback partition identity drifted")
    for prior, current in zip(partitions, partitions[1:]):
        if prior.end_utc != current.start_utc:
            raise ValueError("BTC trend-pullback partitions must be contiguous")
    return partitions


def _validate_source_coverage(
    bars: pd.DataFrame,
    partitions: tuple[BtcTrendPullbackPartition, ...],
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC trend-pullback source requires an aware index")
    expected_last = partitions[-1].end_utc - _MINUTE
    if bars.empty or bars.index.min() > partitions[0].start_utc:
        raise ValueError("BTC trend-pullback source start is incomplete")
    if bars.index.max() < expected_last:
        raise ValueError("BTC trend-pullback source end is incomplete")


def _partition_bars(
    bars: pd.DataFrame, partition: BtcTrendPullbackPartition
) -> pd.DataFrame:
    lower = max(bars.index.min(), partition.start_utc - _WARMUP)
    selected = bars.loc[(bars.index >= lower) & (bars.index < partition.end_utc)].copy()
    if selected.empty:
        raise ValueError(f"BTC trend-pullback partition is empty: {partition.name}")
    return selected
