"""Concurrent completed-bar mark-to-market replay for fixed lifecycles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
import math

import pandas as pd


@dataclass(frozen=True)
class MarkedLifecycle:
    """One accepted lifecycle with exact price and cashflow attribution."""

    trade_id: str
    strategy_id: str
    symbol: str
    side: str
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    quantity: float
    entry_fee_usd: float
    exit_fee_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float

    def __post_init__(self) -> None:
        """Reject malformed lifecycles and unreconciled cashflows."""
        _validate_lifecycle(self)


@dataclass(frozen=True)
class ConcurrentMtmReport:
    """Path-dependent close-mark and adverse-intrabar account diagnostics."""

    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    close_mark_maximum_drawdown_pct: float
    adverse_intrabar_maximum_drawdown_pct: float
    completed_lifecycles: int
    maximum_concurrent_positions: int
    marked_path_points: int
    observed_lifecycles: int
    unobserved_lifecycles: int
    unobserved_trade_ids: tuple[str, ...]
    instant_exit_lifecycles: int
    missing_mark_lifecycles: int
    missing_mark_trade_ids: tuple[str, ...]
    funding_timing: str = "linear_between_entry_and_exit"
    execution_authority: str = "none"
    report_only: bool = True

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe immutable representation."""
        return asdict(self)


@dataclass(frozen=True)
class _MarkEvent:
    timestamp_ms: int
    symbol: str
    close: float
    high: float
    low: float


@dataclass
class _ReplayState:
    realized_net: float = 0.0
    close_peak: float = 0.0
    adverse_peak: float = 0.0
    close_drawdown: float = 0.0
    adverse_drawdown: float = 0.0
    maximum_concurrent: int = 0
    open_by_symbol: dict[str, MarkedLifecycle] = field(default_factory=dict)
    latest_close: dict[str, float] = field(default_factory=dict)
    observations: dict[str, int] = field(default_factory=dict)
    path_rows: list[dict[str, float | int]] = field(default_factory=list)


def replay_concurrent_mark_to_market(
    lifecycles: tuple[MarkedLifecycle, ...],
    bars_by_symbol: Mapping[str, pd.DataFrame],
    initial_equity_usd: float,
) -> tuple[ConcurrentMtmReport, pd.DataFrame]:
    """Revalue all simultaneously open accepted lifecycles on completed bars."""
    _positive(initial_equity_usd, "initial_equity_usd")
    _validate_lifecycles(lifecycles)
    events = _mark_events(bars_by_symbol, lifecycles)
    entries = _group_lifecycles(lifecycles, entry=True)
    exits = _group_lifecycles(lifecycles, entry=False)
    marks = _group_marks(events)
    timestamps = sorted(set(entries) | set(exits) | set(marks))
    state = _ReplayState(
        close_peak=initial_equity_usd,
        adverse_peak=initial_equity_usd,
        observations={row.trade_id: 0 for row in lifecycles},
    )
    for timestamp_ms in timestamps:
        current_marks = marks.get(timestamp_ms, ())
        if current_marks:
            _process_marks(state, current_marks, timestamp_ms)
            _record_path(state, current_marks, timestamp_ms, initial_equity_usd)
        _process_exits(state, exits.get(timestamp_ms, ()))
        _process_entries(state, entries.get(timestamp_ms, ()))
        if timestamp_ms in entries or timestamp_ms in exits:
            _record_path(state, (), timestamp_ms, initial_equity_usd)
    return _build_report(state, lifecycles, initial_equity_usd), pd.DataFrame(
        state.path_rows
    )


def _process_exits(
    state: _ReplayState, lifecycles: tuple[MarkedLifecycle, ...]
) -> None:
    for lifecycle in lifecycles:
        opened = state.open_by_symbol.pop(lifecycle.symbol, None)
        if opened is None or opened.trade_id != lifecycle.trade_id:
            raise RuntimeError(
                f"mark-to-market exit identity mismatch: {lifecycle.trade_id}"
            )
        state.realized_net += lifecycle.net_pnl_usd
        state.latest_close.pop(lifecycle.symbol, None)


def _process_entries(
    state: _ReplayState, lifecycles: tuple[MarkedLifecycle, ...]
) -> None:
    for lifecycle in lifecycles:
        if lifecycle.symbol in state.open_by_symbol:
            raise RuntimeError(
                f"concurrent lifecycle symbol collision: {lifecycle.symbol}"
            )
        state.open_by_symbol[lifecycle.symbol] = lifecycle
        state.latest_close[lifecycle.symbol] = lifecycle.entry_price
        state.maximum_concurrent = max(
            state.maximum_concurrent, len(state.open_by_symbol)
        )


def _process_marks(
    state: _ReplayState,
    events: tuple[_MarkEvent, ...],
    timestamp_ms: int,
) -> None:
    for event in events:
        state.latest_close[event.symbol] = event.close
        lifecycle = state.open_by_symbol.get(event.symbol)
        if (
            lifecycle is not None
            and lifecycle.entry_time_ms < timestamp_ms <= lifecycle.exit_time_ms
        ):
            state.observations[lifecycle.trade_id] += 1


def _record_path(
    state: _ReplayState,
    events: tuple[_MarkEvent, ...],
    timestamp_ms: int,
    initial_equity_usd: float,
) -> None:
    adverse = {event.symbol: _adverse_price(state, event) for event in events}
    close_equity = _marked_equity(state, timestamp_ms, initial_equity_usd, {})
    adverse_equity = _marked_equity(state, timestamp_ms, initial_equity_usd, adverse)
    state.close_peak, state.close_drawdown = _update_drawdown(
        state.close_peak, state.close_drawdown, close_equity
    )
    state.adverse_peak = max(state.adverse_peak, state.close_peak)
    state.adverse_peak, state.adverse_drawdown = _update_drawdown(
        state.adverse_peak, state.adverse_drawdown, adverse_equity
    )
    state.path_rows.append(
        {
            "timestamp_ms": timestamp_ms,
            "close_mark_equity_usd": close_equity,
            "adverse_intrabar_equity_usd": adverse_equity,
            "open_positions": len(state.open_by_symbol),
            "realized_net_pnl_usd": state.realized_net,
        }
    )


def _marked_equity(
    state: _ReplayState,
    timestamp_ms: int,
    initial_equity_usd: float,
    overrides: Mapping[str, float],
) -> float:
    equity = initial_equity_usd + state.realized_net
    for symbol, lifecycle in state.open_by_symbol.items():
        mark = overrides.get(symbol, state.latest_close[symbol])
        sign = 1.0 if lifecycle.side == "long" else -1.0
        gross = sign * lifecycle.quantity * (mark - lifecycle.entry_price)
        equity += gross - lifecycle.entry_fee_usd
        equity += lifecycle.funding_cashflow_usd * _elapsed_fraction(
            lifecycle, timestamp_ms
        )
    return equity


def _adverse_price(state: _ReplayState, event: _MarkEvent) -> float:
    lifecycle = state.open_by_symbol.get(event.symbol)
    if lifecycle is None:
        return event.close
    return event.low if lifecycle.side == "long" else event.high


def _build_report(
    state: _ReplayState,
    lifecycles: tuple[MarkedLifecycle, ...],
    initial_equity_usd: float,
) -> ConcurrentMtmReport:
    if state.open_by_symbol:
        raise RuntimeError("mark-to-market replay ended with open lifecycles")
    unobserved = tuple(
        row.trade_id for row in lifecycles if state.observations[row.trade_id] == 0
    )
    instant = {
        row.trade_id for row in lifecycles if row.exit_time_ms - row.entry_time_ms <= 1
    }
    missing_marks = tuple(
        trade_id for trade_id in unobserved if trade_id not in instant
    )
    final_equity = initial_equity_usd + sum(row.net_pnl_usd for row in lifecycles)
    return ConcurrentMtmReport(
        initial_equity_usd,
        final_equity,
        final_equity - initial_equity_usd,
        state.close_drawdown,
        state.adverse_drawdown,
        len(lifecycles),
        state.maximum_concurrent,
        len(state.path_rows),
        len(lifecycles) - len(unobserved),
        len(unobserved),
        unobserved,
        len(unobserved) - len(missing_marks),
        len(missing_marks),
        missing_marks,
    )


def _mark_events(
    bars_by_symbol: Mapping[str, pd.DataFrame],
    lifecycles: tuple[MarkedLifecycle, ...],
) -> tuple[_MarkEvent, ...]:
    symbols = {row.symbol for row in lifecycles}
    missing = sorted(symbols - set(bars_by_symbol))
    if missing:
        raise ValueError(f"mark bars missing lifecycle symbols: {missing}")
    output: list[_MarkEvent] = []
    for symbol in sorted(symbols):
        output.extend(_symbol_mark_events(symbol, bars_by_symbol[symbol]))
    return tuple(output)


def _symbol_mark_events(symbol: str, bars: pd.DataFrame) -> list[_MarkEvent]:
    required = {"close", "high", "low"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"{symbol} mark bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError(f"{symbol} mark bars require a DatetimeIndex")
    if (
        bars.index.tz is None
        or not bars.index.is_monotonic_increasing
        or not bars.index.is_unique
    ):
        raise ValueError(f"{symbol} mark bars must use a unique ordered aware index")
    output: list[_MarkEvent] = []
    for timestamp, row in bars.iterrows():
        output.append(
            _MarkEvent(
                int(timestamp.timestamp() * 1_000),
                symbol,
                _positive_number(row["close"], f"{symbol} close"),
                _positive_number(row["high"], f"{symbol} high"),
                _positive_number(row["low"], f"{symbol} low"),
            )
        )
    return output


def _group_lifecycles(
    lifecycles: tuple[MarkedLifecycle, ...], *, entry: bool
) -> dict[int, tuple[MarkedLifecycle, ...]]:
    output: dict[int, list[MarkedLifecycle]] = {}
    for row in lifecycles:
        timestamp = row.entry_time_ms if entry else row.exit_time_ms
        output.setdefault(timestamp, []).append(row)
    return {key: tuple(value) for key, value in output.items()}


def _group_marks(events: tuple[_MarkEvent, ...]) -> dict[int, tuple[_MarkEvent, ...]]:
    output: dict[int, list[_MarkEvent]] = {}
    for event in events:
        output.setdefault(event.timestamp_ms, []).append(event)
    return {key: tuple(value) for key, value in output.items()}


def _validate_lifecycles(lifecycles: tuple[MarkedLifecycle, ...]) -> None:
    if not lifecycles:
        raise ValueError("mark-to-market replay requires lifecycles")
    ids = [row.trade_id for row in lifecycles]
    if len(ids) != len(set(ids)):
        raise ValueError("mark-to-market lifecycle IDs must be unique")
    by_symbol: dict[str, list[MarkedLifecycle]] = {}
    for row in lifecycles:
        by_symbol.setdefault(row.symbol, []).append(row)
    for symbol, rows in by_symbol.items():
        ordered = sorted(rows, key=lambda row: row.entry_time_ms)
        if any(
            current.entry_time_ms < prior.exit_time_ms
            for prior, current in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError(f"overlapping accepted {symbol} lifecycles are invalid")


def _validate_lifecycle(row: MarkedLifecycle) -> None:
    if (
        not row.trade_id.strip()
        or not row.strategy_id.strip()
        or not row.symbol.strip()
    ):
        raise ValueError("marked lifecycle identities must be non-empty")
    if row.side not in {"long", "short"}:
        raise ValueError("marked lifecycle side must be long or short")
    if row.entry_time_ms < 0 or row.exit_time_ms <= row.entry_time_ms:
        raise ValueError("marked lifecycle timestamps must be causal")
    for value, label in (
        (row.entry_price, "entry_price"),
        (row.exit_price, "exit_price"),
        (row.quantity, "quantity"),
    ):
        _positive(value, label)
    for value, label in (
        (row.entry_fee_usd, "entry_fee_usd"),
        (row.exit_fee_usd, "exit_fee_usd"),
    ):
        _nonnegative(value, label)
    _finite(row.funding_cashflow_usd, "funding_cashflow_usd")
    _finite(row.net_pnl_usd, "net_pnl_usd")
    sign = 1.0 if row.side == "long" else -1.0
    expected = sign * row.quantity * (row.exit_price - row.entry_price)
    expected += row.funding_cashflow_usd - row.entry_fee_usd - row.exit_fee_usd
    if not math.isclose(expected, row.net_pnl_usd, abs_tol=0.01):
        raise ValueError(f"marked lifecycle does not reconcile: {row.trade_id}")


def _elapsed_fraction(row: MarkedLifecycle, timestamp_ms: int) -> float:
    elapsed = max(min(timestamp_ms, row.exit_time_ms) - row.entry_time_ms, 0)
    return elapsed / (row.exit_time_ms - row.entry_time_ms)


def _update_drawdown(peak: float, maximum: float, equity: float) -> tuple[float, float]:
    updated_peak = max(peak, equity)
    drawdown = 100.0 * (equity / updated_peak - 1.0)
    return updated_peak, min(maximum, drawdown)


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    _positive(result, label)
    return result


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
