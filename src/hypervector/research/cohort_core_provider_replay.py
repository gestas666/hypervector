"""Bounded historical extraction of production core-provider decisions.

Daily batches preserve the provider code, with up to one additional day of
indicator history relative to a rolling live poll. Consumers must validate
rolling-window parity before calling these records exact live decisions.
No orders, fills, account state, or profitability are inferred here.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pandas as pd

from hypervector.live.multi_asset_default_collectors import (
    DefaultProviderCollectorProtocol,
)
from hypervector.live.multi_asset_signal_source import ProviderEvaluation

_CORE_SYMBOLS = frozenset({"BTC", "ETH", "SOL", "HYPE"})
_SOURCES = frozenset({"hl", "hl_gap_fill"})
_MINUTE = pd.Timedelta(minutes=1)
_DAY = pd.Timedelta(days=1)
_CONTRACT_FIELDS = (
    "strategy_id",
    "symbol",
    "decision_time_ms",
    "reference_price",
    "decision_action",
    "eligible",
    "reason",
    "side",
    "exit_sides",
    "exit_reason",
    "primary_regime",
    "state_1m",
    "state_5m",
    "context_15m",
    "target_anchor",
    "trigger",
    "confidence",
    "backend_non_action_reason",
)


@dataclass(frozen=True)
class CoreReplayWindow:
    """Decision bounds (start, end] and production lookback duration."""

    start: pd.Timestamp
    end: pd.Timestamp
    retention_days: int

    def __post_init__(self) -> None:
        """Require aware ordered minute boundaries and positive whole days."""
        if any(value.tzinfo is None for value in (self.start, self.end)):
            raise ValueError("core replay bounds must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("core replay start must precede end")
        if any(value.floor("min") != value for value in (self.start, self.end)):
            raise ValueError("core replay bounds must align to complete minutes")
        if (
            isinstance(self.retention_days, bool)
            or not isinstance(self.retention_days, int)
            or self.retention_days < 1
        ):
            raise ValueError("core replay retention_days must be a positive integer")


@dataclass(frozen=True)
class CoreProviderBatch:
    """Unfiltered provider decisions plus explicit source uncertainty counts."""

    start: pd.Timestamp
    end: pd.Timestamp
    evaluations: tuple[ProviderEvaluation, ...]
    input_minutes: int
    missing_input_minutes: int
    gap_filled_input_minutes: int


def iter_core_provider_batches(
    bars: pd.DataFrame,
    symbol: str,
    window: CoreReplayWindow,
    collector: DefaultProviderCollectorProtocol,
) -> Iterator[CoreProviderBatch]:
    """Yield chronological daily batches without removing exits or weak signals."""
    if symbol not in _CORE_SYMBOLS:
        raise ValueError(f"unsupported core replay symbol: {symbol!r}")
    _validate_bars(bars, window)
    start = window.start
    while start < window.end:
        end = min(start + _DAY, window.end)
        warmup = start - window.retention_days * _DAY
        inputs = bars.loc[bars.timestamp.ge(warmup) & bars.timestamp.lt(end)].copy()
        batch = collector(
            inputs,
            symbol=symbol,
            observed_at=end,
            after_decision_time_ms=_epoch_ms(start),
        )
        _validate_evaluations(batch.evaluations, symbol, start, end)
        yield CoreProviderBatch(
            start,
            end,
            batch.evaluations,
            len(inputs),
            int((end - warmup) / _MINUTE) - len(inputs),
            int(inputs.source.eq("hl_gap_fill").sum()),
        )
        start = end


def evaluation_contract(row: ProviderEvaluation) -> dict[str, object]:
    """Return exact execution and regime fields for replay/parity artifacts."""
    payload = row.as_payload()
    return {field: payload[field] for field in _CONTRACT_FIELDS}


def _validate_bars(bars: pd.DataFrame, window: CoreReplayWindow) -> None:
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    if missing := sorted(required.difference(bars.columns)):
        raise ValueError(f"core replay bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars.timestamp)
    if times.tz is None or times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError("core replay timestamps must be aware, unique and ordered")
    if times.empty or not times.floor("min").equals(times):
        raise ValueError("core replay requires nonempty minute-aligned source bars")
    if (
        times[0] > window.start - window.retention_days * _DAY
        or times[-1] < window.end - _MINUTE
    ):
        raise ValueError("core replay source does not cover warmup and scoring bounds")
    if not set(bars.source).issubset(_SOURCES):
        raise ValueError("core replay source must explicitly identify hl/hl_gap_fill")


def _validate_evaluations(
    rows: tuple[ProviderEvaluation, ...],
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    previous = _epoch_ms(start)
    for row in rows:
        if row.symbol != symbol or not previous < row.decision_time_ms <= _epoch_ms(
            end
        ):
            raise ValueError(
                "core provider returned duplicate, wrong-symbol or out-of-window decisions"
            )
        previous = row.decision_time_ms


def _epoch_ms(value: pd.Timestamp) -> int:
    return int(value.timestamp() * 1000)
