"""Causal shared-capital replay for the frozen crypto participation sleeve."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from hypervector.research.crypto_bull_participation_models import (
    CryptoBullExitReason,
    CryptoBullParticipationConfig,
    CryptoBullPortfolioReport,
    CryptoBullTrade,
)

_OHLC = ("open", "high", "low", "close")


@dataclass
class _Position:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    raw_entry_price: float
    quantity: float
    margin_usd: float
    notional_usd: float
    entry_fee_usd: float
    equity_before_usd: float
    initial_stop_price: float
    liquidation_price: float
    bound_stop_price: float
    stop_reason: CryptoBullExitReason = "protective_stop"
    highest_completed_hour_price: float = 0.0
    funding_cashflow_usd: float = 0.0


@dataclass
class _State:
    equity_usd: float
    peak_marked_equity_usd: float
    positions: dict[str, _Position] = field(default_factory=dict)
    trades: list[CryptoBullTrade] = field(default_factory=list)
    maximum_drawdown_pct: float = 0.0
    maximum_concurrent_positions: int = 0
    maximum_margin_fraction: float = 0.0
    exposure_minutes: int = 0
    stop_losses_by_time: dict[pd.Timestamp, float] = field(
        default_factory=lambda: defaultdict(float)
    )


def evaluate_crypto_bull_portfolio(
    minute_by_symbol: Mapping[str, pd.DataFrame],
    decisions_by_symbol: Mapping[str, pd.DataFrame],
    funding_by_symbol: Mapping[str, pd.Series],
    config: CryptoBullParticipationConfig | None = None,
) -> CryptoBullPortfolioReport:
    """Replay synchronized minute bars with next-boundary decisions and costs."""
    cfg = config or CryptoBullParticipationConfig()
    minutes, decisions, funding = _validated_inputs(
        minute_by_symbol, decisions_by_symbol, funding_by_symbol, cfg
    )
    index = minutes[cfg.symbols[0]].index
    state = _State(cfg.initial_equity_usd, cfg.initial_equity_usd)
    for timestamp in index:
        _settle_funding(state, minutes, funding, timestamp)
        _advance_boundary(state, minutes, decisions, timestamp, cfg)
        _expire_positions(state, minutes, timestamp, cfg)
        _apply_stops(state, minutes, timestamp, cfg)
        _update_marked_state(state, minutes, timestamp)
    _force_end_close(state, minutes, index[-1], cfg)
    return _build_report(state, len(index), cfg)


def _advance_boundary(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    decisions: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    config: CryptoBullParticipationConfig,
) -> None:
    active = [
        symbol for symbol in config.symbols if timestamp in decisions[symbol].index
    ]
    for symbol in active:
        decision = decisions[symbol].loc[timestamp]
        if symbol in state.positions and bool(decision["exit_signal"]):
            _close_at_open(
                state, minutes, symbol, timestamp, "trend_deterioration", config
            )
    for symbol in active:
        if symbol in state.positions:
            high = float(decisions[symbol].loc[timestamp, "completed_hour_high"])
            _update_profit_lock(state.positions[symbol], high, config)
    capacity = config.maximum_positions - len(state.positions)
    entrants = [
        symbol
        for symbol in active
        if symbol not in state.positions
        and bool(decisions[symbol].loc[timestamp, "entry_onset"])
    ][:capacity]
    _open_positions(state, minutes, entrants, timestamp, config)


def _open_positions(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    symbols: list[str],
    timestamp: pd.Timestamp,
    config: CryptoBullParticipationConfig,
) -> None:
    sizing_equity = state.equity_usd
    for symbol in symbols:
        raw = float(minutes[symbol].loc[timestamp, "open"])
        entry = raw * (1.0 + config.adverse_slippage_bps_per_side / 10_000.0)
        margin = sizing_equity * config.margin_fraction_per_position
        notional = margin * config.leverage
        quantity = notional / entry
        fee = notional * config.entry_fee_bps / 10_000.0
        stop = entry * (1.0 - config.protective_stop_bps / 10_000.0)
        liquidation = entry * (1.0 - 1.0 / config.leverage)
        state.positions[symbol] = _Position(
            symbol=symbol,
            entry_time=timestamp,
            entry_price=entry,
            raw_entry_price=raw,
            quantity=quantity,
            margin_usd=margin,
            notional_usd=notional,
            entry_fee_usd=fee,
            equity_before_usd=sizing_equity,
            initial_stop_price=stop,
            liquidation_price=liquidation,
            bound_stop_price=stop,
            highest_completed_hour_price=entry,
        )
        state.equity_usd -= fee
    _update_capacity(state)


def _update_profit_lock(
    position: _Position, completed_high: float, config: CryptoBullParticipationConfig
) -> None:
    position.highest_completed_hour_price = max(
        position.highest_completed_hour_price, completed_high
    )
    gain_bps = 10_000.0 * (
        position.highest_completed_hour_price / position.entry_price - 1.0
    )
    if gain_bps < config.profit_lock_activation_bps:
        return
    floor = position.entry_price * (1.0 + config.profit_lock_floor_bps / 10_000.0)
    trailing = position.highest_completed_hour_price * (
        1.0 - config.profit_lock_giveback_bps / 10_000.0
    )
    position.bound_stop_price = max(position.bound_stop_price, floor, trailing)
    position.stop_reason = "profit_lock"


def _settle_funding(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    funding: Mapping[str, pd.Series],
    timestamp: pd.Timestamp,
) -> None:
    for symbol, position in state.positions.items():
        rate = float(funding[symbol].get(timestamp, 0.0))
        if rate == 0.0:
            continue
        mark = float(minutes[symbol].loc[timestamp, "open"])
        cashflow = -position.quantity * mark * rate
        position.funding_cashflow_usd += cashflow
        state.equity_usd += cashflow


def _expire_positions(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    config: CryptoBullParticipationConfig,
) -> None:
    for symbol, position in tuple(state.positions.items()):
        age = int((timestamp - position.entry_time).total_seconds() // 60)
        if age >= config.maximum_hold_minutes:
            _close_at_open(state, minutes, symbol, timestamp, "maximum_hold", config)


def _apply_stops(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    config: CryptoBullParticipationConfig,
) -> None:
    for symbol, position in tuple(state.positions.items()):
        bar = minutes[symbol].loc[timestamp]
        if float(bar["low"]) <= position.liquidation_price:
            raw_exit = min(float(bar["open"]), position.liquidation_price)
            _close_position(
                state,
                symbol,
                timestamp,
                raw_exit,
                "liquidation",
                config,
            )
            continue
        if float(bar["low"]) > position.bound_stop_price:
            continue
        raw_exit = min(float(bar["open"]), position.bound_stop_price)
        _close_position(
            state,
            symbol,
            timestamp,
            raw_exit,
            position.stop_reason,
            config,
        )


def _close_at_open(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    symbol: str,
    timestamp: pd.Timestamp,
    reason: CryptoBullExitReason,
    config: CryptoBullParticipationConfig,
) -> None:
    raw = float(minutes[symbol].loc[timestamp, "open"])
    _close_position(state, symbol, timestamp, raw, reason, config)


def _close_position(
    state: _State,
    symbol: str,
    timestamp: pd.Timestamp,
    raw_exit: float,
    reason: CryptoBullExitReason,
    config: CryptoBullParticipationConfig,
) -> None:
    position = state.positions.pop(symbol)
    exit_price = raw_exit * (1.0 - config.adverse_slippage_bps_per_side / 10_000.0)
    exit_notional = position.quantity * exit_price
    exit_fee = exit_notional * config.exit_fee_bps / 10_000.0
    gross = position.quantity * (exit_price - position.entry_price)
    state.equity_usd += gross - exit_fee
    fees = position.entry_fee_usd + exit_fee
    slippage = position.quantity * (
        (position.entry_price - position.raw_entry_price) + (raw_exit - exit_price)
    )
    net = gross - fees + position.funding_cashflow_usd
    holding = int((timestamp - position.entry_time).total_seconds() // 60)
    state.trades.append(
        CryptoBullTrade(
            symbol=symbol,
            entry_time_utc=position.entry_time.isoformat(),
            exit_time_utc=timestamp.isoformat(),
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            margin_usd=position.margin_usd,
            notional_usd=position.notional_usd,
            gross_pnl_usd=gross,
            fees_usd=fees,
            funding_cashflow_usd=position.funding_cashflow_usd,
            slippage_cost_usd=slippage,
            net_pnl_usd=net,
            holding_minutes=holding,
            exit_reason=reason,
            initial_stop_price=position.initial_stop_price,
            final_stop_price=position.bound_stop_price,
            highest_completed_hour_price=position.highest_completed_hour_price,
            equity_before_usd=position.equity_before_usd,
            equity_after_usd=state.equity_usd,
        )
    )
    if reason in {"liquidation", "protective_stop", "profit_lock"} and net < 0.0:
        state.stop_losses_by_time[timestamp] += net


def _update_marked_state(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
) -> None:
    if state.positions:
        state.exposure_minutes += 1
    marked = state.equity_usd + sum(
        position.quantity
        * (float(minutes[symbol].loc[timestamp, "close"]) - position.entry_price)
        for symbol, position in state.positions.items()
    )
    state.peak_marked_equity_usd = max(state.peak_marked_equity_usd, marked)
    drawdown = 100.0 * (marked / state.peak_marked_equity_usd - 1.0)
    state.maximum_drawdown_pct = min(state.maximum_drawdown_pct, drawdown)
    _update_capacity(state)


def _update_capacity(state: _State) -> None:
    state.maximum_concurrent_positions = max(
        state.maximum_concurrent_positions, len(state.positions)
    )
    if state.equity_usd <= 0.0:
        return
    margin = sum(position.margin_usd for position in state.positions.values())
    state.maximum_margin_fraction = max(
        state.maximum_margin_fraction, margin / state.equity_usd
    )


def _force_end_close(
    state: _State,
    minutes: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    config: CryptoBullParticipationConfig,
) -> None:
    for symbol in tuple(state.positions):
        raw = float(minutes[symbol].loc[timestamp, "close"])
        _close_position(state, symbol, timestamp, raw, "end_of_data", config)


def _build_report(
    state: _State, available_minutes: int, config: CryptoBullParticipationConfig
) -> CryptoBullPortfolioReport:
    waves = list(state.stop_losses_by_time.values())
    return CryptoBullPortfolioReport(
        initial_equity_usd=config.initial_equity_usd,
        final_equity_usd=state.equity_usd,
        net_pnl_usd=state.equity_usd - config.initial_equity_usd,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        maximum_concurrent_positions=state.maximum_concurrent_positions,
        maximum_margin_fraction=state.maximum_margin_fraction,
        simultaneous_stop_wave_loss_usd=min(waves, default=0.0),
        turnover_usd=sum(
            trade.notional_usd + trade.quantity * trade.exit_price
            for trade in state.trades
        ),
        exposure_minutes=state.exposure_minutes,
        available_minutes=available_minutes,
        trades=tuple(state.trades),
    )


def _validated_inputs(
    minute_values: Mapping[str, pd.DataFrame],
    decision_values: Mapping[str, pd.DataFrame],
    funding_values: Mapping[str, pd.Series],
    config: CryptoBullParticipationConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.Series]]:
    expected = set(config.symbols)
    if any(
        set(values) != expected
        for values in (minute_values, decision_values, funding_values)
    ):
        raise ValueError("replay inputs differ from the configured symbols")
    minutes = {symbol: minute_values[symbol].copy() for symbol in config.symbols}
    decisions = {symbol: decision_values[symbol].copy() for symbol in config.symbols}
    funding = {symbol: funding_values[symbol].copy() for symbol in config.symbols}
    index: pd.DatetimeIndex | None = None
    for symbol in config.symbols:
        _validate_minutes(minutes[symbol], symbol)
        if index is None:
            index = minutes[symbol].index
        elif not minutes[symbol].index.equals(index):
            raise ValueError("replay minute indexes must be aligned")
        _validate_decisions(decisions[symbol], symbol)
        _validate_funding(funding[symbol], index, symbol)
    return minutes, decisions, funding


def _validate_minutes(frame: pd.DataFrame, symbol: str) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{symbol} minute index must be timezone-aware")
    if (
        frame.empty
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
    ):
        raise ValueError(
            f"{symbol} minute frame must be unique, ordered, and non-empty"
        )
    missing = sorted(set(_OHLC).difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} minute frame missing columns: {missing}")
    numeric = frame.loc[:, _OHLC].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy()).all() or (numeric <= 0.0).any().any():
        raise ValueError(f"{symbol} minute OHLC must be finite and positive")


def _validate_decisions(frame: pd.DataFrame, symbol: str) -> None:
    required = {
        "entry_onset",
        "entry_eligible",
        "exit_signal",
        "breadth",
        "completed_hour_high",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} decisions missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{symbol} decision index must be timezone-aware")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{symbol} decisions must be unique and ordered")


def _validate_funding(
    series: pd.Series, minute_index: pd.DatetimeIndex | None, symbol: str
) -> None:
    if minute_index is None:
        raise ValueError("replay minute index is unavailable")
    if not isinstance(series.index, pd.DatetimeIndex) or series.index.tz is None:
        raise ValueError(f"{symbol} funding index must be timezone-aware")
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError(f"{symbol} funding must be unique and ordered")
    if len(series) and not np.isfinite(pd.to_numeric(series, errors="raise")).all():
        raise ValueError(f"{symbol} funding must be finite")
    if len(series.index.difference(minute_index)):
        raise ValueError(f"{symbol} funding timestamps are outside minute coverage")
