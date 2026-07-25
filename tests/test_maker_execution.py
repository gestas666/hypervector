"""Causal maker-order mechanics used by the Hypervelocity paper backend."""

from __future__ import annotations

import pandas as pd

from hypervector.paper.maker_execution import (
    PostOnlyLimitFillModel,
    PendingMakerEntry,
    entry_limit_price,
    entry_was_filled,
    target_was_filled,
)


def _bar(*, high: float = 101.0, low: float = 99.0) -> dict[str, float]:
    return {"open": 100.0, "high": high, "low": low, "close": 100.0}


def test_bar_fallback_requires_one_tick_through_entry_limit() -> None:
    order = PendingMakerEntry(
        direction="long",
        qty=2.0,
        limit_price=100.0,
        submitted_at=pd.Timestamp("2026-07-25T12:00:00Z"),
    )

    assert entry_was_filled(order, _bar(low=99.0), book=None, tick_size=1.0)
    assert not entry_was_filled(order, _bar(low=99.01), book=None, tick_size=1.0)


def test_target_requires_one_tick_through_for_maker_evidence() -> None:
    assert target_was_filled(
        direction="long",
        target_price=100.2,
        record=_bar(high=101.2),
        book=None,
        tick_size=1.0,
    )
    assert not target_was_filled(
        direction="long",
        target_price=100.2,
        record=_bar(high=101.19),
        book=None,
        tick_size=1.0,
    )


def test_missing_book_submits_at_completed_bar_close() -> None:
    assert entry_limit_price("long", _bar(), book=None) == 100.0
    assert entry_limit_price("short", _bar(), book=None) == 100.0


def test_post_only_limit_fill_model_fills_exact_limit_without_slippage() -> None:
    result = PostOnlyLimitFillModel().fill(
        side="buy",
        qty=2.0,
        mark_px=100.0,
        book=None,
        slippage_bps=25.0,
    )

    assert result.fill_px == 100.0
    assert result.fill_qty == 2.0
    assert result.fill_model_id == "post_only_limit_through_v1"
