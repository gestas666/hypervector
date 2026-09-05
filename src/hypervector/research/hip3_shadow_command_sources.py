"""Shared bounded public inputs for HIP-3 shadow lifecycle commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Protocol, cast

import pandas as pd

Record = dict[str, object]
_DAY_MS = 86_400_000


class CandleFetcher(Protocol):
    """Unsigned public candle acquisition boundary."""

    def __call__(
        self, symbol: str, timeframe: str, lookback_days: float, *, end_ms: int
    ) -> pd.DataFrame:
        """Return exact public completed candles."""


class FundingFetcher(Protocol):
    """Unsigned public funding acquisition boundary."""

    def __call__(
        self,
        symbol: str,
        *,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.DataFrame:
        """Return exact public hourly settlements."""


def bounded_decisions(
    rows: Sequence[Mapping[str, object]],
    observed_at: int,
    interval_ms: int,
    decision_start_ms: int | None = None,
) -> tuple[tuple[Record, ...], int]:
    """Bound decision rows by causal receipt and return candle start."""
    if decision_start_ms is not None:
        _positive_integer(decision_start_ms, "decision start")
    output: list[Record] = []
    first_decision: int | None = None
    for row in rows:
        decision = _mapping(row.get("decision"), "decision")
        decision_ms = _positive_integer(
            decision.get("decision_time_ms"), "decision time"
        )
        observed_ms = _positive_integer(
            decision.get("observed_at_ms"), "decision receipt"
        )
        if observed_ms <= observed_at and (
            decision_start_ms is None or decision_ms >= decision_start_ms
        ):
            output.append(cast(Record, row))
            first_decision = (
                decision_ms
                if first_decision is None
                else min(first_decision, decision_ms)
            )
    if not output or first_decision is None:
        raise ValueError("HIP-3 lifecycle has no decisions in its observed window")
    return tuple(output), first_decision - interval_ms


def bounded_books(
    rows: Sequence[Mapping[str, object]], observed_at: int
) -> tuple[Record, ...]:
    """Select explicit book observations and bound them by causal receipt."""
    output: list[Record] = []
    for row in rows:
        if row.get("event_type") != "book_observation":
            continue
        payload = _mapping(row.get("payload"), "book payload")
        receipt = _positive_integer(payload.get("recv_ts_ms"), "book receipt")
        if receipt <= observed_at:
            output.append(cast(Record, row))
    if not output:
        raise ValueError("HIP-3 lifecycle has no books in its observed window")
    return tuple(output)


def completed_candles(
    fetcher: CandleFetcher,
    symbol: str,
    timeframe: str,
    interval_ms: int,
    start_ms: int,
    observed_at: int,
) -> pd.DataFrame:
    """Fetch and causally bound exact completed public candles."""
    if interval_ms <= 0 or observed_at <= start_ms:
        raise ValueError("HIP-3 lifecycle candle window is invalid")
    lookback = (observed_at - start_ms) / _DAY_MS + 0.25
    frame = fetcher(symbol, timeframe, lookback, end_ms=observed_at).copy()
    if "timestamp" not in frame.columns:
        raise ValueError("HIP-3 lifecycle candle snapshot has no timestamps")
    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    complete = timestamp + pd.to_timedelta(interval_ms, unit="ms") <= pd.Timestamp(
        observed_at, unit="ms", tz="UTC"
    )
    output = frame.loc[
        complete & timestamp.ge(pd.Timestamp(start_ms, unit="ms", tz="UTC"))
    ].copy()
    if output.empty:
        raise ValueError("HIP-3 lifecycle candle snapshot has no completed rows")
    return output


def funding_snapshot(
    fetcher: FundingFetcher,
    symbol: str,
    candles: pd.DataFrame,
    observed_at: int,
) -> pd.DataFrame:
    """Fetch official settlements covering the bounded candle window."""
    start = pd.to_datetime(candles["timestamp"], utc=True).min().floor("h")
    end = pd.Timestamp(observed_at, unit="ms", tz="UTC").floor("h")
    return fetcher(symbol, start_time=start, end_time=end)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 lifecycle {label} must be an object")
    return cast(dict[str, object], value)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"HIP-3 lifecycle {label} must be a positive integer")
    return value


def finite_positive(value: object, label: str) -> float:
    """Return one finite positive command input number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 lifecycle {label} must be numeric")
    output = float(value)
    if not math.isfinite(output) or output <= 0.0:
        raise ValueError(f"HIP-3 lifecycle {label} must be finite and positive")
    return output
