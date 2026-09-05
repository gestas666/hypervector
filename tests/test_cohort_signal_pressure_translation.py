"""Provider-native to routing-publication pressure translation diagnostics."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_causal_book_context import CausalBookSnapshot
from hypervector.research.cohort_signal_candidates import SignalCandidate
from hypervector.research.cohort_signal_pressure_translation import (
    build_signal_pressure_translation,
)

_DECISION_MS = 1_800_000_000_000


def test_pressure_translation_distinguishes_retained_and_flipped_signs() -> None:
    """Causal routing books must expose pressure that reverses after decision."""
    candidates = (
        _candidate("long", 0.20, _DECISION_MS),
        _candidate("short", -0.30, _DECISION_MS + 60_000),
    )
    books = {
        "xyz:SPCX": (
            _book(_DECISION_MS + 1_000, 0.40),
            _book(_DECISION_MS + 61_000, 0.50),
        )
    }

    report = build_signal_pressure_translation(candidates, books, 30_000)

    assert report["coverage"] == {
        "eligible_signals": 2,
        "native_pressure_available": 2,
        "publication_book_matched": 2,
        "publication_book_stale": 0,
        "publication_book_missing": 0,
    }
    provider = report["by_provider_symbol"]["provider|xyz:SPCX"]
    assert provider["translation_state"] == {
        "retained": 1,
        "flipped": 1,
        "neutralized": 0,
        "unavailable": 0,
    }
    assert provider["signals"][0]["native_directional_pressure"] == 0.20
    assert provider["signals"][0]["publication_directional_opi"] == 0.40
    assert provider["signals"][1]["native_directional_pressure"] == 0.30
    assert provider["signals"][1]["publication_directional_opi"] == -0.50


def test_future_or_stale_book_cannot_define_publication_pressure() -> None:
    """Only a fresh nonfuture routing-publication book is causal evidence."""
    candidates = (_candidate("long", 0.20, _DECISION_MS),)
    books = {
        "xyz:SPCX": (
            _book(_DECISION_MS - 40_000, 0.40),
            _book(_DECISION_MS + 2_001, -0.50),
        )
    }

    report = build_signal_pressure_translation(candidates, books, 30_000)

    assert report["coverage"]["publication_book_stale"] == 1
    row = report["by_provider_symbol"]["provider|xyz:SPCX"]["signals"][0]
    assert row["translation_state"] == "unavailable"
    assert row["publication_directional_opi"] is None


def test_invalid_native_pressure_fails_closed() -> None:
    """Malformed provider pressure cannot become success-shaped telemetry."""
    candidate = _candidate("long", 1.20, _DECISION_MS)

    with pytest.raises(ValueError, match="native pressure"):
        build_signal_pressure_translation((candidate,), {}, 30_000)


def _candidate(side: str, pressure: float, decision_ms: int) -> SignalCandidate:
    return SignalCandidate(
        strategy_id="provider",
        symbol="xyz:SPCX",
        decision_time_ms=decision_ms,
        available_time_ms=decision_ms + 2_000,
        reference_price=140.0,
        side=side,
        eligible=True,
        blockers=(),
        metrics={"imbalance_10": pressure},
    )


def _book(received_ms: int, opi: float) -> CausalBookSnapshot:
    return CausalBookSnapshot(received_ms, opi, 0.5, 1.0, 140.0, 139.99, 140.01)
