"""Reporting for the frozen BTC trend-pullback experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    no_action_summary,
    summarize_replay_report,
)
from hypervector.research.btc_trend_pullback_reacceleration_replay import (
    BtcTrendPullbackReplay,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


_SCENARIOS = {"nominal": 2.0, "stress": 5.0}
_PARTITIONS = ("development", "validation", "pseudo_holdout")


@dataclass(frozen=True)
class BtcTrendPullbackCell:
    """One frozen partition and friction-scenario comparison."""

    partition: str
    scenario: str
    partition_days: float
    candidate: BtcTrendPullbackReplay
    control: SharedPortfolioReport
    control_signal_count: int
    control_signal_times_utc: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject cell identity or cost drift."""
        if self.partition not in _PARTITIONS:
            raise ValueError("unknown BTC trend-pullback partition")
        expected = _SCENARIOS.get(self.scenario)
        if expected is None or not math.isclose(
            self.candidate.slippage_bps_per_taker_side, expected
        ):
            raise ValueError("BTC trend-pullback scenario drifted")
        if not math.isfinite(self.partition_days) or self.partition_days <= 0.0:
            raise ValueError("BTC trend-pullback partition days must be positive")
        if self.control_signal_count < 0:
            raise ValueError("BTC trend-pullback control signals must be nonnegative")


@dataclass(frozen=True)
class BtcTrendPullbackExperimentResult:
    """JSON-safe report plus complete trade-level evidence."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_btc_trend_pullback_report(
    cells: Sequence[BtcTrendPullbackCell],
) -> BtcTrendPullbackExperimentResult:
    """Build every registered result without performance aborts."""
    ordered = _validated_cells(cells)
    summaries: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    for cell in ordered:
        summaries.extend(_cell_summaries(cell))
        trades.extend(_cell_trade_rows(cell))
    report: dict[str, object] = {
        "schema_version": "v58_btc_trend_pullback_reacceleration_replay_v1",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "live_configuration_changed": False,
            "place_attempted": False,
        },
        "summary_rows": summaries,
        "comparisons": _comparisons(summaries),
        "acceptance": _acceptance(summaries),
        "limitations": [
            "all three partitions were previously opened",
            "one-minute bars cannot establish exact mark or BBO ordering",
            "positive results cannot authorize live promotion",
        ],
    }
    return BtcTrendPullbackExperimentResult(report, tuple(trades))


def _validated_cells(
    cells: Sequence[BtcTrendPullbackCell],
) -> tuple[BtcTrendPullbackCell, ...]:
    indexed = {(cell.partition, cell.scenario): cell for cell in cells}
    required = {
        (partition, scenario) for partition in _PARTITIONS for scenario in _SCENARIOS
    }
    if len(indexed) != len(cells) or set(indexed) != required:
        raise ValueError("BTC trend-pullback cells are duplicate or incomplete")
    return tuple(indexed[key] for key in sorted(indexed))


def _cell_summaries(cell: BtcTrendPullbackCell) -> list[dict[str, object]]:
    overlap = _long_route_overlap(cell)
    arms = (
        (
            "candidate",
            summarize_replay_report(
                cell.candidate.report,
                signal_count=cell.candidate.signal_count,
                partition_days=cell.partition_days,
            ),
            cell.candidate.signal_times_utc,
        ),
        (
            "control",
            summarize_replay_report(
                cell.control,
                signal_count=cell.control_signal_count,
                partition_days=cell.partition_days,
            ),
            cell.control_signal_times_utc,
        ),
        ("no_action", no_action_summary(cell.partition_days), ()),
    )
    return [
        {
            "partition": cell.partition,
            "scenario": cell.scenario,
            "arm": arm,
            **_registered_summary(summary, signal_times, cell.partition_days, overlap),
        }
        for arm, summary, signal_times in arms
    ]


def _registered_summary(
    summary: Mapping[str, object],
    signal_times: Sequence[str],
    partition_days: float,
    overlap: Mapping[str, object],
) -> dict[str, object]:
    output = dict(summary)
    raw_signals = int(output["signal_episodes"])
    output.update(
        {
            "raw_signal_count": raw_signals,
            "fees_usd": output["total_fees_usd"],
            "funding_usd": output["funding_cashflow_usd"],
            "median_interarrival_hours": _median_interarrival_hours(signal_times),
            "events_per_week": raw_signals * 7.0 / partition_days,
            "long_route_overlap_and_displacement": dict(overlap),
        }
    )
    return output


def _long_route_overlap(cell: BtcTrendPullbackCell) -> dict[str, object]:
    candidate = set(cell.candidate.signal_times_utc)
    control = set(cell.control_signal_times_utc)
    return {
        "candidate_raw_events": len(candidate),
        "sweep_control_raw_events": len(control),
        "same_minute_overlap_events": len(candidate.intersection(control)),
        "occupancy_displacement": "reported_in_shared_long_route_case",
    }


def _median_interarrival_hours(signal_times: Sequence[str]) -> float | None:
    if len(signal_times) < 2:
        return None
    times = pd.DatetimeIndex(pd.to_datetime(list(signal_times), utc=True)).sort_values()
    gaps = times.to_series().diff().dropna().dt.total_seconds() / 3_600.0
    return float(gaps.median())


def _cell_trade_rows(cell: BtcTrendPullbackCell) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm, report in (
        ("candidate", cell.candidate.report),
        ("control", cell.control),
    ):
        rows.extend(
            {
                "partition": cell.partition,
                "scenario": cell.scenario,
                "arm": arm,
                **asdict(trade),
            }
            for trade in report.trades
        )
    return rows


def _comparisons(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    indexed = _indexed(rows)
    output: list[dict[str, object]] = []
    for partition in _PARTITIONS:
        for scenario in _SCENARIOS:
            candidate = float(
                indexed[(partition, scenario, "candidate")]["net_pnl_usd"]
            )
            control = float(indexed[(partition, scenario, "control")]["net_pnl_usd"])
            output.append(
                {
                    "partition": partition,
                    "scenario": scenario,
                    "candidate_minus_no_action_usd": candidate,
                    "candidate_minus_control_usd": candidate - control,
                }
            )
    return output


def _acceptance(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    indexed = _indexed(rows)
    failures: list[str] = []
    for partition in ("validation", "pseudo_holdout"):
        nominal = indexed[(partition, "nominal", "candidate")]
        if int(nominal["completed_trades"]) < 13:
            failures.append(f"{partition}_minimum_thirteen_trades")
        for scenario in _SCENARIOS:
            _check_candidate(
                indexed[(partition, scenario, "candidate")],
                partition,
                scenario,
                failures,
            )
    return {
        "candidate_supported": not failures,
        "failed_checks": failures,
        "live_promotion_authorized": False,
        "retuning_authorized": False,
    }


def _check_candidate(
    row: Mapping[str, object], partition: str, scenario: str, failures: list[str]
) -> None:
    prefix = f"{partition}_{scenario}"
    if float(row["net_pnl_usd"]) <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(row):
        failures.append(f"{prefix}_profit_factor_above_one")
    if float(row["net_pnl_excluding_largest_winner_usd"]) <= 0.0:
        failures.append(f"{prefix}_positive_ex_largest")
    if int(row["liquidations"]) != 0:
        failures.append(f"{prefix}_zero_liquidations")


def _profit_factor_above_one(row: Mapping[str, object]) -> bool:
    value = row["profit_factor"]
    if value is None:
        return int(row["wins"]) > 0 and int(row["losses"]) == 0
    return float(value) > 1.0


def _indexed(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    return {
        (str(row["partition"]), str(row["scenario"]), str(row["arm"])): row
        for row in rows
    }
