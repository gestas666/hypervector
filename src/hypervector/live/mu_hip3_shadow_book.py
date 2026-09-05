"""Causal, provenance-preserving book rows for the MU research observer."""

from __future__ import annotations

from hypervector.live.hip3_shadow_book import (
    Hip3ShadowBookSpec,
    hip3_shadow_book_row,
)
from hypervector.live.mu_hip3_breakout_shadow import (
    Hip3BreakoutShadowSpec,
    MU_SHADOW_SPEC,
)
from hypervector.live.mu_hip3_preclose_pressure import MU_PRESSURE_SOURCE
from hypervector.paper.book import BookSnapshot


def mu_shadow_book_row(
    snapshot: BookSnapshot,
    spec: Hip3BreakoutShadowSpec = MU_SHADOW_SPEC,
) -> tuple[dict[str, object], int]:
    """Normalize bounded venue-clock lead while retaining local receipt time."""
    book_spec = Hip3ShadowBookSpec(
        symbol=spec.symbol,
        source=MU_PRESSURE_SOURCE,
        profile_id=spec.ledger_profile_id,
        label="MU",
    )
    return hip3_shadow_book_row(snapshot, book_spec)
