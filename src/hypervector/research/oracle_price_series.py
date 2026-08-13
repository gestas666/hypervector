"""Causal sampled-oracle lookup for historical funding settlements."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OraclePriceObservation:
    """One causal oracle observation selected for a settlement."""

    timestamp_ms: int
    oracle_price: float
    staleness_ms: int


class CausalOraclePriceSeries:
    """Validated oracle samples with a strict last-known-price contract."""

    def __init__(self, frame: pd.DataFrame, *, maximum_staleness_ms: int) -> None:
        _positive_integer(maximum_staleness_ms, "maximum_staleness_ms")
        missing = {"ts_ms", "oracle_price"}.difference(frame.columns)
        if missing:
            raise ValueError(
                f"oracle observations are missing columns: {sorted(missing)}"
            )
        timestamps = _timestamps(frame["ts_ms"])
        prices = _prices(frame["oracle_price"])
        if len(timestamps) == 0:
            raise ValueError("oracle observations require at least one row")
        if len(timestamps) > 1 and np.any(np.diff(timestamps) <= 0):
            raise ValueError("oracle timestamps must be unique and increasing")
        self._timestamps = timestamps
        self._prices = prices
        self._maximum_staleness_ms = maximum_staleness_ms

    def at_or_before(self, timestamp_ms: int) -> OraclePriceObservation:
        """Return the latest non-stale oracle sample known at settlement time."""
        _nonnegative_integer(timestamp_ms, "timestamp_ms")
        index = int(np.searchsorted(self._timestamps, timestamp_ms, side="right")) - 1
        if index < 0:
            raise LookupError("no causal oracle observation exists at settlement")
        observed_ms = int(self._timestamps[index])
        staleness_ms = timestamp_ms - observed_ms
        if staleness_ms > self._maximum_staleness_ms:
            raise LookupError(
                f"oracle observation is stale by {staleness_ms}ms; "
                f"maximum is {self._maximum_staleness_ms}ms"
            )
        return OraclePriceObservation(
            observed_ms,
            float(self._prices[index]),
            staleness_ms,
        )


def _timestamps(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0.0):
        raise ValueError("oracle ts_ms must be non-negative integers")
    if np.any(values != np.floor(values)):
        raise ValueError("oracle ts_ms must be non-negative integers")
    return values.astype(np.int64)


def _prices(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise ValueError("oracle_price must be positive and finite")
    return values


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
