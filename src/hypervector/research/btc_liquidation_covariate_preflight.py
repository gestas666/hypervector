"""Outcome-blind development book-timing preflight."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hypervector.research.btc_liquidation_covariate_inputs import ArchiveHour
from hypervector.research.btc_liquidation_covariate_models import (
    BookSnapshot,
    BookTimingCoverage,
    ReplayEpisode,
)
from hypervector.research.btc_liquidation_covariate_partition import hours_for_window
from hypervector.research.btc_liquidation_covariate_replay import assess_book_timing
from hypervector.research.btc_liquidation_covariate_windows import (
    MergedCovariateWindow,
)


class BookWindowLoader(Protocol):
    """Boundary for reading normalized book rows from explicit source files."""

    def __call__(
        self,
        paths: tuple[Path, ...],
        *,
        start_ms: int,
        end_ms: int,
    ) -> tuple[BookSnapshot, ...]:
        """Return parsed books inside the requested half-open interval."""
        ...


def assess_development_book_timing(
    windows: tuple[MergedCovariateWindow, ...],
    episodes: tuple[ReplayEpisode, ...],
    hours: tuple[ArchiveHour, ...],
    *,
    horizons_ms: tuple[int, ...],
    book_loader: BookWindowLoader,
) -> tuple[BookTimingCoverage, ...]:
    """Measure entry-anchored book coverage without calculating returns."""
    if not horizons_ms:
        raise ValueError("book-timing horizons must be nonempty")
    by_id = _episode_index(episodes)
    planned = tuple(identity for window in windows for identity in window.episode_ids)
    if set(planned) != set(by_id) or len(planned) != len(by_id):
        raise ValueError("development timing inputs do not provide exact coverage")
    output: list[BookTimingCoverage] = []
    for window in windows:
        selected = tuple(by_id[identity] for identity in window.episode_ids)
        output.extend(
            _assess_window(
                window,
                selected,
                hours,
                horizons_ms=horizons_ms,
                book_loader=book_loader,
            )
        )
    return tuple(output)


def _assess_window(
    window: MergedCovariateWindow,
    episodes: tuple[ReplayEpisode, ...],
    hours: tuple[ArchiveHour, ...],
    *,
    horizons_ms: tuple[int, ...],
    book_loader: BookWindowLoader,
) -> tuple[BookTimingCoverage, ...]:
    initial_hours = hours_for_window(hours, window, required_end_ms=window.end_ms)
    initial_books = _load_books(book_loader, initial_hours, window.start_ms)
    preliminary = _assess(episodes, initial_books, horizons_ms)
    entry_times = tuple(
        row.entry_book_time_ms
        for row in preliminary
        if row.entry_book_time_ms is not None
    )
    if not entry_times:
        return preliminary
    required_end_ms = max(entry_times) + max(horizons_ms) + 1
    extended_hours = _extended_hours(hours, window, required_end_ms)
    if extended_hours is None or extended_hours == initial_hours:
        return preliminary
    books = _load_books(book_loader, extended_hours, window.start_ms)
    return _assess(episodes, books, horizons_ms)


def _assess(
    episodes: tuple[ReplayEpisode, ...],
    books: tuple[BookSnapshot, ...],
    horizons_ms: tuple[int, ...],
) -> tuple[BookTimingCoverage, ...]:
    return tuple(
        assess_book_timing(episode, books=books, horizons_ms=horizons_ms)
        for episode in episodes
    )


def _load_books(
    loader: BookWindowLoader,
    hours: tuple[ArchiveHour, ...],
    start_ms: int,
) -> tuple[BookSnapshot, ...]:
    return loader(
        tuple(row.book_path for row in hours),
        start_ms=start_ms,
        end_ms=hours[-1].end_ms,
    )


def _extended_hours(
    hours: tuple[ArchiveHour, ...],
    window: MergedCovariateWindow,
    required_end_ms: int,
) -> tuple[ArchiveHour, ...] | None:
    try:
        return hours_for_window(hours, window, required_end_ms=required_end_ms)
    except ValueError as error:
        if "contiguous requested coverage" not in str(error):
            raise
        return None


def _episode_index(
    episodes: tuple[ReplayEpisode, ...],
) -> dict[str, ReplayEpisode]:
    output = {row.episode_id: row for row in episodes}
    if len(output) != len(episodes):
        raise ValueError("development timing episodes contain duplicate identities")
    return output
