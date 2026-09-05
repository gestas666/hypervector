"""Reporting and frozen acceptance for the BTC IBIT creation experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math
from numbers import Real

import pandas as pd

from hypervector.research.btc_ibit_creation_replay import BtcIbitCreationReplay
from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    no_action_summary,
    summarize_replay_report,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


_PARTITIONS = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {
    "nominal": (2.0, 0),
    "stress": (5.0, 0),
    "publication_delay_24h": (2.0, 1_440),
}
_CANDIDATE = "ibit_two_creation_persistence_candidate"
_SINGLE = "ibit_single_creation_onset_control"
_REDEMPTION = "ibit_two_redemption_persistence_long_placebo"
_SWEEP = "v58_liquidity_sweep_long_control"
_NO_ACTION = "no_action"
_ARMS = (_CANDIDATE, _SINGLE, _REDEMPTION, _SWEEP, _NO_ACTION)


@dataclass(frozen=True)
class BtcIbitCreationCell:
    """One frozen partition and execution-scenario replay."""

    partition: str
    scenario: str
    partition_days: float
    replay: BtcIbitCreationReplay

    def __post_init__(self) -> None:
        """Reject partition, scenario, duration, or authority drift."""
        if self.partition not in _PARTITIONS:
            raise ValueError("unknown BTC IBIT creation partition")
        expected = _SCENARIOS.get(self.scenario)
        observed = (
            self.replay.slippage_bps_per_taker_side,
            self.replay.publication_delay_minutes,
        )
        if expected is None or observed != expected:
            raise ValueError("BTC IBIT creation scenario drifted")
        if not math.isfinite(self.partition_days) or self.partition_days <= 0.0:
            raise ValueError("BTC IBIT creation partition days must be positive")
        if self.replay.execution_authority != "none":
            raise ValueError("BTC IBIT creation replay acquired execution authority")


@dataclass(frozen=True)
class BtcIbitCreationExperimentResult:
    """JSON-safe report plus complete active-arm trade evidence."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_btc_ibit_creation_report(
    cells: Sequence[BtcIbitCreationCell],
) -> BtcIbitCreationExperimentResult:
    """Publish every preregistered outcome without a performance abort."""
    ordered = _validated_cells(cells)
    summaries = [row for cell in ordered for row in _cell_summaries(cell)]
    trades = [row for cell in ordered for row in _cell_trade_rows(cell)]
    report: dict[str, object] = {
        "schema_version": "v58_btc_ibit_creation_persistence_long_replay_v1",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "live_configuration_changed": False,
            "place_attempted": False,
        },
        "summary_rows": summaries,
        "comparisons": _comparisons(summaries),
        "acceptance": evaluate_btc_ibit_creation_acceptance(summaries),
        "limitations": [
            "all three BTC price partitions were previously opened",
            "issuer as-of rows lack observed historical publication timestamps",
            "one-minute bars cannot establish exact BBO, mark ordering, or depth",
            "positive standalone results cannot authorize live promotion",
        ],
    }
    return BtcIbitCreationExperimentResult(report, tuple(trades))


def evaluate_btc_ibit_creation_acceptance(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Apply the exact preregistered support rule without retuning."""
    indexed = _acceptance_rows(rows)
    failures: list[str] = []
    for partition in ("validation", "pseudo_holdout"):
        nominal = indexed[(partition, "nominal", _CANDIDATE)]
        if _integer(nominal, "completed_trades") < 10:
            failures.append(f"{partition}_nominal_minimum_ten_completed_trades")
        for scenario in _SCENARIOS:
            _check_candidate_cell(indexed, partition, scenario, failures)
        _check_nominal_comparators(indexed, partition, failures)
    _check_redemption_specificity(indexed, failures)
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
    cells: Sequence[BtcIbitCreationCell],
) -> tuple[BtcIbitCreationCell, ...]:
    indexed = {(cell.partition, cell.scenario): cell for cell in cells}
    required = {
        (partition, scenario) for partition in _PARTITIONS for scenario in _SCENARIOS
    }
    if len(indexed) != len(cells) or set(indexed) != required:
        raise ValueError("BTC IBIT creation result matrix is duplicate or incomplete")
    return tuple(indexed[key] for key in sorted(indexed))


def _cell_summaries(cell: BtcIbitCreationCell) -> list[dict[str, object]]:
    rows = [
        _summary(cell, arm, report, count, times, gaps)
        for arm, report, count, times, gaps in _active_arms(cell.replay)
    ]
    rows.append(_no_action(cell))
    return rows


def _active_arms(
    replay: BtcIbitCreationReplay,
) -> tuple[
    tuple[str, SharedPortfolioReport, int, tuple[str, ...], int],
    ...,
]:
    return (
        (
            _CANDIDATE,
            replay.candidate_report,
            replay.candidate_signal_count,
            replay.candidate_signal_times_utc,
            replay.candidate_delay_gap_cancellations,
        ),
        (
            _SINGLE,
            replay.single_creation_control_report,
            replay.single_creation_signal_count,
            replay.single_creation_signal_times_utc,
            replay.single_creation_delay_gap_cancellations,
        ),
        (
            _REDEMPTION,
            replay.redemption_placebo_report,
            replay.redemption_placebo_signal_count,
            replay.redemption_placebo_signal_times_utc,
            replay.redemption_placebo_delay_gap_cancellations,
        ),
        (
            _SWEEP,
            replay.v58_sweep_control_report,
            replay.v58_sweep_signal_count,
            replay.v58_sweep_signal_times_utc,
            0,
        ),
    )


def _summary(
    cell: BtcIbitCreationCell,
    arm: str,
    report: SharedPortfolioReport,
    count: int,
    times: tuple[str, ...],
    delay_gap_cancellations: int,
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
        "gap_expired_entries": report.gap_expired_entries + delay_gap_cancellations,
        "median_interarrival_hours": _median_interarrival_hours(times),
        "events_per_week": count * 7.0 / cell.partition_days,
        "point_in_time_event_times_utc": list(times),
    }


def _no_action(cell: BtcIbitCreationCell) -> dict[str, object]:
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


def _cell_trade_rows(cell: BtcIbitCreationCell) -> list[dict[str, object]]:
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
            candidate = indexed[(partition, scenario, _CANDIDATE)]
            output.append(
                {
                    "partition": partition,
                    "scenario": scenario,
                    "candidate_minus_no_action_usd": _number(candidate, "net_pnl_usd"),
                    "candidate_minus_sweep_usd": _net_delta(
                        candidate, indexed[(partition, scenario, _SWEEP)]
                    ),
                    "candidate_minus_single_creation_usd": _net_delta(
                        candidate, indexed[(partition, scenario, _SINGLE)]
                    ),
                    "candidate_minus_redemption_placebo_usd": _net_delta(
                        candidate, indexed[(partition, scenario, _REDEMPTION)]
                    ),
                }
            )
    return output


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
        raise ValueError(f"BTC IBIT creation acceptance rows missing: {missing}")
    return indexed


def _check_candidate_cell(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    scenario: str,
    failures: list[str],
) -> None:
    candidate = rows[(partition, scenario, _CANDIDATE)]
    prefix = f"{partition}_{scenario}"
    if _number(candidate, "net_pnl_usd") <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(candidate):
        failures.append(f"{prefix}_profit_factor_above_one")
    if _number(candidate, "net_pnl_excluding_largest_winner_usd") <= 0.0:
        failures.append(f"{prefix}_positive_ex_largest")
    if _integer(candidate, "liquidations") != 0:
        failures.append(f"{prefix}_zero_liquidations")
    if candidate.get("insolvent") is not False:
        failures.append(f"{prefix}_no_insolvency")


def _check_nominal_comparators(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    failures: list[str],
) -> None:
    candidate = rows[(partition, "nominal", _CANDIDATE)]
    candidate_net = _number(candidate, "net_pnl_usd")
    if candidate_net <= _number(
        rows[(partition, "nominal", _NO_ACTION)], "net_pnl_usd"
    ):
        failures.append(f"{partition}_nominal_candidate_exceeds_no_action")
    if candidate_net <= _number(rows[(partition, "nominal", _SWEEP)], "net_pnl_usd"):
        failures.append(f"{partition}_nominal_candidate_exceeds_v58_sweep")


def _check_redemption_specificity(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    failures: list[str],
) -> None:
    placebo_matches = []
    for partition in ("validation", "pseudo_holdout"):
        candidate = rows[(partition, "nominal", _CANDIDATE)]
        placebo = rows[(partition, "nominal", _REDEMPTION)]
        placebo_matches.append(
            _number(placebo, "net_pnl_usd") >= _number(candidate, "net_pnl_usd")
        )
    if all(placebo_matches):
        failures.append("redemption_long_placebo_not_directionally_specific")


def _indexed(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    output: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for row in rows:
        key = tuple(str(row.get(name, "")) for name in ("partition", "scenario", "arm"))
        if len(key) != 3 or not all(key) or key in output:
            raise ValueError(
                "BTC IBIT creation rows have duplicate or incomplete identity"
            )
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
        raise ValueError(f"BTC IBIT creation {key} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"BTC IBIT creation {key} must be finite")
    return numeric


def _integer(row: Mapping[str, object], key: str) -> int:
    numeric = _number(row, key)
    if numeric < 0.0 or not numeric.is_integer():
        raise ValueError(f"BTC IBIT creation {key} must be a nonnegative integer")
    return int(numeric)
