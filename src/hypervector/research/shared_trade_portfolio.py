"""Chronological shared-capital replay for completed strategy outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Mapping


@dataclass(frozen=True)
class SharedTradeOutcome:
    """One completed trade normalized to its original account equity."""

    trade_id: str
    symbol: str
    entry_time_ms: int
    exit_time_ms: int
    source_equity_usd: float
    margin_fraction: float
    entry_fee_usd: float
    net_pnl_usd: float
    outcome: str

    def __post_init__(self) -> None:
        """Reject malformed or noncausal completed outcomes."""
        if not self.trade_id.strip() or not self.symbol.strip():
            raise ValueError("trade_id and symbol must be non-empty")
        _nonnegative_integer(self.entry_time_ms, "entry_time_ms")
        _nonnegative_integer(self.exit_time_ms, "exit_time_ms")
        if self.exit_time_ms <= self.entry_time_ms:
            raise ValueError("exit_time_ms must follow entry_time_ms")
        _positive(self.source_equity_usd, "source_equity_usd")
        _fraction(self.margin_fraction, "margin_fraction")
        _nonnegative(self.entry_fee_usd, "entry_fee_usd")
        _finite(self.net_pnl_usd, "net_pnl_usd")
        if not self.outcome.strip():
            raise ValueError("outcome must be non-empty")


@dataclass(frozen=True)
class SharedTradeReplayConfig:
    """Shared account and optional symbol-specific scaling caps."""

    initial_equity_usd: float = 15_000.0
    capital_base_caps_usd: Mapping[str, float] = field(default_factory=dict)
    cap_at_source_equity: bool = False

    def __post_init__(self) -> None:
        """Validate the shared account and each explicit capacity cap."""
        _positive(self.initial_equity_usd, "initial_equity_usd")
        for symbol, cap in self.capital_base_caps_usd.items():
            if not symbol.strip():
                raise ValueError("capacity-cap symbol must be non-empty")
            _positive(cap, f"capital_base_caps_usd[{symbol}]")


@dataclass(frozen=True)
class ScaledSharedTrade:
    """One completed outcome after shared-equity scaling."""

    trade_id: str
    symbol: str
    entry_time_ms: int
    exit_time_ms: int
    scaling_base_usd: float
    margin_reserved_usd: float
    entry_fee_usd: float
    net_pnl_usd: float
    equity_after_usd: float
    outcome: str


@dataclass(frozen=True)
class SharedTradeReplayReport:
    """Realized-equity diagnostics for one shared chronological ledger."""

    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    return_pct: float
    realized_maximum_drawdown_pct: float
    completed_trades: int
    wins: int
    losses: int
    profit_factor: float | None
    maximum_concurrent_positions: int
    peak_reserved_margin_usd: float
    trades: tuple[ScaledSharedTrade, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe immutable report representation."""
        return asdict(self)


@dataclass
class _OpenTrade:
    outcome: SharedTradeOutcome
    scaling_base: float
    margin: float
    entry_fee: float


@dataclass
class _ReplayState:
    equity: float
    peak_equity: float
    maximum_drawdown_pct: float = 0.0
    maximum_concurrent: int = 0
    peak_reserved_margin: float = 0.0
    open_trades: dict[str, _OpenTrade] = field(default_factory=dict)
    scaled_trades: list[ScaledSharedTrade] = field(default_factory=list)


def replay_shared_trade_outcomes(
    outcomes: tuple[SharedTradeOutcome, ...],
    config: SharedTradeReplayConfig | None = None,
) -> SharedTradeReplayReport:
    """Scale completed outcomes through one chronological shared account."""
    cfg = config or SharedTradeReplayConfig()
    _validate_outcomes(outcomes)
    state = _ReplayState(cfg.initial_equity_usd, cfg.initial_equity_usd)
    for _time_ms, priority, outcome in _events(outcomes):
        if priority == 0:
            _exit_trade(state, outcome)
        else:
            _enter_trade(state, outcome, cfg)
    if state.open_trades:
        raise RuntimeError("shared trade replay ended with open outcomes")
    return _report(state, cfg)


def _events(
    outcomes: tuple[SharedTradeOutcome, ...],
) -> list[tuple[int, int, SharedTradeOutcome]]:
    events = [
        event
        for outcome in outcomes
        for event in (
            (outcome.entry_time_ms, 1, outcome),
            (outcome.exit_time_ms, 0, outcome),
        )
    ]
    return sorted(events, key=lambda event: (event[0], event[1], event[2].trade_id))


def _enter_trade(
    state: _ReplayState,
    outcome: SharedTradeOutcome,
    config: SharedTradeReplayConfig,
) -> None:
    cap = config.capital_base_caps_usd.get(outcome.symbol)
    base = (
        min(state.equity, outcome.source_equity_usd)
        if config.cap_at_source_equity
        else state.equity
    )
    if cap is not None:
        base = min(base, cap)
    if base <= 0.0:
        raise ValueError("shared equity is not positive at entry")
    scale = base / outcome.source_equity_usd
    entry_fee = outcome.entry_fee_usd * scale
    margin = outcome.margin_fraction * base
    reserved = sum(opened.margin for opened in state.open_trades.values())
    if reserved + margin + entry_fee > state.equity + 1e-9:
        raise ValueError(f"shared margin unavailable for {outcome.trade_id}")
    state.equity -= entry_fee
    state.open_trades[outcome.trade_id] = _OpenTrade(
        outcome,
        base,
        margin,
        entry_fee,
    )
    reserved += margin
    state.maximum_concurrent = max(state.maximum_concurrent, len(state.open_trades))
    state.peak_reserved_margin = max(state.peak_reserved_margin, reserved)
    _update_drawdown(state)


def _exit_trade(state: _ReplayState, outcome: SharedTradeOutcome) -> None:
    opened = state.open_trades.pop(outcome.trade_id, None)
    if opened is None:
        raise RuntimeError(f"missing shared open trade {outcome.trade_id}")
    scale = opened.scaling_base / outcome.source_equity_usd
    remaining_cashflow = (outcome.net_pnl_usd + outcome.entry_fee_usd) * scale
    scaled_net = outcome.net_pnl_usd * scale
    state.equity += remaining_cashflow
    state.peak_equity = max(state.peak_equity, state.equity)
    _update_drawdown(state)
    state.scaled_trades.append(
        ScaledSharedTrade(
            outcome.trade_id,
            outcome.symbol,
            outcome.entry_time_ms,
            outcome.exit_time_ms,
            opened.scaling_base,
            opened.margin,
            opened.entry_fee,
            scaled_net,
            state.equity,
            outcome.outcome,
        )
    )


def _validate_outcomes(outcomes: tuple[SharedTradeOutcome, ...]) -> None:
    ids = [outcome.trade_id for outcome in outcomes]
    if len(ids) != len(set(ids)):
        raise ValueError("shared trade IDs must be unique")
    by_symbol: dict[str, list[SharedTradeOutcome]] = {}
    for outcome in outcomes:
        by_symbol.setdefault(outcome.symbol, []).append(outcome)
    for symbol, trades in by_symbol.items():
        ordered = sorted(trades, key=lambda trade: trade.entry_time_ms)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.entry_time_ms < previous.exit_time_ms:
                raise ValueError(f"overlapping {symbol} outcomes are not allowed")


def _report(
    state: _ReplayState,
    config: SharedTradeReplayConfig,
) -> SharedTradeReplayReport:
    profits = [
        trade.net_pnl_usd for trade in state.scaled_trades if trade.net_pnl_usd > 0
    ]
    losses = [
        -trade.net_pnl_usd for trade in state.scaled_trades if trade.net_pnl_usd < 0
    ]
    profit_factor = sum(profits) / sum(losses) if losses else None
    return SharedTradeReplayReport(
        config.initial_equity_usd,
        state.equity,
        state.equity - config.initial_equity_usd,
        (state.equity / config.initial_equity_usd - 1.0) * 100.0,
        state.maximum_drawdown_pct,
        len(state.scaled_trades),
        len(profits),
        len(losses),
        profit_factor,
        state.maximum_concurrent,
        state.peak_reserved_margin,
        tuple(state.scaled_trades),
    )


def _update_drawdown(state: _ReplayState) -> None:
    drawdown = (state.equity / state.peak_equity - 1.0) * 100.0
    state.maximum_drawdown_pct = min(state.maximum_drawdown_pct, drawdown)


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _fraction(value: float, label: str) -> None:
    _positive(value, label)
    if value > 1.0:
        raise ValueError(f"{label} must not exceed one")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
