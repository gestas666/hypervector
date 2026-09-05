"""Fill-time stop and target resolution for shared portfolio research."""

from __future__ import annotations

from hypervector.research.shared_portfolio_inputs import BarEntrySignal
from hypervector.research.shared_portfolio_models import (
    Direction,
    SharedPortfolioConfig,
)
from hypervector.research.shared_portfolio_pricing import margin_barrier


def entry_barriers(
    pending: BarEntrySignal,
    entry: float,
    config: SharedPortfolioConfig,
) -> tuple[float | None, float | None]:
    """Resolve a stop band first, then derive an exact fill-time R target."""
    raw_stop = pending.stop_price or margin_barrier(
        entry,
        pending.direction,
        config.stop_margin_pct,
        config.leverage,
        favorable=False,
    )
    stop = _clamp_stop_band(
        raw_stop,
        entry,
        pending.direction,
        config.minimum_stop_distance_bps,
        config.maximum_stop_distance_bps,
    )
    target = pending.target_price or _configured_target(
        entry,
        stop,
        pending.direction,
        config,
    )
    return target, stop


def _configured_target(
    entry: float,
    stop: float | None,
    direction: Direction,
    config: SharedPortfolioConfig,
) -> float | None:
    if config.target_r_multiple is not None and _is_adverse_stop(
        stop, entry, direction
    ):
        risk = abs(entry - float(stop))
        favorable = risk * config.target_r_multiple
        return entry + favorable if direction == "long" else entry - favorable
    return margin_barrier(
        entry,
        direction,
        config.target_margin_pct,
        config.leverage,
        favorable=True,
    )


def _clamp_stop_band(
    stop: float | None,
    entry: float,
    direction: Direction,
    minimum_bps: float | None,
    maximum_bps: float | None,
) -> float | None:
    if not _is_adverse_stop(stop, entry, direction):
        return stop
    distance_bps = abs(entry - float(stop)) / entry * 10_000.0
    bounded_bps = distance_bps
    if minimum_bps is not None:
        bounded_bps = max(bounded_bps, minimum_bps)
    if maximum_bps is not None:
        bounded_bps = min(bounded_bps, maximum_bps)
    fraction = bounded_bps / 10_000.0
    return entry * (1.0 - fraction if direction == "long" else 1.0 + fraction)


def _is_adverse_stop(
    stop: float | None,
    entry: float,
    direction: Direction,
) -> bool:
    if stop is None:
        return False
    return stop < entry if direction == "long" else stop > entry
