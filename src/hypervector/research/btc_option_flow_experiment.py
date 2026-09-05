"""Complete frozen standalone experiment for the BTC option-flow candidate."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.btc_option_flow_acceptance import (
    evaluate_frozen_option_flow_acceptance,
)
from hypervector.research.btc_option_flow_controls import (
    BtcOptionFlowSweepControlReplay,
    direction_inverted_placebo_flow,
    evaluate_btc_option_flow_sweep_control,
)
from hypervector.research.btc_option_flow_replay import (
    BtcOptionFlowReplay,
    evaluate_btc_option_flow_replay,
)
from hypervector.research.btc_sweep_primary_relaxation import (
    build_btc_sweep_primary_relaxation_signals,
)
from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    no_action_summary,
    summarize_replay_report,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


_SCENARIOS = (
    ("nominal", 2.0, 0),
    ("stress", 5.0, 5),
    ("delayed", 10.0, 60),
)
_PARTITION_NAMES = {"development", "validation", "pseudo_holdout"}
_MINUTE = pd.Timedelta(minutes=1)
_EXIT_HORIZON = pd.Timedelta(hours=24)
_ScenarioResult = tuple[
    list[dict[str, object]], list[dict[str, object]], BtcOptionFlowReplay
]
_Arm = tuple[str, SharedPortfolioReport, int, dict[str, int]]


@dataclass(frozen=True)
class OptionFlowPartition:
    """One half-open candidate entry interval."""

    name: str
    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        """Require a named, increasing, timezone-aware interval."""
        start, end = pd.Timestamp(self.start), pd.Timestamp(self.end)
        if not self.name.strip():
            raise ValueError("option-flow partition name must be non-empty")
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError(
                "option-flow partition bounds must be aware and increasing"
            )

    @property
    def days(self) -> float:
        """Return the exact partition duration in days."""
        return (
            pd.Timestamp(self.end) - pd.Timestamp(self.start)
        ).total_seconds() / 86_400


@dataclass(frozen=True)
class BtcOptionFlowExperimentResult:
    """Immutable report content and complete trade-level sidecar rows."""

    report: dict[str, object]
    trade_rows: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class _SweepSignals:
    control: pd.DataFrame


class _SweepBuilder:
    def __init__(self, control: pd.DataFrame) -> None:
        self._control = control

    def __call__(self, _: pd.DataFrame) -> _SweepSignals:
        return _SweepSignals(self._control)


def run_frozen_option_flow_experiment(
    execution_bars: pd.DataFrame,
    signal_bars: pd.DataFrame,
    flow_signals: pd.DataFrame,
    *,
    partitions: Sequence[OptionFlowPartition],
    development_folds: Sequence[OptionFlowPartition],
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> BtcOptionFlowExperimentResult:
    """Run every preregistered standalone arm, scenario, partition, and fold."""
    ordered = _validated_partitions(partitions)
    folds = _validated_folds(development_folds, ordered[0])
    sweep = build_btc_sweep_primary_relaxation_signals(signal_bars).control
    placebo = direction_inverted_placebo_flow(flow_signals)
    summaries: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    nominal_oos: list[float] = []
    for partition in ordered:
        cells = _partition_cells(
            execution_bars,
            signal_bars,
            flow_signals,
            placebo,
            sweep,
            partition,
        )
        summaries.extend(cells[0])
        trades.extend(cells[1])
        if partition.name != "development":
            nominal_oos.extend(cells[2])
    fold_rows = _development_fold_rows(execution_bars, flow_signals, folds)
    oos = [row for row in summaries if row["partition"] != "development"]
    acceptance = evaluate_frozen_option_flow_acceptance(
        oos,
        fold_rows,
        pooled_oos_trade_net_pnl_usd=nominal_oos,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    return BtcOptionFlowExperimentResult(
        _report(summaries, fold_rows, acceptance), tuple(trades)
    )


def _partition_cells(
    execution: pd.DataFrame,
    signals: pd.DataFrame,
    flow: pd.DataFrame,
    placebo: pd.DataFrame,
    sweep: pd.DataFrame,
    partition: OptionFlowPartition,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[float]]:
    summaries: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    nominal_oos: list[float] = []
    partition_execution = execution_window(execution, partition)
    for scenario, slippage, delay in _SCENARIOS:
        scenario_rows, scenario_trades, candidate = _scenario_cells(
            partition_execution,
            signals,
            flow,
            placebo,
            sweep,
            partition,
            scenario,
            slippage,
            delay,
        )
        summaries.extend(scenario_rows)
        trades.extend(scenario_trades)
        if scenario == "nominal" and partition.name != "development":
            nominal_oos.extend(trade.net_pnl_usd for trade in candidate.report.trades)
    return summaries, trades, nominal_oos


def _scenario_cells(
    execution: pd.DataFrame,
    signals: pd.DataFrame,
    flow: pd.DataFrame,
    placebo: pd.DataFrame,
    sweep: pd.DataFrame,
    partition: OptionFlowPartition,
    scenario: str,
    slippage: float,
    delay: int,
) -> _ScenarioResult:
    candidate = _replay(execution, flow, partition, slippage, delay)
    inverted = _replay(execution, placebo, partition, slippage, delay)
    control = evaluate_btc_option_flow_sweep_control(
        execution,
        signals,
        slippage_bps_per_market_side=slippage,
        extra_delay_minutes=delay,
        entry_start_utc=partition.start,
        entry_end_utc=partition.end,
        signal_builder=_SweepBuilder(sweep),
    )
    arms = (
        (
            "candidate",
            candidate.report,
            candidate.long_signal_count,
            _flow_routing(candidate),
        ),
        (
            "direction_inverted_placebo",
            inverted.report,
            inverted.long_signal_count,
            _flow_routing(inverted),
        ),
        (
            "sweep_control",
            control.report,
            control.scheduled_signal_count,
            _sweep_routing(control),
        ),
    )
    rows, trades = _arm_output(partition, scenario, arms)
    return rows, trades, candidate


def _arm_output(
    partition: OptionFlowPartition, scenario: str, arms: Sequence[_Arm]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows = [
        _summary(partition, scenario, arm, report, count, routing)
        for arm, report, count, routing in arms
    ]
    rows.append(_no_action(partition, scenario))
    trades = [
        row
        for arm, report, _, _ in arms
        for row in _trade_rows(partition.name, scenario, arm, report)
    ]
    return rows, trades


def _replay(
    execution: pd.DataFrame,
    flow: pd.DataFrame,
    partition: OptionFlowPartition,
    slippage: float,
    delay: int,
) -> BtcOptionFlowReplay:
    return evaluate_btc_option_flow_replay(
        execution,
        flow,
        slippage_bps_per_market_side=slippage,
        extra_delay_minutes=delay,
        entry_start_utc=partition.start,
        entry_end_utc=partition.end,
    )


def _summary(
    partition: OptionFlowPartition,
    scenario: str,
    arm: str,
    report: SharedPortfolioReport,
    signal_count: int,
    routing: dict[str, int],
) -> dict[str, object]:
    return {
        "partition": partition.name,
        "scenario": scenario,
        "arm": arm,
        "routing": routing,
        **summarize_replay_report(
            report, signal_count=signal_count, partition_days=partition.days
        ),
    }


def _no_action(partition: OptionFlowPartition, scenario: str) -> dict[str, object]:
    summary = no_action_summary(partition.days)
    summary.pop("arm", None)
    return {
        "partition": partition.name,
        "scenario": scenario,
        "arm": "no_action",
        "routing": {
            "raw_signals": 0,
            "scheduled_signals": 0,
            "displaced_signals": 0,
            "partition_excluded_signals": 0,
        },
        **summary,
    }


def _flow_routing(replay: BtcOptionFlowReplay) -> dict[str, int]:
    return {
        "scheduled_long_signals": replay.long_signal_count,
        "scheduled_opposing_signals": replay.opposing_signal_count,
        "scheduled_signals": (replay.long_signal_count + replay.opposing_signal_count),
        "displaced_signals": replay.displaced_signal_count,
    }


def _sweep_routing(replay: BtcOptionFlowSweepControlReplay) -> dict[str, int]:
    return {
        "raw_signals": replay.raw_signal_count,
        "scheduled_signals": replay.scheduled_signal_count,
        "displaced_signals": replay.displaced_signal_count,
        "partition_excluded_signals": replay.partition_excluded_signal_count,
    }


def _trade_rows(
    partition: str,
    scenario: str,
    arm: str,
    report: SharedPortfolioReport,
) -> list[dict[str, object]]:
    return [
        {"partition": partition, "scenario": scenario, "arm": arm, **asdict(trade)}
        for trade in report.trades
    ]


def _development_fold_rows(
    execution: pd.DataFrame,
    flow: pd.DataFrame,
    folds: Sequence[OptionFlowPartition],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for fold_id, fold in enumerate(folds):
        replay = _replay(execution_window(execution, fold), flow, fold, 2.0, 0)
        rows.append(
            {
                "fold_id": fold_id,
                "entry_start_utc": pd.Timestamp(fold.start).isoformat(),
                "entry_end_exclusive_utc": pd.Timestamp(fold.end).isoformat(),
                "completed_trades": replay.report.completed_trades,
                "net_pnl_usd": replay.report.net_pnl_usd,
            }
        )
    return rows


def execution_window(
    execution: pd.DataFrame, partition: OptionFlowPartition
) -> pd.DataFrame:
    """Return the complete entry and exit horizon for one partition."""
    start = pd.Timestamp(partition.start).tz_convert("UTC") - _MINUTE
    end = pd.Timestamp(partition.end).tz_convert("UTC") + _EXIT_HORIZON
    output = execution.loc[(execution.index >= start) & (execution.index < end)]
    if output.empty or output.index[0] > start or output.index[-1] < end - _MINUTE:
        raise ValueError(
            f"option-flow execution horizon is incomplete: {partition.name}"
        )
    return output


def _validated_partitions(
    values: Sequence[OptionFlowPartition],
) -> tuple[OptionFlowPartition, ...]:
    indexed = {value.name: value for value in values}
    if len(indexed) != len(values) or set(indexed) != _PARTITION_NAMES:
        raise ValueError("option-flow experiment requires three unique partitions")
    ordered = tuple(
        indexed[name] for name in ("development", "validation", "pseudo_holdout")
    )
    if any(not math.isfinite(value.days) or value.days <= 0.0 for value in ordered):
        raise ValueError("option-flow partition duration is invalid")
    return ordered


def _validated_folds(
    folds: Sequence[OptionFlowPartition], development: OptionFlowPartition
) -> tuple[OptionFlowPartition, ...]:
    if len(folds) != 5:
        raise ValueError("option-flow experiment requires five development folds")
    ordered = tuple(folds)
    if ordered[0].start != development.start or ordered[-1].end != development.end:
        raise ValueError("option-flow development folds do not span development")
    for left, right in zip(ordered[:-1], ordered[1:], strict=True):
        if left.end != right.start:
            raise ValueError("option-flow development folds are not contiguous")
    return ordered


def _report(
    summaries: list[dict[str, object]],
    folds: list[dict[str, object]],
    acceptance: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "v58_btc_deribit_option_flow_experiment_v1",
        "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "live_configuration_changed": False,
            "orders_supported": False,
        },
        "summary_rows": summaries,
        "development_fold_rows": folds,
        "acceptance": acceptance,
        "limitations": (
            "historical price partitions were previously opened by other research",
            "one-minute OHLC uses adverse stop-first ordering for ambiguous touches",
            "bar replay cannot establish exact queue position, market impact, or latency",
            "a historical pass authorizes only future-only report capture",
        ),
    }
