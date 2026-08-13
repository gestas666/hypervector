"""Causal open-lifecycle path diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from hypervector.research.cohort_open_trade_path import (
    build_open_trade_extension_path,
    build_open_trade_path,
)


@dataclass(frozen=True)
class _Candle:
    timestamp_ms: int
    high: float
    low: float
    close: float = 100.0


@pytest.mark.parametrize(
    ("side", "mark"),
    [("long", 105.0), ("short", 95.0)],
)
def test_open_path_is_directionally_symmetric_and_causal(
    side: str,
    mark: float,
) -> None:
    """Only fully post-entry completed candles contribute to excursions."""
    candles = {
        60_000: _Candle(60_000, 150.0, 50.0),
        120_000: _Candle(120_000, 110.0, 95.0),
        180_000: _Candle(180_000, 105.0, 90.0),
        240_000: _Candle(240_000, 200.0, 1.0),
    }
    path = build_open_trade_path(
        candles,
        side,
        {"venue_timestamp_ms": 60_100, "price": 100.0},
        {"mark_price": mark},
        240_000,
    )

    assert path["status"] == "observed"
    assert path["completed_bars"] == 2
    assert path["first_timestamp_ms"] == 120_000
    assert path["last_timestamp_ms"] == 180_000
    assert path["current_directional_return_bps"] == pytest.approx(500.0)
    assert path["maximum_favorable_excursion_bps"] == pytest.approx(1_000.0)
    assert path["maximum_adverse_excursion_bps"] == pytest.approx(1_000.0)
    assert path["peak_giveback_bps"] == pytest.approx(500.0)


def test_extension_path_uses_last_completed_soft_boundary_close() -> None:
    """Post-soft evidence measures incremental extension value, not entry return."""
    candles = {
        60_000: _Candle(60_000, 104.0, 98.0, 102.0),
        120_000: _Candle(120_000, 108.0, 101.0, 106.0),
        180_000: _Candle(180_000, 107.0, 100.0, 104.0),
        240_000: _Candle(240_000, 200.0, 1.0, 150.0),
    }

    path = build_open_trade_extension_path(
        candles,
        "long",
        soft_deadline_ms=130_000,
        marked_economics={"mark_price": 105.0},
        as_of_ms=240_000,
    )

    assert path["status"] == "observed"
    assert path["boundary_timestamp_ms"] == 130_000
    assert path["baseline_timestamp_ms"] == 60_000
    assert path["baseline_price"] == pytest.approx(102.0)
    assert path["completed_bars"] == 1
    assert path["current_directional_return_bps"] == pytest.approx(
        (105.0 / 102.0 - 1.0) * 10_000.0
    )
    assert path["maximum_favorable_excursion_bps"] == pytest.approx(
        (107.0 / 102.0 - 1.0) * 10_000.0
    )
    assert path["maximum_adverse_excursion_bps"] == pytest.approx(
        (1.0 - 100.0 / 102.0) * 10_000.0
    )


def test_extension_path_is_pending_before_soft_boundary() -> None:
    """A not-yet-crossed deadline cannot produce success-shaped path evidence."""
    path = build_open_trade_extension_path(
        {},
        "short",
        soft_deadline_ms=130_000,
        marked_economics={"mark_price": 100.0},
        as_of_ms=120_000,
    )

    assert path["status"] == "pending_soft_deadline"
    assert path["completed_bars"] == 0
    assert path["current_directional_return_bps"] is None
