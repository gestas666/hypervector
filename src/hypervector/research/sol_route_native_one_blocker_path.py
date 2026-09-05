"""Technical path coverage for the SOL route-native shadow."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence

from hypervector.data.hl_events import StreamGap
from hypervector.research.cohort_one_blocker_execution_types import Book
from hypervector.research.sol_route_native_one_blocker_models import MarkObservation

_SYMBOL = "SOL"
_MAXIMUM_MARK_GAP_MS = 5_000
_MAXIMUM_L2_GAP_MS = 15_000


def has_unresolved_stream_gap(
    gaps: Sequence[StreamGap],
    marks: Sequence[MarkObservation],
    books: Sequence[Book],
    start_ms: int,
    end_ms: int,
) -> bool:
    """Return whether an overlapping disconnect leaves a consumed path unresolved."""
    mark_times = tuple(mark.observed_ts_ms for mark in marks)
    book_times = tuple(book.recv_ts_ms for book in books)
    for gap in gaps:
        if gap.symbol != _SYMBOL:
            raise ValueError("SOL shadow gap evidence has the wrong symbol")
        if not _overlaps(gap, start_ms, end_ms):
            continue
        if not _declared_l2_interval_is_bounded(gap):
            return True
        detected_ms = min(max(gap.detected_ts_ns // 1_000_000, start_ms), end_ms)
        if "activeAssetCtx" in gap.channel and not _crossing_is_bounded(
            mark_times, detected_ms, start_ms, end_ms, _MAXIMUM_MARK_GAP_MS
        ):
            return True
        if "l2Book" in gap.channel and not _crossing_is_bounded(
            book_times, detected_ms, start_ms, end_ms, _MAXIMUM_L2_GAP_MS
        ):
            return True
    return False


def _overlaps(gap: StreamGap, start_ms: int, end_ms: int) -> bool:
    detected_ms = gap.detected_ts_ns // 1_000_000
    gap_start = gap.previous_exchange_ts_ms or detected_ms
    gap_end = gap.next_exchange_ts_ms
    return gap_start <= end_ms and (gap_end is None or gap_end >= start_ms)


def _declared_l2_interval_is_bounded(gap: StreamGap) -> bool:
    if "l2Book" not in gap.channel:
        return True
    start = gap.previous_exchange_ts_ms
    end = gap.next_exchange_ts_ms
    return (
        start is not None and end is not None and 0 <= end - start <= _MAXIMUM_L2_GAP_MS
    )


def _crossing_is_bounded(
    timestamps: Sequence[int],
    point_ms: int,
    start_ms: int,
    end_ms: int,
    maximum_gap_ms: int,
) -> bool:
    scoped = tuple(value for value in timestamps if start_ms <= value <= end_ms)
    index = bisect_right(scoped, point_ms)
    left = scoped[index - 1] if index else start_ms
    right = scoped[index] if index < len(scoped) else end_ms
    return right - left <= maximum_gap_ms
