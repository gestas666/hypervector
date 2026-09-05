"""Reporting for the frozen BTC negative-funding breakout experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.btc_negative_funding_breakout_replay import (
    BtcNegativeFundingBreakoutReplay,
)
from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    no_action_summary,
    summarize_replay_report,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


_PARTITIONS = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {
    "nominal": (2.0, 0),
    "stress": (5.0, 0),
    "one_minute_entry_delay": (2.0, 1),
}


@dataclass(frozen=True)
class BtcNegativeFundingBreakoutCell:
    """One frozen partition and execution-scenario replay."""

    partition: str
    scenario: str
    partition_days: float
    replay: BtcNegativeFundingBreakoutReplay

    def __post_init__(self) -> None:
        """Reject cell identity, timing, or friction drift."""
        if self.partition not in _PARTITIONS:
            raise ValueError("unknown BTC negative-funding breakout partition")
        expected = _SCENARIOS.get(self.scenario)
        observed = (
            self.replay.slippage_bps_per_taker_side,
            self.replay.entry_delay_minutes,
        )
        if expected is None or observed != expected:
            raise ValueError("BTC negative-funding breakout scenario drifted")
        if not math.isfinite(self.partition_days) or self.partition_days <= 0.0:
            raise ValueError("BTC breakout partition days must be positive")
        if self.replay.execution_authority != "none":
            raise ValueError("BTC breakout replay acquired execution authority")


@dataclass(frozen=True)
class BtcNegativeFundingBreakoutExperimentResult:
    """JSON-safe report plus complete trade-level evidence."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_btc_negative_funding_breakout_report(
    cells: Sequence[BtcNegativeFundingBreakoutCell],
) -> BtcNegativeFundingBreakoutExperimentResult:
    """Build every preregistered result without performance aborts."""
    ordered = _validated_cells(cells)
    summaries: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    for cell in ordered:
        summaries.extend(_cell_summaries(cell))
        trades.extend(_cell_trade_rows(cell))
    report: dict[str, object] = {
        "schema_version": "v58_btc_negative_funding_breakout_replay_v1",
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
            "all three historical partitions were previously opened",
            "negative funding is not proof of spot-led demand",
            "one-minute bars cannot establish exact mark or BBO ordering",
            "positive standalone results cannot authorize live promotion",
        ],
    }
    return BtcNegativeFundingBreakoutExperimentResult(report, tuple(trades))


def _validated_cells(
    cells: Sequence[BtcNegativeFundingBreakoutCell],
) -> tuple[BtcNegativeFundingBreakoutCell, ...]:
    indexed = {(cell.partition, cell.scenario): cell for cell in cells}
    required = {
        (partition, scenario) for partition in _PARTITIONS for scenario in _SCENARIOS
    }
    if len(indexed) != len(cells) or set(indexed) != required:
        raise ValueError(
            "BTC negative-funding result matrix is duplicate or incomplete"
        )
    return tuple(indexed[key] for key in sorted(indexed))


def _cell_summaries(
    cell: BtcNegativeFundingBreakoutCell,
) -> list[dict[str, object]]:
    overlap = _same_minute_overlap(cell.replay)
    arms = (
        (
            "negative_funding_breakout_candidate",
            cell.replay.candidate_report,
            cell.replay.candidate_signal_count,
            cell.replay.candidate_signal_times_utc,
        ),
        (
            "unconditioned_breakout_control",
            cell.replay.control_report,
            cell.replay.control_signal_count,
            cell.replay.control_signal_times_utc,
        ),
    )
    rows = [
        _report_summary(cell, arm, report, count, times, overlap)
        for arm, report, count, times in arms
    ]
    rows.append(_no_action_row(cell, overlap))
    return rows


def _report_summary(
    cell: BtcNegativeFundingBreakoutCell,
    arm: str,
    report: SharedPortfolioReport,
    signal_count: int,
    signal_times: tuple[str, ...],
    overlap: int,
) -> dict[str, object]:
    summary = summarize_replay_report(
        report,
        signal_count=signal_count,
        partition_days=cell.partition_days,
    )
    return {
        "partition": cell.partition,
        "scenario": cell.scenario,
        "arm": arm,
        **summary,
        "raw_signal_count": signal_count,
        "gross_market_pnl_usd": sum(trade.gross_pnl_usd for trade in report.trades),
        "fees_usd": report.total_fees_usd,
        "funding_usd": report.funding_cashflow_usd,
        "median_interarrival_hours": _median_interarrival_hours(signal_times),
        "events_per_week": signal_count * 7.0 / cell.partition_days,
        "candidate_control_same_minute_overlap": overlap,
    }


def _no_action_row(
    cell: BtcNegativeFundingBreakoutCell,
    overlap: int,
) -> dict[str, object]:
    return {
        "partition": cell.partition,
        "scenario": cell.scenario,
        "arm": "no_action",
        **no_action_summary(cell.partition_days),
        "raw_signal_count": 0,
        "gross_market_pnl_usd": 0.0,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "median_interarrival_hours": None,
        "events_per_week": 0.0,
        "candidate_control_same_minute_overlap": overlap,
    }


def _same_minute_overlap(replay: BtcNegativeFundingBreakoutReplay) -> int:
    candidate = set(replay.candidate_signal_times_utc)
    control = set(replay.control_signal_times_utc)
    return len(candidate.intersection(control))


def _median_interarrival_hours(signal_times: tuple[str, ...]) -> float | None:
    if len(signal_times) < 2:
        return None
    times = pd.DatetimeIndex(pd.to_datetime(list(signal_times), utc=True)).sort_values()
    gaps = times.to_series().diff().dropna().dt.total_seconds() / 3_600.0
    return float(gaps.median())


def _cell_trade_rows(
    cell: BtcNegativeFundingBreakoutCell,
) -> list[dict[str, object]]:
    reports = (
        ("negative_funding_breakout_candidate", cell.replay.candidate_report),
        ("unconditioned_breakout_control", cell.replay.control_report),
    )
    return [
        {
            "partition": cell.partition,
            "scenario": cell.scenario,
            "arm": arm,
            **asdict(trade),
        }
        for arm, report in reports
        for trade in report.trades
    ]


def _comparisons(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    indexed = _indexed(rows)
    output: list[dict[str, object]] = []
    for partition in _PARTITIONS:
        for scenario in _SCENARIOS:
            candidate = indexed[
                (partition, scenario, "negative_funding_breakout_candidate")
            ]
            control = indexed[(partition, scenario, "unconditioned_breakout_control")]
            output.append(
                {
                    "partition": partition,
                    "scenario": scenario,
                    "candidate_minus_no_action_usd": _number(
                        candidate,
                        "net_pnl_usd",
                    ),
                    "candidate_minus_control_usd": _number(
                        candidate,
                        "net_pnl_usd",
                    )
                    - _number(control, "net_pnl_usd"),
                    "candidate_minus_control_drawdown_pct": _number(
                        candidate,
                        "maximum_drawdown_pct",
                    )
                    - _number(control, "maximum_drawdown_pct"),
                }
            )
    return output


def _acceptance(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    indexed = _indexed(rows)
    failures: list[str] = []
    for partition in ("validation", "pseudo_holdout"):
        nominal = indexed[(partition, "nominal", "negative_funding_breakout_candidate")]
        if _integer(nominal, "completed_trades") < 13:
            failures.append(f"{partition}_minimum_thirteen_trades")
        for scenario in _SCENARIOS:
            _check_cell(indexed, partition, scenario, failures)
    return {
        "candidate_supported": not failures,
        "failed_checks": failures,
        "live_promotion_authorized": False,
        "retuning_authorized": False,
    }


def _check_cell(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    scenario: str,
    failures: list[str],
) -> None:
    candidate = rows[(partition, scenario, "negative_funding_breakout_candidate")]
    control = rows[(partition, scenario, "unconditioned_breakout_control")]
    prefix = f"{partition}_{scenario}"
    if _number(candidate, "net_pnl_usd") <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(candidate):
        failures.append(f"{prefix}_profit_factor_above_one")
    if _number(candidate, "net_pnl_excluding_largest_winner_usd") <= 0.0:
        failures.append(f"{prefix}_positive_ex_largest")
    if _integer(candidate, "liquidations") != 0:
        failures.append(f"{prefix}_zero_liquidations")
    if _number(candidate, "net_pnl_usd") <= _number(control, "net_pnl_usd"):
        failures.append(f"{prefix}_candidate_exceeds_control")
    if _number(candidate, "maximum_drawdown_pct") < _number(
        control,
        "maximum_drawdown_pct",
    ):
        failures.append(f"{prefix}_drawdown_no_worse_than_control")


def _profit_factor_above_one(row: Mapping[str, object]) -> bool:
    value = row.get("profit_factor")
    if value is None:
        return _integer(row, "wins") > 0 and _integer(row, "losses") == 0
    return _number(row, "profit_factor") > 1.0


def _indexed(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    return {
        (str(row["partition"]), str(row["scenario"]), str(row["arm"])): row
        for row in rows
    }


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool):
        raise ValueError(f"BTC breakout {key} must be numeric")
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"BTC breakout {key} must be numeric") from error
    if not math.isfinite(numeric):
        raise ValueError(f"BTC breakout {key} must be finite")
    return numeric


def _integer(row: Mapping[str, object], key: str) -> int:
    numeric = _number(row, key)
    if numeric < 0.0 or not numeric.is_integer():
        raise ValueError(f"BTC breakout {key} must be a nonnegative integer")
    return int(numeric)
