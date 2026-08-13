"""Serial one-position bar diagnostics for Hypervelocity regime candidates."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import pandas as pd

from hypervector.regime.models import BreakoutDirection
from hypervector.research.hypervelocity_candidate_eval import (
    CandidateBarrierConfig,
    CandidatePositionTerms,
    position_terms,
)

Direction = Literal["long", "short"]
TradeStatus = Literal["target_completed", "liquidated"]


@dataclass(frozen=True)
class SerialPortfolioConfig:
    """Assumptions unique to the serial portfolio diagnostic."""

    barrier: CandidateBarrierConfig = field(default_factory=CandidateBarrierConfig)
    reentry_cooldown_bars: int = 1
    same_direction_reentry_policy: Literal[
        "regime_reset",
        "cooldown_only",
        "target_continuation",
        "target_rsi_reconfirmation",
    ] = "regime_reset"
    same_direction_reentry_clearance_bps: float = 0.0
    target_continuation_limit_per_episode: int | None = None
    target_continuation_minimum_episode_bars: int = 0

    def __post_init__(self) -> None:
        if self.reentry_cooldown_bars < 0:
            raise ValueError("reentry_cooldown_bars must be non-negative")
        if self.same_direction_reentry_policy not in {
            "regime_reset",
            "cooldown_only",
            "target_continuation",
            "target_rsi_reconfirmation",
        }:
            raise ValueError(
                "same_direction_reentry_policy must be "
                "regime_reset|cooldown_only|target_continuation|"
                "target_rsi_reconfirmation"
            )
        if (
            not math.isfinite(self.same_direction_reentry_clearance_bps)
            or self.same_direction_reentry_clearance_bps < 0.0
        ):
            raise ValueError(
                "same_direction_reentry_clearance_bps must be finite and non-negative"
            )
        limit = self.target_continuation_limit_per_episode
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError(
                "target_continuation_limit_per_episode must be a positive integer"
            )
        if (
            limit is not None
            and self.same_direction_reentry_policy != "target_continuation"
        ):
            raise ValueError(
                "target_continuation_limit_per_episode requires target_continuation"
            )
        minimum = self.target_continuation_minimum_episode_bars
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            raise ValueError(
                "target_continuation_minimum_episode_bars must be a "
                "non-negative integer"
            )
        if minimum > 0 and self.same_direction_reentry_policy != "target_continuation":
            raise ValueError(
                "target_continuation_minimum_episode_bars requires target_continuation"
            )


@dataclass(frozen=True)
class SerialPortfolioTrade:
    """One completed next-bar-open diagnostic trade."""

    direction: Direction
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    signal_position: int
    entry_position: int
    exit_position: int
    status: TradeStatus
    entry_price: float
    exit_price: float
    target_price: float
    liquidation_price: float
    quantity: float
    margin: float
    fees_usd: float
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    same_bar_ambiguous: bool


@dataclass(frozen=True)
class SerialPortfolioReport:
    """Compounded one-position result with explicit modeling limits."""

    initial_equity: float
    realized_equity: float
    final_marked_equity: float
    net_pnl_usd: float
    return_pct: float
    maximum_drawdown_pct: float
    submitted_entries: int
    entry_fills: int
    completed_trades: int
    targets_completed: int
    liquidations: int
    open_positions: int
    pending_entries: int
    blocked_same_direction_bars: int
    maximum_concurrent_positions: int
    insolvent: bool
    liquidation_model: str
    drawdown_model: str
    trades: tuple[SerialPortfolioTrade, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe serial portfolio report."""
        return asdict(self)


@dataclass(frozen=True)
class _OpenPosition:
    direction: Direction
    signal_position: int
    entry_position: int
    entry_price: float
    equity_before: float
    terms: CandidatePositionTerms


@dataclass
class _PortfolioState:
    equity: float
    peak_equity: float
    maximum_drawdown_pct: float = 0.0
    pending: tuple[Direction, int] | None = None
    position: _OpenPosition | None = None
    consumed_direction: Direction | None = None
    consumed_status: TradeStatus | None = None
    consumed_reference_price: float | None = None
    structural_episode_direction: Direction | None = None
    structural_episode_start_position: int | None = None
    target_completions_in_episode: int = 0
    last_exit_position: int | None = None
    submitted_entries: int = 0
    entry_fills: int = 0
    blocked_same_direction_bars: int = 0
    maximum_concurrent_positions: int = 0
    trades: list[SerialPortfolioTrade] = field(default_factory=list)


def _validate_inputs(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    config: SerialPortfolioConfig,
) -> None:
    missing_bars = {"open", "high", "low", "close"}.difference(bars.columns)
    missing_decisions = {"entry_direction", "structural_direction"}.difference(
        decisions.columns
    )
    if missing_bars:
        raise ValueError(f"serial bars missing columns: {sorted(missing_bars)}")
    if missing_decisions:
        raise ValueError(
            f"serial decisions missing columns: {sorted(missing_decisions)}"
        )
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("serial bars require a DatetimeIndex")
    if not bars.index.equals(decisions.index):
        raise ValueError("serial bars and decisions require the same index")
    if (
        config.same_direction_reentry_policy == "target_rsi_reconfirmation"
        and "rsi_cross_direction" not in decisions
    ):
        raise ValueError(
            "target_rsi_reconfirmation requires rsi_cross_direction telemetry"
        )


def _direction(value: object) -> Direction | None:
    return value if value in ("long", "short") else None


def _update_drawdown(state: _PortfolioState, marked_equity: float) -> None:
    state.peak_equity = max(state.peak_equity, marked_equity)
    drawdown = 100.0 * (marked_equity - state.peak_equity) / state.peak_equity
    state.maximum_drawdown_pct = min(state.maximum_drawdown_pct, drawdown)


def _fill_pending(
    state: _PortfolioState,
    bars: pd.DataFrame,
    position: int,
    config: CandidateBarrierConfig,
) -> None:
    if state.pending is None:
        return
    direction, signal_position = state.pending
    entry_price = float(bars["open"].iloc[position])
    terms = position_terms(direction, entry_price, state.equity, config)
    before = state.equity
    state.equity -= terms.entry_fee
    state.position = _OpenPosition(
        direction, signal_position, position, entry_price, before, terms
    )
    state.pending = None
    state.entry_fills += 1
    state.maximum_concurrent_positions = max(state.maximum_concurrent_positions, 1)
    _update_drawdown(state, state.equity)


def _barrier_status(
    position: _OpenPosition,
    high: float,
    low: float,
) -> tuple[TradeStatus | None, bool]:
    terms = position.terms
    if position.direction == "long":
        target_hit = high >= terms.target_price
        liquidation_hit = low <= terms.liquidation_price
    else:
        target_hit = low <= terms.target_price
        liquidation_hit = high >= terms.liquidation_price
    ambiguous = target_hit and liquidation_hit
    if liquidation_hit:
        return "liquidated", ambiguous
    return ("target_completed" if target_hit else None), ambiguous


def _close_position(
    state: _PortfolioState,
    bars: pd.DataFrame,
    position: int,
    status: TradeStatus,
    ambiguous: bool,
    config: CandidateBarrierConfig,
) -> None:
    opened = state.position
    if opened is None:
        raise RuntimeError("serial close requires an open position")
    exit_price = (
        opened.terms.liquidation_price
        if status == "liquidated"
        else opened.terms.target_price
    )
    sign = 1.0 if opened.direction == "long" else -1.0
    gross = sign * opened.terms.quantity * (exit_price - opened.entry_price)
    fee_rate = (
        config.liquidation_fee_rate if status == "liquidated" else config.maker_fee_rate
    )
    exit_fee = opened.terms.quantity * exit_price * fee_rate
    state.equity += gross - exit_fee
    fees = opened.terms.entry_fee + exit_fee
    state.trades.append(
        _trade_record(
            opened, bars, position, status, exit_price, fees, state.equity, ambiguous
        )
    )
    state.consumed_direction = opened.direction
    state.consumed_status = status
    state.consumed_reference_price = exit_price
    if status == "target_completed":
        state.target_completions_in_episode += 1
    state.last_exit_position = position
    state.position = None
    _update_drawdown(state, state.equity)


def _trade_record(
    opened: _OpenPosition,
    bars: pd.DataFrame,
    exit_position: int,
    status: TradeStatus,
    exit_price: float,
    fees: float,
    equity_after: float,
    ambiguous: bool,
) -> SerialPortfolioTrade:
    sign = 1.0 if opened.direction == "long" else -1.0
    gross = sign * opened.terms.quantity * (exit_price - opened.entry_price)
    return SerialPortfolioTrade(
        opened.direction,
        bars.index[opened.signal_position].isoformat(),
        bars.index[opened.entry_position].isoformat(),
        bars.index[exit_position].isoformat(),
        opened.signal_position,
        opened.entry_position,
        exit_position,
        status,
        opened.entry_price,
        exit_price,
        opened.terms.target_price,
        opened.terms.liquidation_price,
        opened.terms.quantity,
        opened.terms.margin,
        fees,
        gross - fees,
        opened.equity_before,
        equity_after,
        ambiguous,
    )


def _marked_equity(state: _PortfolioState, close: float) -> float:
    opened = state.position
    if opened is None:
        return state.equity
    sign = 1.0 if opened.direction == "long" else -1.0
    unrealized = sign * opened.terms.quantity * (close - opened.entry_price)
    return state.equity + unrealized


def _may_schedule(
    state: _PortfolioState,
    direction: Direction,
    position: int,
    market_price: float,
    rsi_cross: object,
    config: SerialPortfolioConfig,
) -> bool:
    if state.position is not None or state.pending is not None or state.equity <= 0.0:
        return False
    if direction == state.consumed_direction:
        blocked = config.same_direction_reentry_policy == "regime_reset"
        if config.same_direction_reentry_policy == "target_continuation":
            reference = state.consumed_reference_price
            clearance = config.same_direction_reentry_clearance_bps / 10_000.0
            continued = reference is not None and (
                market_price >= reference * (1.0 + clearance)
                if direction == "long"
                else market_price <= reference * (1.0 - clearance)
            )
            limit = config.target_continuation_limit_per_episode
            at_limit = (
                limit is not None and state.target_completions_in_episode >= limit
            )
            start = state.structural_episode_start_position
            mature = start is not None and (
                position - start >= config.target_continuation_minimum_episode_bars
            )
            blocked = (
                state.consumed_status != "target_completed"
                or not continued
                or at_limit
                or not mature
            )
        if config.same_direction_reentry_policy == "target_rsi_reconfirmation":
            expected = (
                BreakoutDirection.UPWARD.value
                if direction == "long"
                else BreakoutDirection.DOWNWARD.value
            )
            blocked = (
                state.consumed_status != "target_completed" or rsi_cross != expected
            )
        if blocked:
            state.blocked_same_direction_bars += 1
            return False
    if state.last_exit_position is None:
        return True
    return position - state.last_exit_position >= config.reentry_cooldown_bars


def _advance_bar(
    state: _PortfolioState,
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    position: int,
    config: SerialPortfolioConfig,
) -> None:
    _fill_pending(state, bars, position, config.barrier)
    opened = state.position
    if opened is not None:
        status, ambiguous = _barrier_status(
            opened,
            float(bars["high"].iloc[position]),
            float(bars["low"].iloc[position]),
        )
        if status is not None:
            _close_position(state, bars, position, status, ambiguous, config.barrier)
    _update_drawdown(state, _marked_equity(state, float(bars["close"].iloc[position])))
    structural = _direction(decisions["structural_direction"].iloc[position])
    if structural != state.structural_episode_direction:
        state.structural_episode_direction = structural
        state.structural_episode_start_position = position
        state.target_completions_in_episode = 0
    if state.consumed_direction is not None and structural != state.consumed_direction:
        state.consumed_direction = None
        state.consumed_status = None
        state.consumed_reference_price = None
    desired = _direction(decisions["entry_direction"].iloc[position])
    rsi_cross = (
        decisions["rsi_cross_direction"].iloc[position]
        if "rsi_cross_direction" in decisions
        else None
    )
    if desired is not None and position + 1 < len(bars):
        if _may_schedule(
            state,
            desired,
            position,
            float(bars["close"].iloc[position]),
            rsi_cross,
            config,
        ):
            state.pending = (desired, position)
            state.submitted_entries += 1


def evaluate_serial_portfolio(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    config: SerialPortfolioConfig | None = None,
) -> SerialPortfolioReport:
    """Evaluate causal entries with runtime-like reentry and TP-only holding."""
    cfg = config or SerialPortfolioConfig()
    _validate_inputs(bars, decisions, cfg)
    initial = cfg.barrier.initial_equity
    state = _PortfolioState(initial, initial)
    for position in range(len(bars)):
        _advance_bar(state, bars, decisions, position, cfg)
    final_marked = _marked_equity(state, float(bars["close"].iloc[-1]))
    if not math.isfinite(final_marked):
        raise ValueError("serial portfolio produced non-finite final equity")
    return SerialPortfolioReport(
        initial,
        state.equity,
        final_marked,
        final_marked - initial,
        100.0 * (final_marked - initial) / initial,
        state.maximum_drawdown_pct,
        state.submitted_entries,
        state.entry_fills,
        len(state.trades),
        sum(trade.status == "target_completed" for trade in state.trades),
        sum(trade.status == "liquidated" for trade in state.trades),
        int(state.position is not None),
        int(state.pending is not None),
        state.blocked_same_direction_bars,
        state.maximum_concurrent_positions,
        state.equity <= 0.0,
        "full_close_at_isolated_boundary_v1",
        "close_mark_to_market_and_realized_events_v1",
        tuple(state.trades),
    )
