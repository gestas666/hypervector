"""Fail-closed continuity evidence for sampled active book paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_exact_depth_books import book_time

Record = Mapping[str, object]


def active_book_gap(
    entry: Record,
    end: Record,
    books: Sequence[Record],
    maximum_ms: int,
) -> dict[str, object] | None:
    """Return exact evidence when an active sampled path exceeds its limit."""
    start_ms = book_time(entry)
    end_ms = book_time(end)
    times = [
        start_ms,
        *(book_time(row) for row in books if start_ms < book_time(row) <= end_ms),
    ]
    gap_start, gap_end = max(zip(times, times[1:]), key=lambda pair: pair[1] - pair[0])
    maximum_gap = gap_end - gap_start
    if maximum_gap <= maximum_ms:
        return None
    return {
        "status": "active_book_path_gap",
        "current_exit_time_ms": end_ms,
        "maximum_active_book_gap_ms": maximum_gap,
        "maximum_allowed_active_book_gap_ms": maximum_ms,
        "active_book_gap_start_ms": gap_start,
        "active_book_gap_end_ms": gap_end,
    }


def active_book_gap_attempt(
    base: Record,
    entry_fields: Record,
    gap: Record,
    deadline_ms: int,
) -> dict[str, object]:
    """Build one entered but technically censored lifecycle attempt."""
    return {**base, **entry_fields, "deadline_time_ms": deadline_ms, **gap}
