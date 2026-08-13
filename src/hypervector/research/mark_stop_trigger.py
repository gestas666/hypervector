"""Sampled Hyperliquid mark-price stop-trigger bounds."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.shared_portfolio_models import Direction


class MarkQueryGapError(ValueError):
    """An active mark-price query crosses an unobserved interval."""


@dataclass(frozen=True)
class MarkStopCrossing:
    """First sampled venue mark observed beyond a stop boundary."""

    timestamp_ms: int
    mark_price: float


@dataclass(frozen=True)
class MarkObservation:
    """One timestamped sampled venue mark."""

    timestamp_ms: int
    mark_price: float


class SampledMarkSeries:
    """Validated chronological mark observations with a strict gap contract."""

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        maximum_gap_ms: int,
        query_scoped: bool = False,
    ) -> None:
        _positive_integer(maximum_gap_ms, "maximum_gap_ms")
        missing = {"ts_ms", "mark_price"}.difference(frame.columns)
        if missing:
            raise ValueError(
                f"mark observations are missing columns: {sorted(missing)}"
            )
        timestamps = _timestamps(frame["ts_ms"])
        marks = _marks(frame["mark_price"])
        if len(timestamps) < 2:
            raise ValueError("mark observations require at least two rows")
        gaps = np.diff(timestamps)
        if np.any(gaps <= 0):
            raise ValueError("mark timestamps must be unique and increasing")
        maximum_observed = int(gaps.max())
        if maximum_observed > maximum_gap_ms and not query_scoped:
            raise ValueError(
                f"mark observation gap {maximum_observed}ms exceeds {maximum_gap_ms}ms"
            )
        self._timestamps = timestamps
        self._marks = marks
        self._maximum_gap_ms = maximum_observed
        self._contract_gap_ms = maximum_gap_ms
        self._query_scoped = query_scoped

    @property
    def maximum_observed_gap_ms(self) -> int:
        """Return the largest adjacent mark-observation gap."""
        return self._maximum_gap_ms

    def first_crossing(
        self,
        direction: Direction,
        stop_price: float,
        start_time_ms: int,
        end_time_ms: int,
    ) -> MarkStopCrossing | None:
        """Return the first sampled adverse mark in a half-open window."""
        _validate_query(direction, stop_price, start_time_ms, end_time_ms)
        left, right = self._raw_query_bounds(start_time_ms, end_time_ms)
        window = self._marks[left:right]
        crossed = window <= stop_price if direction == "long" else window >= stop_price
        matches = np.flatnonzero(crossed)
        if not len(matches):
            if self._query_scoped:
                self._validate_query_gaps(start_time_ms, end_time_ms, left, right)
            return None
        index = left + int(matches[0])
        if self._query_scoped:
            crossing_end_ms = int(self._timestamps[index]) + 1
            self._validate_query_gaps(
                start_time_ms,
                crossing_end_ms,
                left,
                index + 1,
            )
        return MarkStopCrossing(
            int(self._timestamps[index]),
            float(self._marks[index]),
        )

    def observations(
        self,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[MarkObservation, ...]:
        """Return sampled marks in one half-open timestamp window."""
        _validate_window(start_time_ms, end_time_ms)
        left, right = self._query_bounds(start_time_ms, end_time_ms)
        return tuple(
            MarkObservation(int(self._timestamps[index]), float(self._marks[index]))
            for index in range(left, right)
        )

    def _query_bounds(self, start_time_ms: int, end_time_ms: int) -> tuple[int, int]:
        """Resolve one query and enforce its active-window gap contract."""
        left, right = self._raw_query_bounds(start_time_ms, end_time_ms)
        if self._query_scoped:
            self._validate_query_gaps(start_time_ms, end_time_ms, left, right)
        return left, right

    def _raw_query_bounds(
        self,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[int, int]:
        """Resolve half-open query indexes without asserting future coverage."""
        left = int(np.searchsorted(self._timestamps, start_time_ms, side="left"))
        right = int(np.searchsorted(self._timestamps, end_time_ms, side="left"))
        return left, right

    def _validate_query_gaps(
        self,
        start_time_ms: int,
        end_time_ms: int,
        left: int,
        right: int,
    ) -> None:
        """Fail when an active mark query contains an unobserved interval."""
        if left >= right:
            self._validate_empty_query_gap(start_time_ms, end_time_ms, left)
            return
        timestamps = self._timestamps[left:right]
        edge_gaps = (timestamps[0] - start_time_ms, end_time_ms - timestamps[-1])
        internal = int(np.diff(timestamps).max()) if len(timestamps) > 1 else 0
        maximum = max(int(edge_gaps[0]), int(edge_gaps[1]), internal)
        if maximum > self._contract_gap_ms:
            raise MarkQueryGapError(
                f"mark query gap {maximum}ms exceeds {self._contract_gap_ms}ms"
            )

    def _validate_empty_query_gap(
        self,
        start_time_ms: int,
        end_time_ms: int,
        insertion_index: int,
    ) -> None:
        previous = (
            int(self._timestamps[insertion_index - 1]) if insertion_index > 0 else None
        )
        following = (
            int(self._timestamps[insertion_index])
            if insertion_index < len(self._timestamps)
            else None
        )
        if previous is not None and following is not None:
            gap_ms = following - previous
        elif previous is not None:
            gap_ms = end_time_ms - previous
        elif following is not None:
            gap_ms = following - start_time_ms
        else:
            raise MarkQueryGapError("mark query gap contains no observations")
        if gap_ms > self._contract_gap_ms:
            raise MarkQueryGapError(
                f"mark query gap {gap_ms}ms exceeds {self._contract_gap_ms}ms"
            )


def _timestamps(series: pd.Series) -> np.ndarray:
    numeric = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or np.any(numeric < 0.0):
        raise ValueError("mark ts_ms must be non-negative integers")
    if np.any(numeric != np.floor(numeric)):
        raise ValueError("mark ts_ms must be non-negative integers")
    return numeric.astype(np.int64)


def _marks(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise ValueError("mark_price must be positive and finite")
    return values


def _validate_query(
    direction: object,
    stop_price: float,
    start_time_ms: int,
    end_time_ms: int,
) -> None:
    if direction not in ("long", "short"):
        raise ValueError("direction must be long or short")
    if isinstance(stop_price, bool) or not math.isfinite(stop_price):
        raise ValueError("stop_price must be positive and finite")
    if stop_price <= 0.0:
        raise ValueError("stop_price must be positive and finite")
    _validate_window(start_time_ms, end_time_ms)


def _validate_window(start_time_ms: int, end_time_ms: int) -> None:
    _nonnegative_integer(start_time_ms, "start_time_ms")
    _nonnegative_integer(end_time_ms, "end_time_ms")
    if end_time_ms <= start_time_ms:
        raise ValueError("end_time_ms must follow start_time_ms")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
