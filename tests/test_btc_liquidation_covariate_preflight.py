"""Outcome-blind timing preflight for BTC liquidation development replay."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from hypervector.research.btc_liquidation_covariate_inputs import ArchiveHour
from hypervector.research.btc_liquidation_covariate_models import (
    BookSnapshot,
    ReplayEpisode,
    VisibleLevel,
)
from hypervector.research.btc_liquidation_covariate_preflight import (
    assess_development_book_timing,
)
from hypervector.research.btc_liquidation_covariate_windows import (
    MergedCovariateWindow,
)


def _levels(best: int, step: int) -> tuple[VisibleLevel, ...]:
    """Build exact 20-level visible depth."""
    return tuple(
        VisibleLevel(Decimal(best + step * index), Decimal("10")) for index in range(20)
    )


def _book(timestamp_ms: int) -> BookSnapshot:
    """Build one complete uncrossed book."""
    return BookSnapshot(timestamp_ms, _levels(100, -1), _levels(101, 1))


def _hour(start_ms: int, suffix: str) -> ArchiveHour:
    """Build one synthetic paired archive hour."""
    return ArchiveHour(
        start_ms,
        start_ms + 3_600_000,
        Path(f"book-{suffix}"),
        Path(f"trade-{suffix}"),
    )


def test_preflight_extends_past_planned_end_for_entry_anchored_horizon() -> None:
    """Use an acquired next hour when entry latency pushes the exit past plan end."""
    episode = ReplayEpisode(
        "episode-a",
        "development",
        "continuation_long",
        2_689_000,
        Decimal("100"),
        ("5s_p95",),
    )
    window = MergedCovariateWindow(
        "development",
        2_639_000,
        3_599_000,
        (episode.episode_id,),
    )
    rows = (_book(2_701_000), _book(3_601_500))

    def loader(
        paths: tuple[Path, ...],
        *,
        start_ms: int,
        end_ms: int,
    ) -> tuple[BookSnapshot, ...]:
        """Return in-memory rows inside the requested half-open interval."""
        assert paths
        return tuple(row for row in rows if start_ms <= row.ts_exchange_ms < end_ms)

    result = assess_development_book_timing(
        (window,),
        (episode,),
        (_hour(0, "a"), _hour(3_600_000, "b")),
        horizons_ms=(900_000,),
        book_loader=loader,
    )

    assert len(result) == 1
    assert result[0].entry_book_time_ms == 2_701_000
    assert result[0].horizon_book_times_ms == ((900_000, 3_601_500),)
    assert result[0].technical_complete is True


def test_preflight_reports_missing_post_entry_horizon_without_fabrication() -> None:
    """Retain an incomplete result when no acquired hour covers the target."""
    episode = ReplayEpisode(
        "episode-a",
        "development",
        "continuation_long",
        2_689_000,
        Decimal("100"),
        ("5s_p95",),
    )
    window = MergedCovariateWindow(
        "development",
        2_639_000,
        3_599_000,
        (episode.episode_id,),
    )
    rows = (_book(2_701_000),)

    def loader(
        paths: tuple[Path, ...],
        *,
        start_ms: int,
        end_ms: int,
    ) -> tuple[BookSnapshot, ...]:
        """Return only the available first-hour entry book."""
        assert paths
        return tuple(row for row in rows if start_ms <= row.ts_exchange_ms < end_ms)

    result = assess_development_book_timing(
        (window,),
        (episode,),
        (_hour(0, "a"),),
        horizons_ms=(900_000,),
        book_loader=loader,
    )

    assert result[0].entry_book_time_ms == 2_701_000
    assert result[0].horizon_book_times_ms == ((900_000, None),)
    assert result[0].technical_complete is False
