"""Reporting for the frozen BTC spot-lead catch-up experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.btc_spot_lead_catchup_replay import (
    BtcSpotLeadCatchupReplay,
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
_CANDIDATE = "binance_spot_lead_hl_perp_catchup_candidate"
_NATIVE = "hl_native_breakout_control"
_PLACEBO = "binance_spot_lead_60m_lag_placebo"


@dataclass(frozen=True)
class BtcSpotLeadCatchupCell:
    """One frozen partition and execution-scenario replay."""

    partition: str
    scenario: str
    partition_days: float
    replay: BtcSpotLeadCatchupReplay

    def __post_init__(self) -> None:
        """Reject matrix, friction, timing, or authority drift."""
        if self.partition not in _PARTITIONS:
            raise ValueError("unknown BTC spot-lead partition")
        expected = _SCENARIOS.get(self.scenario)
        observed = (
            self.replay.slippage_bps_per_taker_side,
            self.replay.entry_delay_minutes,
        )
        if expected is None or observed != expected:
            raise ValueError("BTC spot-lead scenario drifted")
        if not math.isfinite(self.partition_days) or self.partition_days <= 0.0:
            raise ValueError("BTC spot-lead partition days must be positive")
        if self.replay.execution_authority != "none":
            raise ValueError("BTC spot-lead replay acquired execution authority")


@dataclass(frozen=True)
class BtcSpotLeadCatchupExperimentResult:
    """JSON-safe report plus all active-arm trade evidence."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_btc_spot_lead_catchup_report(
    cells: Sequence[BtcSpotLeadCatchupCell],
) -> BtcSpotLeadCatchupExperimentResult:
    """Build every preregistered result without performance aborts."""
    ordered = _validated_cells(cells)
    summaries = [row for cell in ordered for row in _cell_summaries(cell)]
    trades = [row for cell in ordered for row in _cell_trade_rows(cell)]
    report: dict[str, object] = {
        "schema_version": "v58_btc_spot_lead_catchup_replay_v1",
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
            "all three Hyperliquid partitions were previously opened",
            "cross-venue structural order does not prove causal price discovery",
            "one-minute bars cannot establish private latency, exact mark, or BBO ordering",
            "positive standalone results cannot authorize live promotion",
        ],
    }
    return BtcSpotLeadCatchupExperimentResult(report, tuple(trades))


def _validated_cells(
    cells: Sequence[BtcSpotLeadCatchupCell],
) -> tuple[BtcSpotLeadCatchupCell, ...]:
    indexed = {(cell.partition, cell.scenario): cell for cell in cells}
    required = {
        (partition, scenario) for partition in _PARTITIONS for scenario in _SCENARIOS
    }
    if len(indexed) != len(cells) or set(indexed) != required:
        raise ValueError("BTC spot-lead result matrix is duplicate or incomplete")
    return tuple(indexed[key] for key in sorted(indexed))


def _cell_summaries(cell: BtcSpotLeadCatchupCell) -> list[dict[str, object]]:
    native_overlap = _overlap(
        cell.replay.candidate_signal_times_utc,
        cell.replay.native_control_signal_times_utc,
    )
    placebo_overlap = _overlap(
        cell.replay.candidate_signal_times_utc,
        cell.replay.placebo_signal_times_utc,
    )
    rows = [
        _summary(cell, arm, report, count, times, native_overlap, placebo_overlap)
        for arm, report, count, times in _active_arms(cell.replay)
    ]
    rows.append(_no_action(cell, native_overlap, placebo_overlap))
    return rows


def _active_arms(
    replay: BtcSpotLeadCatchupReplay,
) -> tuple[tuple[str, SharedPortfolioReport, int, tuple[str, ...]], ...]:
    return (
        (
            _CANDIDATE,
            replay.candidate_report,
            replay.candidate_signal_count,
            replay.candidate_signal_times_utc,
        ),
        (
            _NATIVE,
            replay.native_control_report,
            replay.native_control_signal_count,
            replay.native_control_signal_times_utc,
        ),
        (
            _PLACEBO,
            replay.placebo_report,
            replay.placebo_signal_count,
            replay.placebo_signal_times_utc,
        ),
    )


def _summary(
    cell: BtcSpotLeadCatchupCell,
    arm: str,
    report: SharedPortfolioReport,
    count: int,
    times: tuple[str, ...],
    native_overlap: int,
    placebo_overlap: int,
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
        "median_interarrival_hours": _median_interarrival_hours(times),
        "events_per_week": count * 7.0 / cell.partition_days,
        "candidate_native_control_same_minute_overlap": native_overlap,
        "candidate_placebo_same_minute_overlap": placebo_overlap,
    }


def _no_action(
    cell: BtcSpotLeadCatchupCell,
    native_overlap: int,
    placebo_overlap: int,
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
        "candidate_native_control_same_minute_overlap": native_overlap,
        "candidate_placebo_same_minute_overlap": placebo_overlap,
    }


def _cell_trade_rows(cell: BtcSpotLeadCatchupCell) -> list[dict[str, object]]:
    return [
        {
            "partition": cell.partition,
            "scenario": cell.scenario,
            "arm": arm,
            **asdict(trade),
        }
        for arm, report, _, _ in _active_arms(cell.replay)
        for trade in report.trades
    ]


def _comparisons(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    indexed = _indexed(rows)
    output: list[dict[str, object]] = []
    for partition in _PARTITIONS:
        for scenario in _SCENARIOS:
            candidate = indexed[(partition, scenario, _CANDIDATE)]
            native = indexed[(partition, scenario, _NATIVE)]
            placebo = indexed[(partition, scenario, _PLACEBO)]
            output.append(
                {
                    "partition": partition,
                    "scenario": scenario,
                    "candidate_minus_no_action_usd": _number(candidate, "net_pnl_usd"),
                    "candidate_minus_native_control_usd": _number(
                        candidate, "net_pnl_usd"
                    )
                    - _number(native, "net_pnl_usd"),
                    "candidate_minus_placebo_usd": _number(candidate, "net_pnl_usd")
                    - _number(placebo, "net_pnl_usd"),
                    "candidate_minus_native_drawdown_pct": _number(
                        candidate, "maximum_drawdown_pct"
                    )
                    - _number(native, "maximum_drawdown_pct"),
                    "candidate_minus_placebo_drawdown_pct": _number(
                        candidate, "maximum_drawdown_pct"
                    )
                    - _number(placebo, "maximum_drawdown_pct"),
                }
            )
    return output


def _acceptance(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    indexed = _indexed(rows)
    failures: list[str] = []
    for partition in ("validation", "pseudo_holdout"):
        nominal = indexed[(partition, "nominal", _CANDIDATE)]
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
    candidate = rows[(partition, scenario, _CANDIDATE)]
    controls = (
        rows[(partition, scenario, _NATIVE)],
        rows[(partition, scenario, _PLACEBO)],
    )
    prefix = f"{partition}_{scenario}"
    if _number(candidate, "net_pnl_usd") <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(candidate):
        failures.append(f"{prefix}_profit_factor_above_one")
    if _number(candidate, "net_pnl_excluding_largest_winner_usd") <= 0.0:
        failures.append(f"{prefix}_positive_ex_largest")
    if _integer(candidate, "liquidations") != 0:
        failures.append(f"{prefix}_zero_liquidations")
    for name, control in zip(("native", "placebo"), controls):
        if _number(candidate, "net_pnl_usd") <= _number(control, "net_pnl_usd"):
            failures.append(f"{prefix}_candidate_exceeds_{name}")
        if _number(candidate, "maximum_drawdown_pct") < _number(
            control, "maximum_drawdown_pct"
        ):
            failures.append(f"{prefix}_drawdown_no_worse_than_{name}")


def _overlap(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    return len(set(left).intersection(right))


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
        raise ValueError(f"BTC spot-lead {key} must be numeric")
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"BTC spot-lead {key} must be numeric") from error
    if not math.isfinite(numeric):
        raise ValueError(f"BTC spot-lead {key} must be finite")
    return numeric


def _integer(row: Mapping[str, object], key: str) -> int:
    numeric = _number(row, key)
    if numeric < 0.0 or not numeric.is_integer():
        raise ValueError(f"BTC spot-lead {key} must be a nonnegative integer")
    return int(numeric)
