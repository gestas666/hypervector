"""Report-only taker-entry parity screen for the BTC liquidity-sweep long."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Mapping

import pandas as pd

Partition = Literal["development", "forward"]
Outcome = Literal["win", "loss", "timeout"]
Record = Mapping[str, object]
_MAXIMUM_MARK_GAP_MS = 120_000


@dataclass(frozen=True)
class SignalPathObservation:
    """One causal entry-delay and barrier path for a frozen signal."""

    signal_time_utc: str
    partition: Partition
    entry_delay_seconds: int
    entry_time_ms: int
    entry_ask: float
    stop_time_ms: int | None
    target_times_ms: Mapping[float, int | None]
    maximum_mark_gap_ms: int
    maximum_mark_gap_by_target_ms: Mapping[float, int]

    def __post_init__(self) -> None:
        """Reject incomplete, noncausal, or nonfinite path evidence."""
        if not self.signal_time_utc.strip():
            raise ValueError("signal time must be non-empty")
        if self.partition not in {"development", "forward"}:
            raise ValueError("partition must be development or forward")
        _nonnegative_integer(self.entry_delay_seconds, "entry delay")
        _positive_integer(self.entry_time_ms, "entry time")
        _positive(self.entry_ask, "entry ask")
        _optional_time(self.stop_time_ms, self.entry_time_ms, "stop time")
        _nonnegative_integer(self.maximum_mark_gap_ms, "maximum mark gap")
        for target, timestamp in self.target_times_ms.items():
            _positive(target, "target bps")
            _optional_time(timestamp, self.entry_time_ms, "target time")
        if set(self.maximum_mark_gap_by_target_ms) != set(self.target_times_ms):
            raise ValueError("target mark-gap evidence must match the target grid")
        for value in self.maximum_mark_gap_by_target_ms.values():
            _nonnegative_integer(value, "target maximum mark gap")


@dataclass(frozen=True)
class TakerFriction:
    """Conservative target and stop path costs in basis points."""

    win_bps: float
    loss_bps: float

    def __post_init__(self) -> None:
        """Require finite nonnegative friction on both lifecycle paths."""
        _nonnegative(self.win_bps, "win friction")
        _nonnegative(self.loss_bps, "loss friction")


def derive_signal_paths(
    *,
    signal_time_utc: str,
    partition: Partition,
    books: pd.DataFrame,
    marks: pd.DataFrame,
    entry_delays_seconds: tuple[int, ...],
    target_grid_bps: tuple[float, ...],
    stop_bps: float,
    evidence_end_ms: int,
) -> tuple[SignalPathObservation, ...]:
    """Derive causal taker entries and barrier times from exact BBO and mark rows."""
    signal_ms = _timestamp_ms(signal_time_utc)
    book_rows = _market_frame(books, ("best_bid", "best_ask"), "book")
    mark_rows = _market_frame(marks, ("mark_price",), "mark")
    if evidence_end_ms <= signal_ms:
        raise ValueError("evidence end must follow the signal")
    paths = [
        _derive_delay_path(
            signal_time_utc,
            partition,
            signal_ms,
            delay,
            target_grid_bps,
            stop_bps,
            evidence_end_ms,
            book_rows,
            mark_rows,
        )
        for delay in entry_delays_seconds
    ]
    return tuple(paths)


def _derive_delay_path(
    signal_time_utc: str,
    partition: Partition,
    signal_ms: int,
    delay: int,
    targets: tuple[float, ...],
    stop_bps: float,
    end_ms: int,
    books: pd.DataFrame,
    marks: pd.DataFrame,
) -> SignalPathObservation:
    _nonnegative_integer(delay, "entry delay")
    eligible = books.loc[
        books["ts_ms"].between(signal_ms + delay * 1_000, end_ms, inclusive="left")
    ]
    if eligible.empty:
        raise ValueError("book evidence does not contain a causal entry")
    entry = eligible.iloc[0]
    entry_ms, ask = int(entry["ts_ms"]), float(entry["best_ask"])
    mark_path = marks.loc[marks["ts_ms"].between(entry_ms, end_ms, inclusive="left")]
    if mark_path.empty:
        raise ValueError("mark evidence does not cover the entry path")
    stop_time = _first_time(mark_path, "mark_price", ask * (1.0 - stop_bps / 10_000))
    target_times = {
        target: _first_time(
            eligible, "best_bid", ask * (1.0 + target / 10_000), greater=True
        )
        for target in targets
    }
    target_gaps = _target_mark_gaps(
        mark_path, target_times, stop_time, entry_ms, end_ms
    )
    return SignalPathObservation(
        signal_time_utc,
        partition,
        delay,
        entry_ms,
        ask,
        stop_time,
        target_times,
        max(target_gaps.values()),
        target_gaps,
    )


def _market_frame(
    frame: pd.DataFrame, value_columns: tuple[str, ...], label: str
) -> pd.DataFrame:
    required = {"ts_ms", *value_columns}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} evidence missing columns: {sorted(missing)}")
    result = frame.loc[:, ["ts_ms", *value_columns]].copy()
    for column in result.columns:
        result[column] = pd.to_numeric(result[column], errors="raise")
    if result.isna().any().any() or (result[list(value_columns)] <= 0.0).any().any():
        raise ValueError(f"{label} evidence must contain positive finite values")
    return result.sort_values("ts_ms").drop_duplicates().reset_index(drop=True)


def _first_time(
    frame: pd.DataFrame,
    column: str,
    barrier: float,
    *,
    greater: bool = False,
) -> int | None:
    selected = frame.loc[
        frame[column] >= barrier if greater else frame[column] <= barrier
    ]
    return None if selected.empty else int(selected.iloc[0]["ts_ms"])


def _target_mark_gaps(
    marks: pd.DataFrame,
    target_times: Mapping[float, int | None],
    stop_time: int | None,
    entry_ms: int,
    evidence_end_ms: int,
) -> dict[float, int]:
    result: dict[float, int] = {}
    for target, target_time in target_times.items():
        path_end = (
            target_time
            if target_time is not None
            and (stop_time is None or target_time < stop_time)
            else stop_time or evidence_end_ms
        )
        resolved = marks.loc[marks["ts_ms"] <= path_end]
        result[target] = _maximum_gap(resolved["ts_ms"], entry_ms, path_end)
    return result


def _maximum_gap(times: pd.Series, start_ms: int, end_ms: int) -> int:
    values = [start_ms, *(int(value) for value in times), end_ms]
    return max(right - left for left, right in zip(values, values[1:]))


def _timestamp_ms(value: str) -> int:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("signal timestamp must include a UTC offset")
    return int(parsed.tz_convert("UTC").timestamp() * 1_000)


def build_taker_parity_report(
    paths: tuple[SignalPathObservation, ...],
    *,
    target_grid_bps: tuple[float, ...],
    stop_bps: float,
    friction: TakerFriction,
) -> dict[str, object]:
    """Select a development-stable target and delay without live authority."""
    _validate_inputs(paths, target_grid_bps, stop_bps)
    delays = tuple(sorted({path.entry_delay_seconds for path in paths}))
    summaries = _summaries(paths, target_grid_bps, delays, stop_bps, friction)
    target = _select_target(summaries, target_grid_bps, delays[0])
    delay = _select_delay(summaries, delays, target)
    development = summaries[("development", delay, target)]
    forward = summaries[("forward", delay, target)]
    unresolved = _unresolved_signals(paths, delay, target)
    return {
        "schema_version": "btc_liquidity_sweep_taker_parity_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "contract": {
            "entry_source": "first_causal_bbo_ask_after_delay",
            "stop_trigger_source": "causal_hyperliquid_mark",
            "target_execution_source": "causal_bbo_bid",
            "stop_bps": stop_bps,
            "target_grid_bps": list(target_grid_bps),
            "entry_delay_grid_seconds": list(delays),
            "maximum_mark_gap_ms": _MAXIMUM_MARK_GAP_MS,
        },
        "grid": _grid_rows(summaries),
        "selection": _selection_payload(
            target, delay, development, forward, unresolved, stop_bps, friction
        ),
        "limitations": [
            "Target and entry-delay selection used the development paths.",
            "The forward partition contains one signal and cannot prove repeatability.",
            "Barrier timing does not model queueing because live entry is taker IOC.",
        ],
    }


def _selection_payload(
    target: float,
    delay: int,
    development: Record,
    forward: Record,
    unresolved: Mapping[str, list[str]],
    stop_bps: float,
    friction: TakerFriction,
) -> dict[str, object]:
    return {
        "target_bps": target,
        "maximum_entry_delay_seconds": delay,
        "development": _counts(development),
        "forward": _counts(forward),
        "development_selected": True,
        "forward_sample_count": int(forward["sample_count"]),
        "confidence": "low",
        "development_path_resolved": not bool(unresolved["development"]),
        "forward_path_resolved": not bool(unresolved["forward"]),
        "unresolved_development_signals": unresolved["development"],
        "unresolved_forward_signals": unresolved["forward"],
        "friction_adjusted_breakeven_win_rate": _breakeven(target, stop_bps, friction),
    }


def _validate_inputs(
    paths: tuple[SignalPathObservation, ...],
    targets: tuple[float, ...],
    stop_bps: float,
) -> None:
    if not paths or len(targets) < 2:
        raise ValueError("parity screen requires paths and at least two targets")
    _positive(stop_bps, "stop bps")
    if len(set(targets)) != len(targets) or tuple(sorted(targets)) != targets:
        raise ValueError("target grid must be unique and increasing")
    required_targets = set(targets)
    if any(set(path.target_times_ms) != required_targets for path in paths):
        raise ValueError("every path must cover the exact target grid")
    _require_rectangular(paths)


def _unresolved_signals(
    paths: tuple[SignalPathObservation, ...], delay: int, target: float
) -> dict[str, list[str]]:
    return {
        partition: sorted(
            {
                path.signal_time_utc
                for path in paths
                if path.partition == partition
                and path.entry_delay_seconds == delay
                and path.maximum_mark_gap_by_target_ms[target] > _MAXIMUM_MARK_GAP_MS
            }
        )
        for partition in ("development", "forward")
    }


def _require_rectangular(paths: tuple[SignalPathObservation, ...]) -> None:
    delays = {path.entry_delay_seconds for path in paths}
    groups: dict[tuple[Partition, str], set[int]] = {}
    for path in paths:
        key = (path.partition, path.signal_time_utc)
        if path.entry_delay_seconds in groups.setdefault(key, set()):
            raise ValueError("path grid contains a duplicate signal delay")
        groups[key].add(path.entry_delay_seconds)
    if {partition for partition, _ in groups} != {"development", "forward"}:
        raise ValueError("path grid must contain development and forward partitions")
    if any(group != delays for group in groups.values()):
        raise ValueError("path grid must be rectangular across every signal and delay")


def _summaries(
    paths: tuple[SignalPathObservation, ...],
    targets: tuple[float, ...],
    delays: tuple[int, ...],
    stop_bps: float,
    friction: TakerFriction,
) -> dict[tuple[Partition, int, float], dict[str, float | int]]:
    summaries: dict[tuple[Partition, int, float], dict[str, float | int]] = {}
    for partition in ("development", "forward"):
        for delay in delays:
            selected = tuple(
                path
                for path in paths
                if path.partition == partition and path.entry_delay_seconds == delay
            )
            for target in targets:
                summaries[(partition, delay, target)] = _summary(
                    selected, target, stop_bps, friction
                )
    return summaries


def _summary(
    paths: tuple[SignalPathObservation, ...],
    target: float,
    stop: float,
    friction: TakerFriction,
) -> dict[str, float | int]:
    outcomes = tuple(_outcome(path, target) for path in paths)
    wins, losses = outcomes.count("win"), outcomes.count("loss")
    timeouts = outcomes.count("timeout")
    net = wins * (target - friction.win_bps) - losses * (stop + friction.loss_bps)
    return {
        "sample_count": len(paths),
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "mean_net_bps": net / len(paths),
    }


def _outcome(path: SignalPathObservation, target: float) -> Outcome:
    target_time = path.target_times_ms[target]
    if target_time is not None and (
        path.stop_time_ms is None or target_time < path.stop_time_ms
    ):
        return "win"
    return "loss" if path.stop_time_ms is not None else "timeout"


def _select_target(
    summaries: Mapping[tuple[Partition, int, float], Mapping[str, float | int]],
    targets: tuple[float, ...],
    delay: int,
) -> float:
    baseline = _counts(summaries[("development", delay, targets[0])])
    stable = [
        target
        for target in targets
        if _counts(summaries[("development", delay, target)]) == baseline
    ]
    if not stable:
        raise RuntimeError("no stable development target exists")
    return max(stable)


def _select_delay(
    summaries: Mapping[tuple[Partition, int, float], Mapping[str, float | int]],
    delays: tuple[int, ...],
    target: float,
) -> int:
    baseline = _counts(summaries[("development", delays[0], target)])
    stable = [
        delay
        for delay in delays
        if _counts(summaries[("development", delay, target)]) == baseline
    ]
    if not stable:
        raise RuntimeError("no stable development entry delay exists")
    return max(stable)


def _grid_rows(
    summaries: Mapping[tuple[Partition, int, float], Mapping[str, float | int]],
) -> list[dict[str, object]]:
    return [
        {
            "partition": partition,
            "entry_delay_seconds": delay,
            "target_bps": target,
            **summary,
        }
        for (partition, delay, target), summary in sorted(summaries.items())
    ]


def _counts(summary: Mapping[str, float | int]) -> dict[str, int]:
    return {name: int(summary[name]) for name in ("wins", "losses", "timeouts")}


def _breakeven(target: float, stop: float, friction: TakerFriction) -> float:
    win = target - friction.win_bps
    loss = stop + friction.loss_bps
    if win <= 0.0:
        raise ValueError("selected target does not clear friction")
    return loss / (loss + win)


def _optional_time(value: int | None, earliest: int, label: str) -> None:
    if value is None:
        return
    _positive_integer(value, label)
    if value < earliest:
        raise ValueError(f"{label} must not precede entry")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
