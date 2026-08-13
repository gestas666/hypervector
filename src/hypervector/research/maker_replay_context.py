"""Causal mark/oracle and funding context for maker replay."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from hypervector.research.maker_replay_models import MakerReplayConfig, ReplayState
from hypervector.research.maker_replay_risk import (
    apply_book_liquidation,
    update_drawdown,
    update_peak_protection,
)


@dataclass(frozen=True)
class MakerReplayContext:
    """Validated venue price and settled-funding evidence."""

    prices: pd.DataFrame
    funding: pd.DataFrame

    def __post_init__(self) -> None:
        object.__setattr__(self, "prices", _validate_prices(self.prices))
        object.__setattr__(self, "funding", _validate_funding(self.funding))

    @classmethod
    def from_parquet(cls, prices_path: str, funding_path: str) -> MakerReplayContext:
        """Load normalized immutable context evidence from Parquet files."""
        return cls(pd.read_parquet(prices_path), pd.read_parquet(funding_path))

    def window(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return one half-open chronological context chunk."""
        start_ms = int(pd.Timestamp(start).timestamp() * 1000)
        end_ms = int(pd.Timestamp(end).timestamp() * 1000)
        prices = self.prices.loc[
            self.prices["ts_ms"].between(start_ms, end_ms, inclusive="left")
        ]
        funding = self.funding.loc[
            self.funding["event_ts_ms"].between(start_ms, end_ms, inclusive="left")
        ]
        return prices.reset_index(drop=True), funding.reset_index(drop=True)


def build_event_tape(
    books: pd.DataFrame,
    trades: pd.DataFrame,
    prices: pd.DataFrame | None = None,
    funding: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Interleave market and context evidence using explicit causal priority."""
    frames = [books.assign(event_kind="book", event_priority=2)]
    if not trades.empty:
        frames.append(trades.assign(event_kind="trade", event_priority=3))
    if prices is not None and not prices.empty:
        frames.append(prices.assign(event_kind="price", event_priority=0))
    if funding is not None and not funding.empty:
        events = funding.rename(columns={"event_ts_ms": "ts_ms"})
        frames.append(events.assign(event_kind="funding", event_priority=1))
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["ts_ms", "event_priority"])
        .reset_index(drop=True)
    )


def enable_authentic_context(state: ReplayState) -> None:
    """Mark replay state as requiring authentic rather than proxy context."""
    state.authentic_context_enabled = True


def remember_book(
    state: ReplayState, timestamp: pd.Timestamp, bid: float, ask: float
) -> None:
    """Retain the latest causally observed executable top of book."""
    state.last_book_ms = int(timestamp.timestamp() * 1000)
    state.last_bid = bid
    state.last_ask = ask


def apply_price_event(
    state: ReplayState,
    timestamp: pd.Timestamp,
    mark_price: float,
    oracle_price: float,
    config: MakerReplayConfig,
) -> None:
    """Update authentic prices and evaluate risk without future BBO evidence."""
    timestamp_ms = int(timestamp.timestamp() * 1000)
    state.latest_price_ms = timestamp_ms
    state.latest_mark_price = mark_price
    state.latest_oracle_price = oracle_price
    state.authentic_price_updates += 1
    if state.position is None:
        update_drawdown(state, mark_price)
        return
    update_drawdown(state, mark_price)
    update_peak_protection(state, timestamp, mark_price, config)
    if not _fresh_book(state, timestamp_ms, config.context_max_age_seconds):
        return
    apply_book_liquidation(
        state,
        timestamp,
        float(state.last_bid),
        float(state.last_ask),
        config,
        trigger_mark=mark_price,
    )


def mark_for_book(
    state: ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> float | None:
    """Select only backward-known fresh mark evidence for one book event."""
    if not state.authentic_context_enabled:
        return (bid + ask) / 2.0
    status = _price_status(state, timestamp, config.context_max_age_seconds)
    if status == "missing":
        if state.position is not None:
            state.missing_mark_events += 1
            state.execution_economics_conclusive = False
        return None
    if status == "stale":
        if state.position is not None:
            state.stale_mark_events += 1
            state.execution_economics_conclusive = False
        return None
    return state.latest_mark_price


def apply_funding_event(
    state: ReplayState,
    timestamp: pd.Timestamp,
    funding_rate: float,
    config: MakerReplayConfig,
) -> None:
    """Book one signed funding cashflow using fresh backward-known oracle."""
    position = state.position
    if position is None or timestamp <= position.entry_time:
        return
    status = _price_status(state, timestamp, config.context_max_age_seconds)
    if status == "missing":
        state.missing_oracle_settlements += 1
        state.execution_economics_conclusive = False
        return
    if status == "stale":
        state.stale_oracle_settlements += 1
        state.execution_economics_conclusive = False
        return
    oracle = float(state.latest_oracle_price)
    side_sign = -1.0 if position.direction == "long" else 1.0
    cashflow = side_sign * position.quantity * oracle * funding_rate
    if position.open_funding_basis is None:
        position.open_funding_basis = position.funding_cashflow
    position.funding_cashflow += cashflow
    position.open_funding_basis += cashflow
    state.equity += cashflow
    state.funding_settlements += 1
    state.funding_cashflow += cashflow
    state.funding_paid += max(-cashflow, 0.0)
    state.funding_received += max(cashflow, 0.0)
    if state.latest_mark_price is not None:
        update_drawdown(state, state.latest_mark_price)


def _price_status(
    state: ReplayState, timestamp: pd.Timestamp, max_age_seconds: float
) -> str:
    if (
        state.latest_price_ms is None
        or state.latest_mark_price is None
        or state.latest_oracle_price is None
    ):
        return "missing"
    timestamp_ms = int(timestamp.timestamp() * 1000)
    age_ms = timestamp_ms - state.latest_price_ms
    if age_ms < 0:
        raise RuntimeError("replay context attempted forward price selection")
    return "stale" if age_ms > max_age_seconds * 1000.0 else "fresh"


def _fresh_book(state: ReplayState, timestamp_ms: int, max_age_seconds: float) -> bool:
    if state.last_book_ms is None or state.last_bid is None or state.last_ask is None:
        return False
    age_ms = timestamp_ms - state.last_book_ms
    return 0 <= age_ms <= max_age_seconds * 1000.0


def _validate_prices(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"ts_ms", "mark_price", "oracle_price"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"replay prices missing columns: {sorted(missing)}")
    result = frame.loc[:, sorted(required)].copy()
    return _validate_context_frame(result, "ts_ms", ("mark_price", "oracle_price"))


def _validate_funding(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"event_ts_ms", "funding_rate"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"replay funding missing columns: {sorted(missing)}")
    result = frame.loc[:, ["event_ts_ms", "funding_rate"]].copy()
    return _validate_context_frame(result, "event_ts_ms", ())


def _validate_context_frame(
    frame: pd.DataFrame, timestamp_column: str, positive_columns: tuple[str, ...]
) -> pd.DataFrame:
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    finite = frame.map(lambda value: math.isfinite(float(value)))
    if not finite.to_numpy().all():
        raise ValueError("replay context values must be finite")
    timestamps = frame[timestamp_column]
    if (timestamps <= 0.0).any() or (timestamps % 1 != 0).any():
        raise ValueError(
            "replay context timestamps must be positive integer milliseconds"
        )
    if frame[timestamp_column].duplicated().any():
        raise ValueError(f"replay context has duplicate {timestamp_column}")
    frame = frame.sort_values(timestamp_column).reset_index(drop=True)
    if any((frame[column] <= 0.0).any() for column in positive_columns):
        raise ValueError("replay context prices must be positive")
    return frame
