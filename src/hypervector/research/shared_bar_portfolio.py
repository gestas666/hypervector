"""Causal one-position bar simulator for broad strategy screening."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from hypervector.research.shared_portfolio_barriers import (
    barrier_exit_price,
    barrier_hits,
    isolated_liquidation_price,
    ordered_exit_reason,
)
from hypervector.research.shared_portfolio_inputs import (
    BarEntrySignal,
    barriers_allow_entry,
    bar_entry_signal,
    desired_entry,
    side_exit_signal,
    validate_shared_inputs,
)
from hypervector.research.shared_portfolio_entry_barriers import entry_barriers
from hypervector.research.shared_portfolio_models import (
    Direction,
    ExitReason,
    SharedPortfolioConfig,
    SharedPortfolioReport,
    SharedPortfolioTrade,
)
from hypervector.research.shared_portfolio_pricing import (
    adverse_price,
    maximum_hold_reached,
)
from hypervector.research.shared_portfolio_profit_lock import (
    completed_bar_profit_lock_triggered,
)
from hypervector.research.shared_portfolio_completed_peak_lock import (
    completed_close_peak_lock_triggered,
)
from hypervector.research.shared_portfolio_quotes import (
    executable_close_price,
    executable_open_price,
)
from hypervector.research.shared_portfolio_reporting import (
    build_shared_portfolio_report,
)
from hypervector.research.shared_portfolio_sizing import position_size
from hypervector.research.shared_portfolio_signal_exits import signal_exit_allowed


@dataclass
class _OpenPosition:
    direction: Direction
    signal_position: int
    entry_position: int
    signal_name: str
    entry_price: float
    quantity: float
    margin: float
    notional: float
    equity_before: float
    entry_fee: float
    target_price: float | None
    stop_price: float | None
    funding_cashflow: float = 0.0


@dataclass
class _State:
    equity: float
    peak_equity: float
    maximum_drawdown_pct: float = 0.0
    position: _OpenPosition | None = None
    pending_entry: BarEntrySignal | None = None
    pending_exit: ExitReason | None = None
    last_exit_position: int | None = None
    blocked_reentry_direction: Direction | None = None
    conflicts: int = 0
    barrier_invalidated_entries: int = 0
    gap_expired_entries: int = 0
    maximum_concurrent_positions: int = 0
    trades: list[SharedPortfolioTrade] = field(default_factory=list)

    def update_drawdown(self, marked_equity: float) -> None:
        self.peak_equity = max(self.peak_equity, marked_equity)
        drawdown = 100.0 * (marked_equity - self.peak_equity) / self.peak_equity
        self.maximum_drawdown_pct = min(self.maximum_drawdown_pct, drawdown)


def evaluate_shared_bar_portfolio(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: SharedPortfolioConfig | None = None,
) -> SharedPortfolioReport:
    """Screen causal signals through one chronological isolated asset portfolio."""
    cfg = config or SharedPortfolioConfig()
    validate_shared_inputs(bars, signals, cfg)
    state = _State(cfg.initial_equity, cfg.initial_equity)
    for position in range(len(bars)):
        _advance_bar(state, bars, signals, position, cfg)
    _force_end_close(state, bars, cfg)
    return build_shared_portfolio_report(
        equity=state.equity,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        conflicts=state.conflicts,
        barrier_invalidated_entries=state.barrier_invalidated_entries,
        gap_expired_entries=state.gap_expired_entries,
        maximum_concurrent_positions=state.maximum_concurrent_positions,
        trades=state.trades,
        config=cfg,
    )


def _advance_bar(
    state: _State,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    _settle_funding(state, bars, position, config)
    _censor_open_position_at_gap(state, bars, position, config)
    _execute_open_orders(state, bars, position, config)
    _execute_wall_clock_expiry(state, bars, position, config)
    _evaluate_intrabar_risk(state, bars, position, config)
    _update_open_drawdown(state, bars, position, config)
    _schedule_close_actions(state, bars, signals, position, config)


def _censor_open_position_at_gap(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    """Close unknown in-gap lifecycle at the first observed executable quote."""
    opened = state.position
    if opened is None or not _entry_crosses_gap(bars, position):
        return
    open_price = executable_open_price(
        bars,
        position,
        opened.direction,
        entering=False,
        config=config,
    )
    _close_position(state, bars, position, open_price, "data_gap", False, config)
    state.pending_exit = None


def _execute_open_orders(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    if state.pending_exit is not None and state.position is not None:
        reason = state.pending_exit
        open_price = executable_open_price(
            bars,
            position,
            state.position.direction,
            entering=False,
            config=config,
        )
        _close_position(state, bars, position, open_price, reason, False, config)
    state.pending_exit = None
    if state.pending_entry is not None and state.position is None:
        if _entry_crosses_gap(bars, position):
            state.pending_entry = None
            state.gap_expired_entries += 1
        elif state.equity > 0.0:
            _fill_entry(state, bars, position, config)
        else:
            state.pending_entry = None


def _entry_crosses_gap(bars: pd.DataFrame, position: int) -> bool:
    if "gap_before_bars" not in bars:
        return False
    return int(bars["gap_before_bars"].iloc[position]) > 0


def _execute_wall_clock_expiry(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    opened = state.position
    if opened is None or config.max_hold_seconds is None:
        return
    entry_time = _open_observed_time(bars, opened.entry_position)
    observed_time = _open_observed_time(bars, position)
    if (observed_time - entry_time).total_seconds() < config.max_hold_seconds:
        return
    exit_price = executable_open_price(
        bars,
        position,
        opened.direction,
        entering=False,
        config=config,
    )
    _close_position(state, bars, position, exit_price, "max_hold", False, config)


def _fill_entry(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    pending = state.pending_entry
    if pending is None:
        return
    raw_open = executable_open_price(
        bars,
        position,
        pending.direction,
        entering=True,
        config=config,
    )
    entry = adverse_price(
        raw_open,
        pending.direction,
        config.entry_slippage_bps,
        entering=True,
    )
    target, stop = entry_barriers(pending, entry, config)
    if not barriers_allow_entry(entry, pending.direction, target, stop):
        state.pending_entry = None
        state.barrier_invalidated_entries += 1
        return
    margin, notional = position_size(
        state.equity,
        entry,
        stop,
        pending.direction,
        config,
    )
    fee = notional * config.entry_fee_rate
    quantity = notional / entry
    state.position = _OpenPosition(
        pending.direction,
        pending.signal_position,
        position,
        pending.signal_name,
        entry,
        quantity,
        margin,
        notional,
        state.equity,
        fee,
        target,
        stop,
    )
    state.pending_entry = None
    state.equity -= fee
    state.maximum_concurrent_positions = max(state.maximum_concurrent_positions, 1)
    state.update_drawdown(state.equity)


def _settle_funding(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    opened = state.position
    if opened is None or config.funding_column not in bars:
        return
    rate = float(bars[config.funding_column].iloc[position])
    if rate == 0.0:
        return
    mark = float(bars["open"].iloc[position])
    sign = 1.0 if opened.direction == "long" else -1.0
    cashflow = -sign * opened.quantity * mark * rate
    opened.funding_cashflow += cashflow
    state.equity += cashflow
    state.update_drawdown(state.equity)


def _evaluate_intrabar_risk(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    opened = state.position
    if opened is None:
        return
    high_column, low_column = _risk_columns(opened, position, config)
    high = float(bars[high_column].iloc[position])
    low = float(bars[low_column].iloc[position])
    bar_open = executable_open_price(
        bars,
        position,
        opened.direction,
        entering=False,
        config=config,
    )
    liquidation = _liquidation_price(opened, config)
    hits = barrier_hits(
        opened.direction,
        high,
        low,
        liquidation,
        opened.stop_price,
        opened.target_price,
    )
    reason = ordered_exit_reason(hits)
    if reason is None:
        return
    raw_exit = barrier_exit_price(
        opened.direction,
        liquidation,
        opened.stop_price,
        opened.target_price,
        reason,
        bar_open,
    )
    ambiguous = sum(hits.values()) > 1
    _close_position(state, bars, position, raw_exit, reason, ambiguous, config)


def _close_position(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    raw_exit: float,
    reason: ExitReason,
    ambiguous: bool,
    config: SharedPortfolioConfig,
) -> None:
    opened = state.position
    if opened is None:
        raise RuntimeError("shared portfolio close requires an open position")
    exit_price, exit_fee = _exit_terms(opened, raw_exit, reason, config)
    sign = 1.0 if opened.direction == "long" else -1.0
    gross = sign * opened.quantity * (exit_price - opened.entry_price)
    state.equity += gross - exit_fee
    state.trades.append(
        _trade_record(
            opened,
            bars,
            position,
            exit_price,
            gross,
            exit_fee,
            state.equity,
            reason,
            ambiguous,
            config,
        )
    )
    state.position = None
    state.last_exit_position = position
    if config.same_direction_reentry_requires_reset:
        state.blocked_reentry_direction = opened.direction
    state.update_drawdown(state.equity)


def _exit_terms(
    opened: _OpenPosition,
    raw_exit: float,
    reason: ExitReason,
    config: SharedPortfolioConfig,
) -> tuple[float, float]:
    if reason == "target":
        return raw_exit, opened.quantity * raw_exit * config.target_fee_rate
    if reason == "liquidation":
        price = adverse_price(
            raw_exit,
            opened.direction,
            config.liquidation_slippage_bps,
            entering=False,
        )
        return price, opened.quantity * price * config.liquidation_fee_rate
    price = adverse_price(
        raw_exit,
        opened.direction,
        config.market_exit_slippage_bps,
        entering=False,
    )
    return price, opened.quantity * price * config.market_exit_fee_rate


def _trade_record(
    opened: _OpenPosition,
    bars: pd.DataFrame,
    position: int,
    exit_price: float,
    gross: float,
    exit_fee: float,
    equity_after: float,
    reason: ExitReason,
    ambiguous: bool,
    config: SharedPortfolioConfig,
) -> SharedPortfolioTrade:
    fees = opened.entry_fee + exit_fee
    net = gross - fees + opened.funding_cashflow
    return SharedPortfolioTrade(
        opened.signal_name,
        opened.direction,
        bars.index[opened.signal_position].isoformat(),
        _open_observed_time(bars, opened.entry_position).isoformat(),
        _exit_observed_time(bars, position, reason).isoformat(),
        opened.signal_position,
        opened.entry_position,
        position,
        opened.entry_price,
        exit_price,
        opened.target_price,
        opened.stop_price,
        _liquidation_price(opened, config),
        opened.quantity,
        opened.margin,
        opened.notional,
        config.leverage,
        gross,
        fees,
        opened.funding_cashflow,
        net,
        opened.equity_before,
        equity_after,
        reason,
        ambiguous,
    )


def _open_observed_time(bars: pd.DataFrame, position: int) -> pd.Timestamp:
    timestamp = pd.Timestamp(bars.index[position])
    if "first_boundary_delay_ms" not in bars:
        return timestamp
    delay_ms = float(bars["first_boundary_delay_ms"].iloc[position])
    return timestamp + pd.Timedelta(milliseconds=delay_ms)


def _exit_observed_time(
    bars: pd.DataFrame,
    position: int,
    reason: ExitReason,
) -> pd.Timestamp:
    """Return the boundary timestamp matching the consumed exit quote."""
    if reason != "end_of_data" or "end_boundary_age_ms" not in bars:
        return _open_observed_time(bars, position)
    deltas = bars.index.to_series().diff().dropna()
    positive = deltas[deltas > pd.Timedelta(0)]
    if positive.empty:
        raise ValueError("close observation time requires a positive bar interval")
    duration = positive.min()
    age_ms = float(bars["end_boundary_age_ms"].iloc[position])
    if age_ms < 0.0 or age_ms >= duration.total_seconds() * 1_000.0:
        raise ValueError("end boundary age must be inside the bar interval")
    return (
        pd.Timestamp(bars.index[position])
        + duration
        - pd.Timedelta(milliseconds=age_ms)
    )


def _schedule_close_actions(
    state: _State,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    desired, conflict = desired_entry(signals, position)
    state.conflicts += int(conflict)
    if config.same_direction_reentry_requires_reset and (
        desired != state.blocked_reentry_direction
    ):
        state.blocked_reentry_direction = None
    opened = state.position
    if opened is not None:
        if completed_bar_profit_lock_triggered(
            bars,
            entry_position=opened.entry_position,
            current_position=position,
            direction=opened.direction,
            entry_price=opened.entry_price,
            policy=config.completed_bar_profit_lock,
        ):
            state.pending_exit = "profit_lock"
        if completed_close_peak_lock_triggered(
            bars,
            entry_position=opened.entry_position,
            current_position=position,
            direction=opened.direction,
            entry_price=opened.entry_price,
            leverage=config.leverage,
            policy=config.completed_bar_peak_lock,
        ):
            state.pending_exit = "profit_lock"
        _schedule_for_open_position(state, bars, signals, position, desired, config)
        return
    if desired is None or state.equity <= 0.0:
        return
    if state.blocked_reentry_direction == desired:
        return
    elapsed = (
        None
        if state.last_exit_position is None
        else position - state.last_exit_position
    )
    if elapsed is None or elapsed >= config.reentry_cooldown_bars:
        state.pending_entry = bar_entry_signal(signals, position, desired)


def _schedule_for_open_position(
    state: _State,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    position: int,
    desired: Direction | None,
    config: SharedPortfolioConfig,
) -> None:
    opened = state.position
    if opened is None or state.pending_exit is not None:
        return
    opposite = desired is not None and desired != opened.direction
    if opposite and config.close_on_opposite_signal:
        state.pending_exit = "opposite_signal"
        if config.reverse_on_opposite_signal:
            state.pending_entry = bar_entry_signal(signals, position, desired)
        return
    if side_exit_signal(signals, position, opened.direction) and signal_exit_allowed(
        bars,
        direction=opened.direction,
        entry_position=opened.entry_position,
        entry_price=opened.entry_price,
        current_position=position,
        config=config,
    ):
        state.pending_exit = "signal"
        return
    if maximum_hold_reached(
        opened.entry_position,
        position,
        config.max_hold_bars,
    ):
        state.pending_exit = "max_hold"


def _force_end_close(
    state: _State,
    bars: pd.DataFrame,
    config: SharedPortfolioConfig,
) -> None:
    if state.position is None:
        return
    position = len(bars) - 1
    _close_position(
        state,
        bars,
        position,
        executable_close_price(bars, position, state.position.direction, config),
        "end_of_data",
        False,
        config,
    )


def _liquidation_price(
    opened: _OpenPosition,
    config: SharedPortfolioConfig,
) -> float:
    return isolated_liquidation_price(
        config.symbol,
        opened.direction,
        opened.quantity,
        opened.entry_price,
        opened.margin,
        config.venue_max_leverage,
        opened.entry_fee,
        opened.funding_cashflow,
    )


def _update_open_drawdown(
    state: _State,
    bars: pd.DataFrame,
    position: int,
    config: SharedPortfolioConfig,
) -> None:
    opened = state.position
    if opened is None:
        state.update_drawdown(state.equity)
        return
    high_column, low_column = _risk_columns(opened, position, config)
    adverse = (
        float(bars[low_column].iloc[position])
        if opened.direction == "long"
        else float(bars[high_column].iloc[position])
    )
    sign = 1.0 if opened.direction == "long" else -1.0
    marked = state.equity + sign * opened.quantity * (adverse - opened.entry_price)
    state.update_drawdown(marked)


def _risk_columns(
    opened: _OpenPosition,
    position: int,
    config: SharedPortfolioConfig,
) -> tuple[str, str]:
    """Use post-fill extrema on the entry bar and full extrema thereafter."""
    if opened.entry_position == position and config.entry_risk_high_column is not None:
        if config.entry_risk_low_column is None:
            raise RuntimeError("entry risk columns require a complete pair")
        return config.entry_risk_high_column, config.entry_risk_low_column
    return config.risk_high_column, config.risk_low_column
