"""Causal, report-only replay primitives for the HYPE five-minute impulse fade."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from hypervector.research.hype_impulse_5m_signals import (
    aggregate_completed_five_minute_bars,
    build_impulse_signals,
    validate_five_minute_bars,
)

__all__ = [
    "HypeImpulseConfig",
    "HypeImpulseReplay",
    "HypeImpulseTrade",
    "aggregate_completed_five_minute_bars",
    "build_impulse_signals",
    "maximum_hold_bars",
    "replay_impulse_signals",
]

Side = Literal["long", "short"]
ExitReason = Literal["stop", "target", "maximum_hold"]
_BAR_DURATION = pd.Timedelta(minutes=5)
_BAR_MINUTES = 5


@dataclass(frozen=True)
class HypeImpulseConfig:
    """Frozen signal and lifecycle parameters for the candidate replay."""

    maximum_close_vs_ema21_bps: float = -20.0
    maximum_di_delta: float = -40.0
    maximum_roc_5_pct: float = -0.2
    take_profit_atr_multiple: float = 3.999439
    stop_loss_atr_multiple: float = 0.500732
    maximum_hold_minutes: int = 23
    clean_history_bars: int = 60

    def __post_init__(self) -> None:
        """Reject lifecycle settings that cannot produce a causal replay."""
        if self.take_profit_atr_multiple <= 0 or self.stop_loss_atr_multiple <= 0:
            raise ValueError("HYPE impulse ATR barrier multiples must be positive")
        if self.maximum_hold_minutes <= 0:
            raise ValueError("HYPE impulse maximum hold minutes must be positive")
        if self.clean_history_bars < 21:
            raise ValueError("HYPE impulse clean history must cover at least 21 bars")


@dataclass(frozen=True)
class HypeImpulseTrade:
    """One resolved report-only HYPE impulse lifecycle."""

    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: Side
    entry_price: float
    exit_price: float
    exit_reason: ExitReason
    holding_minutes: int
    gross_bps: float
    cost_bps: float
    funding_bps: float
    net_bps: float


@dataclass(frozen=True)
class HypeImpulseReplay:
    """Resolved trades and explicit technical censor counts."""

    trades: tuple[HypeImpulseTrade, ...]
    candidate_signals: int
    gap_censored: int
    boundary_censored: int


def maximum_hold_bars(config: HypeImpulseConfig) -> int:
    """Convert a minute ceiling to the first observable completed 5m close."""
    return math.ceil(config.maximum_hold_minutes / _BAR_MINUTES)


def replay_impulse_signals(
    bars: pd.DataFrame,
    signals: pd.Series,
    atr_bps: pd.Series,
    funding_rates: pd.Series,
    *,
    config: HypeImpulseConfig,
    side: Side,
    round_trip_cost_bps: float,
    partition_start: pd.Timestamp,
    partition_end: pd.Timestamp,
) -> HypeImpulseReplay:
    """Replay next-bar entries with barriers, funding, and half-open bounds."""
    frame = validate_five_minute_bars(bars)
    _require_side(side)
    _validate_replay_inputs(frame, signals, atr_bps, funding_rates)
    start, end = _partition_bounds(partition_start, partition_end)
    signal_positions = _signal_positions(frame, signals, start, end)
    state = _ReplayAccumulator(candidate_signals=len(signal_positions))
    next_signal_position = 0
    for signal_position in signal_positions:
        if signal_position < next_signal_position:
            continue
        outcome = _resolve_candidate(
            frame,
            atr_bps,
            funding_rates,
            config,
            side,
            round_trip_cost_bps,
            signal_position,
            end,
        )
        next_signal_position = state.record(signal_position, outcome)
    return state.result()


@dataclass(frozen=True)
class _ResolvedCandidate:
    trade: HypeImpulseTrade | None
    exit_position: int
    censor: Literal["gap", "boundary"] | None = None


@dataclass
class _ReplayAccumulator:
    candidate_signals: int
    trades: list[HypeImpulseTrade] | None = None
    gap_censored: int = 0
    boundary_censored: int = 0

    def __post_init__(self) -> None:
        self.trades = []

    def record(self, signal_position: int, outcome: _ResolvedCandidate) -> int:
        """Record one candidate and return the next admissible signal position."""
        if outcome.censor == "gap":
            self.gap_censored += 1
        elif outcome.censor == "boundary":
            self.boundary_censored += 1
        elif outcome.trade is not None and self.trades is not None:
            self.trades.append(outcome.trade)
            return outcome.exit_position
        return signal_position + 1

    def result(self) -> HypeImpulseReplay:
        """Freeze accumulated replay evidence."""
        return HypeImpulseReplay(
            trades=tuple(self.trades or []),
            candidate_signals=self.candidate_signals,
            gap_censored=self.gap_censored,
            boundary_censored=self.boundary_censored,
        )


def _resolve_candidate(
    frame: pd.DataFrame,
    atr_bps: pd.Series,
    funding: pd.Series,
    config: HypeImpulseConfig,
    side: Side,
    cost_bps: float,
    signal_position: int,
    partition_end: pd.Timestamp,
) -> _ResolvedCandidate:
    entry_position = signal_position + 1
    scheduled_exit = entry_position + maximum_hold_bars(config) - 1
    last_completed = _last_completed_position(frame, partition_end)
    exit_position = min(scheduled_exit, len(frame) - 1, last_completed)
    if entry_position > exit_position:
        return _ResolvedCandidate(None, exit_position, "boundary")
    path = frame.iloc[entry_position : exit_position + 1]
    if bool(path["contains_gap_fill"].any()):
        return _ResolvedCandidate(None, exit_position, "gap")
    trade, actual_exit = _resolved_trade(
        frame,
        atr_bps,
        funding,
        config,
        side,
        cost_bps,
        signal_position,
        entry_position,
        exit_position,
    )
    if trade.exit_reason == "maximum_hold" and exit_position < scheduled_exit:
        return _ResolvedCandidate(None, exit_position, "boundary")
    return _ResolvedCandidate(trade, actual_exit)


def _last_completed_position(frame: pd.DataFrame, partition_end: pd.Timestamp) -> int:
    completed = frame["timestamp"].add(_BAR_DURATION).le(partition_end)
    positions = frame.index[completed]
    return int(positions[-1]) if len(positions) else -1


def _resolved_trade(
    frame: pd.DataFrame,
    atr_bps: pd.Series,
    funding: pd.Series,
    config: HypeImpulseConfig,
    side: Side,
    cost_bps: float,
    signal_position: int,
    entry_position: int,
    maximum_exit_position: int,
) -> tuple[HypeImpulseTrade, int]:
    distance = float(atr_bps.iloc[signal_position])
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("signaled HYPE impulse ATR basis points must be positive")
    entry_price = float(frame.iloc[entry_position]["open"])
    stop, target = _barriers(entry_price, distance, config, side)
    exit_price, reason, exit_position = _find_exit(
        frame, entry_position, maximum_exit_position, stop, target, side
    )
    return _trade_record(
        frame,
        funding,
        side,
        signal_position,
        entry_position,
        exit_position,
        entry_price,
        exit_price,
        reason,
        cost_bps,
    ), exit_position


def _find_exit(
    frame: pd.DataFrame,
    entry_position: int,
    maximum_exit_position: int,
    stop: float,
    target: float,
    side: Side,
) -> tuple[float, ExitReason, int]:
    for position in range(entry_position, maximum_exit_position + 1):
        row = frame.iloc[position]
        stop_hit, target_hit = _barrier_hits(row, stop, target, side)
        if stop_hit:
            return stop, "stop", position
        if target_hit:
            return target, "target", position
    return (
        float(frame.iloc[maximum_exit_position]["close"]),
        "maximum_hold",
        maximum_exit_position,
    )


def _trade_record(
    frame: pd.DataFrame,
    funding: pd.Series,
    side: Side,
    signal_position: int,
    entry_position: int,
    exit_position: int,
    entry_price: float,
    exit_price: float,
    reason: ExitReason,
    cost_bps: float,
) -> HypeImpulseTrade:
    entry_time = pd.Timestamp(frame.iloc[entry_position]["timestamp"])
    exit_time = pd.Timestamp(frame.iloc[exit_position]["timestamp"]) + _BAR_DURATION
    sign = 1.0 if side == "long" else -1.0
    gross = sign * (exit_price / entry_price - 1.0) * 10_000.0
    funding_bps = _funding_bps(funding, entry_time, exit_time, side)
    return HypeImpulseTrade(
        signal_time=pd.Timestamp(frame.iloc[signal_position]["timestamp"]),
        entry_time=entry_time,
        exit_time=exit_time,
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        exit_reason=reason,
        holding_minutes=int((exit_time - entry_time).total_seconds() // 60),
        gross_bps=gross,
        cost_bps=cost_bps,
        funding_bps=funding_bps,
        net_bps=gross - cost_bps + funding_bps,
    )


def _validate_replay_inputs(
    frame: pd.DataFrame,
    signals: pd.Series,
    atr_bps: pd.Series,
    funding: pd.Series,
) -> None:
    if len(signals) != len(frame) or len(atr_bps) != len(frame):
        raise ValueError("HYPE impulse signals and ATR must align with bars")
    if not signals.index.equals(frame.index) or not atr_bps.index.equals(frame.index):
        raise ValueError("HYPE impulse signals and ATR indexes must match bars")
    if not funding.empty:
        if not isinstance(funding.index, pd.DatetimeIndex) or funding.index.tz is None:
            raise ValueError("HYPE funding index must be timezone-aware")
        if not funding.index.is_monotonic_increasing or funding.index.has_duplicates:
            raise ValueError("HYPE funding rows must be ordered and unique")


def _barriers(
    entry: float,
    atr_bps: float,
    config: HypeImpulseConfig,
    side: Side,
) -> tuple[float, float]:
    stop_fraction = atr_bps * config.stop_loss_atr_multiple / 10_000.0
    target_fraction = atr_bps * config.take_profit_atr_multiple / 10_000.0
    if side == "long":
        return entry * (1.0 - stop_fraction), entry * (1.0 + target_fraction)
    return entry * (1.0 + stop_fraction), entry * (1.0 - target_fraction)


def _barrier_hits(
    row: pd.Series, stop: float, target: float, side: Side
) -> tuple[bool, bool]:
    if side == "long":
        return float(row["low"]) <= stop, float(row["high"]) >= target
    return float(row["high"]) >= stop, float(row["low"]) <= target


def _funding_bps(
    funding: pd.Series,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    side: Side,
) -> float:
    if funding.empty:
        return 0.0
    covered = funding.loc[(funding.index > entry_time) & (funding.index <= exit_time)]
    sign = -1.0 if side == "long" else 1.0
    return sign * float(covered.sum()) * 10_000.0


def _signal_positions(
    frame: pd.DataFrame,
    signals: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[int]:
    timestamps = frame["timestamp"]
    mask = signals.astype(bool) & timestamps.ge(start) & timestamps.lt(end)
    return [int(position) for position in frame.index[mask]]


def _partition_bounds(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    normalized_start = pd.Timestamp(start)
    normalized_end = pd.Timestamp(end)
    if normalized_start.tz is None or normalized_end.tz is None:
        raise ValueError("HYPE replay partition bounds must be timezone-aware")
    if normalized_start >= normalized_end:
        raise ValueError("HYPE replay partition start must precede end")
    return normalized_start, normalized_end


def _require_side(side: str) -> None:
    if side not in {"long", "short"}:
        raise ValueError("HYPE impulse side must be long or short")
