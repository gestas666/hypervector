"""Frozen reporting and acceptance for the BTC sweep-relaxation replay."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

from hypervector.research.btc_sweep_primary_relaxation_replay import (
    BtcSweepPrimaryRelaxationReplay,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


_SCENARIO_SLIPPAGE = {"nominal": 2.0, "stress": 5.0}


@dataclass(frozen=True)
class BtcSweepHistoricalCell:
    """One frozen partition and friction-scenario replay pair."""

    partition: str
    scenario: str
    partition_days: float
    replay: BtcSweepPrimaryRelaxationReplay

    def __post_init__(self) -> None:
        """Reject identity, duration, or friction drift."""
        if self.partition not in {"development", "validation", "pseudo_holdout"}:
            raise ValueError("unknown BTC sweep-relaxation partition")
        expected = _SCENARIO_SLIPPAGE.get(self.scenario)
        if expected is None:
            raise ValueError("unknown BTC sweep-relaxation scenario")
        if not math.isclose(self.replay.slippage_bps_per_taker_side, expected):
            raise ValueError("BTC sweep-relaxation scenario slippage drifted")
        if not math.isfinite(self.partition_days) or self.partition_days <= 0.0:
            raise ValueError("BTC sweep-relaxation partition days must be positive")


@dataclass(frozen=True)
class BtcSweepHistoricalExperimentResult:
    """JSON-safe report plus its complete trade-level sidecar rows."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


def build_historical_experiment_report(
    cells: Sequence[BtcSweepHistoricalCell],
) -> BtcSweepHistoricalExperimentResult:
    """Build all registered baselines, deltas, and the frozen decision."""
    ordered = _validated_cells(cells)
    summaries: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    for cell in ordered:
        summaries.extend(_cell_summaries(cell))
        trades.extend(_cell_trade_rows(cell))
    report: dict[str, object] = {
        "schema_version": "v58_btc_sweep_primary_relaxation_replay_v1",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "place_attempted": False,
            "live_configuration_changed": False,
        },
        "summary_rows": summaries,
        "comparisons": _comparisons(summaries),
        "acceptance": evaluate_frozen_acceptance(summaries),
        "limitations": [
            "all historical partitions were previously opened and are not pristine",
            "one-minute OHLC uses adverse stop-first ordering for same-bar touches",
            "bar replay does not establish exact mark triggers, latency, queue, or depth",
            "positive results cannot authorize live promotion",
        ],
    }
    return BtcSweepHistoricalExperimentResult(report, tuple(trades))


def _validated_cells(
    cells: Sequence[BtcSweepHistoricalCell],
) -> tuple[BtcSweepHistoricalCell, ...]:
    indexed: dict[tuple[str, str], BtcSweepHistoricalCell] = {}
    for cell in cells:
        key = (cell.partition, cell.scenario)
        if key in indexed:
            raise ValueError(f"duplicate BTC sweep-relaxation cell: {key}")
        indexed[key] = cell
    required = {
        (partition, scenario)
        for partition in ("development", "validation", "pseudo_holdout")
        for scenario in _SCENARIO_SLIPPAGE
    }
    missing = sorted(required.difference(indexed))
    if missing:
        raise ValueError(f"BTC sweep-relaxation cells missing: {missing}")
    return tuple(indexed[key] for key in sorted(indexed))


def _cell_summaries(cell: BtcSweepHistoricalCell) -> list[dict[str, object]]:
    rows = [
        _identified_summary(
            cell,
            "control",
            summarize_replay_report(
                cell.replay.control,
                signal_count=cell.replay.control_signal_count,
                partition_days=cell.partition_days,
            ),
        ),
        _identified_summary(
            cell,
            "candidate",
            summarize_replay_report(
                cell.replay.candidate,
                signal_count=cell.replay.candidate_signal_count,
                partition_days=cell.partition_days,
            ),
        ),
    ]
    rows.append(
        _identified_summary(cell, "no_action", no_action_summary(cell.partition_days))
    )
    return rows


def _identified_summary(
    cell: BtcSweepHistoricalCell,
    arm: str,
    summary: Mapping[str, object],
) -> dict[str, object]:
    return {
        "partition": cell.partition,
        "scenario": cell.scenario,
        "arm": arm,
        **summary,
    }


def _cell_trade_rows(cell: BtcSweepHistoricalCell) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm, report in (
        ("control", cell.replay.control),
        ("candidate", cell.replay.candidate),
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
    indexed = {
        (str(row["partition"]), str(row["scenario"]), str(row["arm"])): row
        for row in rows
    }
    output: list[dict[str, object]] = []
    for partition in ("development", "validation", "pseudo_holdout"):
        for scenario in ("nominal", "stress"):
            control = _number(indexed[(partition, scenario, "control")], "net_pnl_usd")
            candidate = _number(
                indexed[(partition, scenario, "candidate")], "net_pnl_usd"
            )
            output.append(
                {
                    "partition": partition,
                    "scenario": scenario,
                    "control_minus_no_action_usd": control,
                    "candidate_minus_control_usd": candidate - control,
                }
            )
    return output


def summarize_replay_report(
    report: SharedPortfolioReport,
    *,
    signal_count: int,
    partition_days: float,
) -> dict[str, object]:
    """Summarize one arm from its sole chronological trade stream."""
    if signal_count < 0:
        raise ValueError("BTC sweep-relaxation signal count must be non-negative")
    if not math.isfinite(partition_days) or partition_days <= 0.0:
        raise ValueError("BTC sweep-relaxation partition days must be positive")
    net_values = [trade.net_pnl_usd for trade in report.trades]
    largest = max((value for value in net_values if value > 0.0), default=None)
    exits = Counter(trade.exit_reason for trade in report.trades)
    return {
        "signal_episodes": signal_count,
        "submitted_entries": report.completed_trades,
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "trades_per_week": report.completed_trades * 7.0 / partition_days,
        "net_pnl_usd": report.net_pnl_usd,
        "return_pct": report.return_pct,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "total_fees_usd": report.total_fees_usd,
        "funding_cashflow_usd": report.funding_cashflow_usd,
        "largest_winner_usd": largest,
        "net_pnl_excluding_largest_winner_usd": (
            report.net_pnl_usd - largest if largest is not None else report.net_pnl_usd
        ),
        "exit_reasons": dict(sorted(exits.items())),
        "same_bar_ambiguities": sum(
            trade.same_bar_ambiguous for trade in report.trades
        ),
        "forced_end_exits": report.forced_end_exits,
        "gap_expired_entries": report.gap_expired_entries,
        "liquidations": report.liquidations,
        "insolvent": report.insolvent,
    }


def no_action_summary(partition_days: float) -> dict[str, object]:
    """Represent no route as a measured zero-opportunity baseline."""
    if not math.isfinite(partition_days) or partition_days <= 0.0:
        raise ValueError("BTC sweep-relaxation partition days must be positive")
    return {
        "arm": "no_action",
        "signal_episodes": 0,
        "submitted_entries": 0,
        "completed_trades": 0,
        "wins": 0,
        "losses": 0,
        "trades_per_week": 0.0,
        "net_pnl_usd": 0.0,
        "return_pct": 0.0,
        "profit_factor": None,
        "maximum_drawdown_pct": 0.0,
        "total_fees_usd": 0.0,
        "funding_cashflow_usd": 0.0,
        "largest_winner_usd": None,
        "net_pnl_excluding_largest_winner_usd": 0.0,
        "exit_reasons": {},
        "same_bar_ambiguities": 0,
        "forced_end_exits": 0,
        "gap_expired_entries": 0,
        "liquidations": 0,
        "insolvent": False,
    }


def evaluate_frozen_acceptance(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Apply the preregistered rule without tuning or live promotion."""
    indexed = _indexed_rows(rows)
    failures: list[str] = []
    _check_trade_counts(indexed, failures)
    for partition in ("validation", "pseudo_holdout"):
        for scenario in ("nominal", "stress"):
            _check_candidate_cell(indexed, partition, scenario, failures)
        _check_stress_increment(indexed, partition, failures)
    return {
        "accepted_for_next_validation_stage": not failures,
        "decision": (
            "advance_to_shared_portfolio_and_prospective_validation"
            if not failures
            else "reject_frozen_candidate"
        ),
        "failed_checks": failures,
        "live_promotion_authorized": False,
        "retuning_authorized": False,
    }


def _indexed_rows(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    output: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for row in rows:
        key = tuple(str(row.get(name, "")) for name in ("partition", "scenario", "arm"))
        if len(key) != 3 or not all(key):
            raise ValueError(
                "BTC sweep-relaxation acceptance row identity is incomplete"
            )
        if key in output:
            raise ValueError(f"duplicate BTC sweep-relaxation acceptance row: {key}")
        output[key] = row
    required = {
        (partition, scenario, arm)
        for partition in ("validation", "pseudo_holdout")
        for scenario in ("nominal", "stress")
        for arm in ("control", "candidate")
    }
    missing = sorted(required.difference(output))
    if missing:
        raise ValueError(f"BTC sweep-relaxation acceptance rows missing: {missing}")
    return output


def _check_trade_counts(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    failures: list[str],
) -> None:
    validation = _integer(
        rows[("validation", "nominal", "candidate")], "completed_trades"
    )
    holdout = _integer(
        rows[("pseudo_holdout", "nominal", "candidate")], "completed_trades"
    )
    if validation < 4:
        failures.append("validation_candidate_minimum_four_trades")
    if holdout < 4:
        failures.append("pseudo_holdout_candidate_minimum_four_trades")
    if validation + holdout < 12:
        failures.append("validation_plus_pseudo_holdout_minimum_twelve_trades")


def _check_candidate_cell(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    scenario: str,
    failures: list[str],
) -> None:
    row = rows[(partition, scenario, "candidate")]
    prefix = f"{partition}_{scenario}_candidate"
    if _number(row, "net_pnl_usd") <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(row):
        failures.append(f"{prefix}_profit_factor_above_one")
    if _number(row, "net_pnl_excluding_largest_winner_usd") <= 0.0:
        failures.append(f"{prefix}_positive_ex_largest")
    if _number(row, "maximum_drawdown_pct") < -10.0:
        failures.append(f"{prefix}_drawdown_floor")
    if _integer(row, "liquidations") != 0:
        failures.append(f"{prefix}_zero_liquidations")


def _check_stress_increment(
    rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    partition: str,
    failures: list[str],
) -> None:
    candidate = _number(rows[(partition, "stress", "candidate")], "net_pnl_usd")
    control = _number(rows[(partition, "stress", "control")], "net_pnl_usd")
    if candidate <= control:
        failures.append(f"{partition}_stress_candidate_exceeds_control")


def _profit_factor_above_one(row: Mapping[str, object]) -> bool:
    value = row.get("profit_factor")
    if value is None:
        return _integer(row, "wins") > 0 and _integer(row, "losses") == 0
    return _number(row, "profit_factor") > 1.0


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool):
        raise ValueError(f"BTC sweep-relaxation {key} must be numeric")
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"BTC sweep-relaxation {key} must be numeric") from error
    if not math.isfinite(numeric):
        raise ValueError(f"BTC sweep-relaxation {key} must be finite")
    return numeric


def _integer(row: Mapping[str, object], key: str) -> int:
    numeric = _number(row, key)
    if not numeric.is_integer() or numeric < 0.0:
        raise ValueError(f"BTC sweep-relaxation {key} must be non-negative integer")
    return int(numeric)
