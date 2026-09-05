"""Reporting and frozen acceptance for the BTC DVOL-VRP long experiment."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from numbers import Real

import pandas as pd

from hypervector.research.btc_dvol_vrp_replay import BtcDvolVrpReplay
from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    no_action_summary,
    summarize_replay_report,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


_PARTITIONS = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {"nominal": (2.0, 0), "stress": (5.0, 5), "delayed": (10.0, 60)}
_PRIMARY = "dvol_vrp_bullish_breakout_long"
_PRICE = "price_only_bullish_breakout_long"
_HIGH = "high_vrp_only_long"
_LOW = "low_vrp_bullish_breakout_long_placebo"
_SWEEP = "v58_liquidity_sweep_long_control"
_NO_ACTION = "no_action"
_ARMS = (_PRIMARY, _PRICE, _HIGH, _LOW, _SWEEP, _NO_ACTION)


@dataclass(frozen=True)
class BtcDvolVrpCell:
    """One frozen partition and execution-scenario replay."""

    partition: str
    scenario: str
    partition_days: float
    replay: BtcDvolVrpReplay

    def __post_init__(self) -> None:
        """Reject partition, scenario, duration, or authority drift."""
        if self.partition not in _PARTITIONS:
            raise ValueError("unknown BTC DVOL-VRP partition")
        expected = _SCENARIOS.get(self.scenario)
        observed = (
            self.replay.slippage_bps_per_taker_side,
            self.replay.extra_delay_minutes,
        )
        if (
            expected is None
            or self.replay.scenario != self.scenario
            or observed != expected
        ):
            raise ValueError("BTC DVOL-VRP scenario drifted")
        if not math.isfinite(self.partition_days) or self.partition_days <= 0.0:
            raise ValueError("BTC DVOL-VRP partition days must be positive")
        if self.replay.execution_authority != "none":
            raise ValueError("BTC DVOL-VRP replay acquired execution authority")


@dataclass(frozen=True)
class BtcDvolVrpExperimentResult:
    """JSON-safe report plus complete active-arm trade evidence."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_btc_dvol_vrp_report(
    cells: Sequence[BtcDvolVrpCell],
) -> BtcDvolVrpExperimentResult:
    """Publish every preregistered outcome without a performance abort."""
    ordered = _validated_cells(cells)
    summaries = [row for cell in ordered for row in _cell_summaries(cell)]
    trades = [row for cell in ordered for row in _cell_trade_rows(cell)]
    report: dict[str, object] = {
        "schema_version": "v58_btc_dvol_vrp_continuation_long_replay_v1",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "live_configuration_changed": False,
            "place_attempted": False,
        },
        "summary_rows": summaries,
        "comparisons": _comparisons(summaries),
        "acceptance": evaluate_btc_dvol_vrp_acceptance(summaries),
        "delayed_scenario_cost_headroom": _delayed_headroom(summaries),
        "unfavorable_slices": _unfavorable_slices(summaries),
        "limitations": [
            "all BTC price partitions were previously opened",
            "DVOL history lacks bitemporal revision or receipt-time metadata",
            "one-minute bars cannot establish exact BBO ordering or market impact",
            "the delayed scenario is a lower-bound stress, not exact break-even cost",
            "positive standalone results cannot authorize live promotion",
        ],
    }
    return BtcDvolVrpExperimentResult(report, tuple(trades))


def evaluate_btc_dvol_vrp_acceptance(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Apply the exact preregistered support rule without retuning."""
    indexed = _acceptance_rows(rows)
    failures: list[str] = []
    for partition in ("validation", "pseudo_holdout"):
        nominal = indexed[(partition, "nominal", _PRIMARY)]
        if _integer(nominal, "completed_trades") < 10:
            failures.append(f"{partition}_nominal_minimum_ten_completed_trades")
        for scenario in _SCENARIOS:
            _check_primary_cell(indexed, partition, scenario, failures)
        _check_nominal_comparators(indexed, partition, failures)
    _check_placebo_specificity(indexed, failures)
    return {
        "candidate_supported": not failures,
        "decision": (
            "advance_to_shared_route_and_prospective_validation"
            if not failures
            else "reject_frozen_candidate_without_retuning"
        ),
        "failed_checks": failures,
        "live_promotion_authorized": False,
        "retuning_authorized": False,
    }


def _validated_cells(
    cells: Sequence[BtcDvolVrpCell],
) -> tuple[BtcDvolVrpCell, ...]:
    indexed = {(cell.partition, cell.scenario): cell for cell in cells}
    required = {
        (partition, scenario) for partition in _PARTITIONS for scenario in _SCENARIOS
    }
    if len(indexed) != len(cells) or set(indexed) != required:
        raise ValueError("BTC DVOL-VRP result matrix is duplicate or incomplete")
    return tuple(indexed[key] for key in sorted(indexed))


def _cell_summaries(cell: BtcDvolVrpCell) -> list[dict[str, object]]:
    rows = [
        _summary(cell, arm, report, count, times, gaps)
        for arm, report, count, times, gaps in _active_arms(cell.replay)
    ]
    rows.append(_no_action(cell))
    return rows


def _active_arms(
    replay: BtcDvolVrpReplay,
) -> tuple[tuple[str, SharedPortfolioReport, int, tuple[str, ...], int], ...]:
    return (
        (
            _PRIMARY,
            replay.primary_report,
            replay.primary_signal_count,
            replay.primary_signal_times_utc,
            replay.primary_delay_gap_cancellations,
        ),
        (
            _PRICE,
            replay.price_only_report,
            replay.price_only_signal_count,
            replay.price_only_signal_times_utc,
            replay.price_only_delay_gap_cancellations,
        ),
        (
            _HIGH,
            replay.high_vrp_only_report,
            replay.high_vrp_only_signal_count,
            replay.high_vrp_only_signal_times_utc,
            replay.high_vrp_only_delay_gap_cancellations,
        ),
        (
            _LOW,
            replay.low_vrp_placebo_report,
            replay.low_vrp_placebo_signal_count,
            replay.low_vrp_placebo_signal_times_utc,
            replay.low_vrp_placebo_delay_gap_cancellations,
        ),
        (
            _SWEEP,
            replay.v58_sweep_report,
            replay.v58_sweep_signal_count,
            replay.v58_sweep_signal_times_utc,
            replay.v58_sweep_delay_gap_cancellations,
        ),
    )


def _summary(
    cell: BtcDvolVrpCell,
    arm: str,
    report: SharedPortfolioReport,
    count: int,
    times: tuple[str, ...],
    gap_cancellations: int,
) -> dict[str, object]:
    summary = summarize_replay_report(
        report,
        signal_count=count,
        partition_days=cell.partition_days,
    )
    return {
        "partition": cell.partition,
        "scenario": cell.scenario,
        "arm": arm,
        **summary,
        "raw_signal_count": count,
        "gross_market_pnl_usd": sum(trade.gross_pnl_usd for trade in report.trades),
        "fees_usd": report.total_fees_usd,
        "funding_usd": report.funding_cashflow_usd,
        "gap_expired_entries": report.gap_expired_entries + gap_cancellations,
        "median_interarrival_hours": _median_interarrival_hours(times),
        "events_per_week": count * 7.0 / cell.partition_days,
        "point_in_time_event_times_utc": list(times),
    }


def _no_action(cell: BtcDvolVrpCell) -> dict[str, object]:
    return {
        "partition": cell.partition,
        "scenario": cell.scenario,
        "arm": _NO_ACTION,
        **no_action_summary(cell.partition_days),
        "raw_signal_count": 0,
        "gross_market_pnl_usd": 0.0,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "median_interarrival_hours": None,
        "events_per_week": 0.0,
        "point_in_time_event_times_utc": [],
    }


def _cell_trade_rows(cell: BtcDvolVrpCell) -> list[dict[str, object]]:
    return [
        {
            "partition": cell.partition,
            "scenario": cell.scenario,
            "arm": arm,
            **asdict(trade),
        }
        for arm, report, _, _, _ in _active_arms(cell.replay)
        for trade in report.trades
    ]


def _comparisons(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    indexed = _indexed(rows)
    output: list[dict[str, object]] = []
    for partition in _PARTITIONS:
        for scenario in _SCENARIOS:
            primary = indexed[(partition, scenario, _PRIMARY)]
            output.append(_comparison_row(indexed, primary, partition, scenario))
    return output


def _comparison_row(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    primary: Mapping[str, object],
    partition: str,
    scenario: str,
) -> dict[str, object]:
    return {
        "partition": partition,
        "scenario": scenario,
        "candidate_minus_no_action_usd": _number(primary, "net_pnl_usd"),
        "candidate_minus_price_only_usd": _net_delta(
            primary, rows[(partition, scenario, _PRICE)]
        ),
        "candidate_minus_high_vrp_only_usd": _net_delta(
            primary, rows[(partition, scenario, _HIGH)]
        ),
        "candidate_minus_low_vrp_placebo_usd": _net_delta(
            primary, rows[(partition, scenario, _LOW)]
        ),
        "candidate_minus_sweep_usd": _net_delta(
            primary, rows[(partition, scenario, _SWEEP)]
        ),
    }


def _acceptance_rows(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    indexed = _indexed(rows)
    required = {
        (partition, scenario, arm)
        for partition in ("validation", "pseudo_holdout")
        for scenario in _SCENARIOS
        for arm in _ARMS
    }
    missing = sorted(required.difference(indexed))
    if missing:
        raise ValueError(f"BTC DVOL-VRP acceptance rows missing: {missing}")
    return indexed


def _check_primary_cell(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    scenario: str,
    failures: list[str],
) -> None:
    primary = rows[(partition, scenario, _PRIMARY)]
    prefix = f"{partition}_{scenario}"
    if _number(primary, "net_pnl_usd") <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(primary):
        failures.append(f"{prefix}_profit_factor_above_one")
    if _number(primary, "net_pnl_excluding_largest_winner_usd") <= 0.0:
        failures.append(f"{prefix}_positive_ex_largest")
    if _integer(primary, "liquidations") != 0:
        failures.append(f"{prefix}_zero_liquidations")
    if primary.get("insolvent") is not False:
        failures.append(f"{prefix}_no_insolvency")


def _check_nominal_comparators(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    failures: list[str],
) -> None:
    primary = rows[(partition, "nominal", _PRIMARY)]
    primary_net = _number(primary, "net_pnl_usd")
    comparators = (
        (_NO_ACTION, "no_action"),
        (_PRICE, "price_only"),
        (_SWEEP, "v58_sweep"),
    )
    for arm, label in comparators:
        if primary_net <= _number(rows[(partition, "nominal", arm)], "net_pnl_usd"):
            failures.append(f"{partition}_nominal_candidate_exceeds_{label}")


def _check_placebo_specificity(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    failures: list[str],
) -> None:
    matches = []
    for partition in ("validation", "pseudo_holdout"):
        primary = rows[(partition, "nominal", _PRIMARY)]
        placebo = rows[(partition, "nominal", _LOW)]
        matches.append(
            _number(placebo, "net_pnl_usd") >= _number(primary, "net_pnl_usd")
        )
    if all(matches):
        failures.append("low_vrp_placebo_not_directionally_specific")


def _delayed_headroom(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    indexed = _indexed(rows)
    return [
        {
            "partition": partition,
            "net_pnl_usd": _number(
                indexed[(partition, "delayed", _PRIMARY)], "net_pnl_usd"
            ),
            "survives_lower_bound": _primary_cell_passes(
                indexed[(partition, "delayed", _PRIMARY)]
            ),
        }
        for partition in ("validation", "pseudo_holdout")
    ]


def _primary_cell_passes(row: Mapping[str, object]) -> bool:
    return (
        _number(row, "net_pnl_usd") > 0.0
        and _profit_factor_above_one(row)
        and _number(row, "net_pnl_excluding_largest_winner_usd") > 0.0
        and _integer(row, "liquidations") == 0
        and row.get("insolvent") is False
    )


def _unfavorable_slices(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "partition": str(row.get("partition")),
            "scenario": str(row.get("scenario")),
            "net_pnl_usd": _number(row, "net_pnl_usd"),
            "maximum_drawdown_pct": _number(row, "maximum_drawdown_pct"),
        }
        for row in rows
        if row.get("arm") == _PRIMARY and _number(row, "net_pnl_usd") <= 0.0
    ]


def _indexed(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    output: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for row in rows:
        key = tuple(str(row.get(name, "")) for name in ("partition", "scenario", "arm"))
        if len(key) != 3 or not all(key) or key in output:
            raise ValueError("BTC DVOL-VRP rows have duplicate or incomplete identity")
        output[key] = row
    return output


def _net_delta(left: Mapping[str, object], right: Mapping[str, object]) -> float:
    return _number(left, "net_pnl_usd") - _number(right, "net_pnl_usd")


def _median_interarrival_hours(times: tuple[str, ...]) -> float | None:
    if len(times) < 2:
        return None
    index = pd.DatetimeIndex(pd.to_datetime(list(times), utc=True)).sort_values()
    gaps = index.to_series().diff().dropna().dt.total_seconds() / 3_600.0
    return float(gaps.median())


def _profit_factor_above_one(row: Mapping[str, object]) -> bool:
    value = row.get("profit_factor")
    if value is None:
        return _integer(row, "wins") > 0 and _integer(row, "losses") == 0
    return _number(row, "profit_factor") > 1.0


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"BTC DVOL-VRP {key} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"BTC DVOL-VRP {key} must be finite")
    return numeric


def _integer(row: Mapping[str, object], key: str) -> int:
    numeric = _number(row, key)
    if numeric < 0.0 or not numeric.is_integer():
        raise ValueError(f"BTC DVOL-VRP {key} must be a nonnegative integer")
    return int(numeric)
