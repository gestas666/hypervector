"""Independent causal barrier outcomes for Hypervelocity regime candidates."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import median
from typing import Literal

import pandas as pd

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)

OutcomeStatus = Literal["target_completed", "liquidated", "unresolved"]


@dataclass(frozen=True)
class CandidateBarrierConfig:
    """Explicit assumptions for independent signal-outcome screening."""

    initial_equity: float = 10_000.0
    margin_fraction: float = 0.70
    leverage: float = 40.0
    target_margin_pct: float = 8.0
    maker_fee_rate: float = 0.00015
    liquidation_fee_rate: float = 0.00045

    def __post_init__(self) -> None:
        for name in ("initial_equity", "margin_fraction", "leverage"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.margin_fraction > 1.0:
            raise ValueError("margin_fraction must be <= 1")
        if not 0.0 < self.target_margin_pct:
            raise ValueError("target_margin_pct must be positive")
        for name in ("maker_fee_rate", "liquidation_fee_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value < 1.0:
                raise ValueError(f"{name} must be within [0, 1)")


@dataclass(frozen=True)
class CandidatePositionTerms:
    """Sized position and price barriers for one candidate entry."""

    margin: float
    notional: float
    quantity: float
    target_price: float
    liquidation_price: float
    entry_fee: float


@dataclass(frozen=True)
class CandidateBarrierOutcome:
    """One independent entry signal and its first observed price barrier."""

    direction: Literal["long", "short"]
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str | None
    status: OutcomeStatus
    entry_price: float
    target_price: float
    liquidation_price: float
    fees_usd: float
    net_pnl_usd: float
    hold_seconds: float | None
    adverse_excursion_margin_pct: float
    same_bar_ambiguous: bool


@dataclass(frozen=True)
class CandidateBarrierReport:
    """Aggregate independent outcomes without pretending they are fills."""

    total_signals: int
    targets_completed: int
    liquidations: int
    unresolved: int
    ambiguous_barriers: int
    net_pnl_usd: float
    median_hold_seconds: float | None
    median_adverse_excursion_margin_pct: float | None
    outcomes: tuple[CandidateBarrierOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe diagnostic report."""
        return asdict(self)


def _validate_inputs(bars: pd.DataFrame, decisions: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"candidate bars missing columns: {sorted(missing)}")
    if "entry_direction" not in decisions:
        raise ValueError("candidate decisions require entry_direction")
    if not bars.index.equals(decisions.index):
        raise ValueError("candidate bars and decisions require the same index")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("candidate bars require a DatetimeIndex")


def _signal_positions(decisions: pd.DataFrame) -> list[int]:
    directions = decisions["entry_direction"].astype(object)
    valid = directions.isin(["long", "short"])
    starts = valid & directions.ne(directions.shift())
    return [int(position) for position in starts.to_numpy().nonzero()[0]]


def position_terms(
    direction: Literal["long", "short"],
    entry_price: float,
    equity: float,
    config: CandidateBarrierConfig,
) -> CandidatePositionTerms:
    """Return fixed-contract sizing, fees, target, and liquidation boundary."""
    margin = equity * config.margin_fraction
    notional = margin * config.leverage
    quantity = notional / entry_price
    entry_fee = notional * config.maker_fee_rate
    price_fraction = config.target_margin_pct / 100.0 / config.leverage
    target = entry_price * (
        1.0 + price_fraction if direction == "long" else 1.0 - price_fraction
    )
    position = IsolatedMarginPosition(
        symbol="BTC",
        side=direction,
        quantity=quantity,
        entry_price=entry_price,
        isolated_margin=margin,
        maintenance_rate=maintenance_rate_for_max_leverage(config.leverage),
        fees_paid_usd=entry_fee,
    )
    return CandidatePositionTerms(
        margin,
        notional,
        quantity,
        target,
        position.liquidation_price(),
        entry_fee,
    )


def _barrier_flags(
    direction: Literal["long", "short"],
    high: float,
    low: float,
    target: float,
    liquidation: float,
) -> tuple[bool, bool]:
    if direction == "long":
        return high >= target, low <= liquidation
    return low <= target, high >= liquidation


def _adverse_excursion(
    direction: Literal["long", "short"],
    entry_price: float,
    quantity: float,
    margin: float,
    highs: list[float],
    lows: list[float],
) -> float:
    adverse_price = min(lows) if direction == "long" else max(highs)
    sign = 1.0 if direction == "long" else -1.0
    adverse_pnl = sign * quantity * (adverse_price - entry_price)
    return 100.0 * adverse_pnl / margin


def _evaluate_signal(
    bars: pd.DataFrame,
    signal_position: int,
    direction: Literal["long", "short"],
    config: CandidateBarrierConfig,
) -> CandidateBarrierOutcome | None:
    entry_position = signal_position + 1
    if entry_position >= len(bars):
        return None
    entry_price = float(bars["open"].iloc[entry_position])
    terms = position_terms(direction, entry_price, config.initial_equity, config)
    return _scan_barriers(
        bars,
        signal_position,
        entry_position,
        direction,
        entry_price,
        terms.margin,
        terms.notional,
        terms.quantity,
        terms.target_price,
        terms.liquidation_price,
        config,
    )


def _scan_barriers(
    bars: pd.DataFrame,
    signal_position: int,
    entry_position: int,
    direction: Literal["long", "short"],
    entry_price: float,
    margin: float,
    notional: float,
    quantity: float,
    target: float,
    liquidation: float,
    config: CandidateBarrierConfig,
) -> CandidateBarrierOutcome:
    highs: list[float] = []
    lows: list[float] = []
    for position in range(entry_position, len(bars)):
        high, low = (
            float(bars["high"].iloc[position]),
            float(bars["low"].iloc[position]),
        )
        highs.append(high)
        lows.append(low)
        target_hit, liquidation_hit = _barrier_flags(
            direction, high, low, target, liquidation
        )
        if target_hit or liquidation_hit:
            status: OutcomeStatus = (
                "liquidated" if liquidation_hit else "target_completed"
            )
            ambiguous = target_hit and liquidation_hit
            return _resolved_outcome(
                bars,
                signal_position,
                entry_position,
                position,
                direction,
                entry_price,
                margin,
                notional,
                quantity,
                target,
                liquidation,
                status,
                ambiguous,
                highs,
                lows,
                config,
            )
    return _unresolved_outcome(
        bars,
        signal_position,
        entry_position,
        direction,
        entry_price,
        margin,
        quantity,
        target,
        liquidation,
        highs,
        lows,
    )


def _resolved_outcome(
    bars: pd.DataFrame,
    signal_position: int,
    entry_position: int,
    exit_position: int,
    direction: Literal["long", "short"],
    entry_price: float,
    margin: float,
    notional: float,
    quantity: float,
    target: float,
    liquidation: float,
    status: OutcomeStatus,
    ambiguous: bool,
    highs: list[float],
    lows: list[float],
    config: CandidateBarrierConfig,
) -> CandidateBarrierOutcome:
    entry_fee = notional * config.maker_fee_rate
    if status == "liquidated":
        exit_price = liquidation
        gross = quantity * (exit_price - entry_price)
        if direction == "short":
            gross = -gross
        exit_fee = quantity * exit_price * config.liquidation_fee_rate
    else:
        gross = abs(target - entry_price) * quantity
        exit_fee = quantity * target * config.maker_fee_rate
    fees = entry_fee + exit_fee
    net_pnl = gross - fees
    hold = (bars.index[exit_position] - bars.index[entry_position]).total_seconds()
    return CandidateBarrierOutcome(
        direction,
        bars.index[signal_position].isoformat(),
        bars.index[entry_position].isoformat(),
        bars.index[exit_position].isoformat(),
        status,
        entry_price,
        target,
        liquidation,
        fees,
        net_pnl,
        hold,
        _adverse_excursion(direction, entry_price, quantity, margin, highs, lows),
        ambiguous,
    )


def _unresolved_outcome(
    bars: pd.DataFrame,
    signal_position: int,
    entry_position: int,
    direction: Literal["long", "short"],
    entry_price: float,
    margin: float,
    quantity: float,
    target: float,
    liquidation: float,
    highs: list[float],
    lows: list[float],
) -> CandidateBarrierOutcome:
    return CandidateBarrierOutcome(
        direction,
        bars.index[signal_position].isoformat(),
        bars.index[entry_position].isoformat(),
        None,
        "unresolved",
        entry_price,
        target,
        liquidation,
        0.0,
        0.0,
        None,
        _adverse_excursion(direction, entry_price, quantity, margin, highs, lows),
        False,
    )


def evaluate_independent_barriers(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    config: CandidateBarrierConfig | None = None,
) -> CandidateBarrierReport:
    """Evaluate every directional episode independently from its next bar open."""
    _validate_inputs(bars, decisions)
    cfg = config or CandidateBarrierConfig()
    outcomes = tuple(
        outcome
        for position in _signal_positions(decisions)
        if (
            outcome := _evaluate_signal(
                bars, position, decisions["entry_direction"].iloc[position], cfg
            )
        )
        is not None
    )
    holds = [item.hold_seconds for item in outcomes if item.hold_seconds is not None]
    adverse = [item.adverse_excursion_margin_pct for item in outcomes]
    return CandidateBarrierReport(
        len(outcomes),
        sum(item.status == "target_completed" for item in outcomes),
        sum(item.status == "liquidated" for item in outcomes),
        sum(item.status == "unresolved" for item in outcomes),
        sum(item.same_bar_ambiguous for item in outcomes),
        sum(item.net_pnl_usd for item in outcomes),
        median(holds) if holds else None,
        median(adverse) if adverse else None,
        outcomes,
    )
