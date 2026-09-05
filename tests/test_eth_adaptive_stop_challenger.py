"""Tests for the preregistered causal ETH adaptive-stop construction."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.eth_adaptive_stop_challenger import (
    ANCHOR_COLUMN,
    ATR_COLUMN,
    STRUCTURE_COLUMN,
    build_eth_adaptive_stop_market,
)


def _market(*, entry_position: int, side: str, rows: int = 20) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    close = pd.Series([100.0 + position for position in range(rows)], index=index)
    market = pd.DataFrame(
        {
            "open": close,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "entry_side": None,
        },
        index=index,
    )
    market.iloc[entry_position, market.columns.get_loc("entry_side")] = side
    return market


@pytest.mark.parametrize("side", ["long", "short"])
def test_adaptive_stop_uses_more_adverse_atr_or_structure_anchor(side: str) -> None:
    """The frozen candidate must use the declared side-specific adverse anchor."""
    market = _market(entry_position=15, side=side)

    result = build_eth_adaptive_stop_market(market)

    atr = float(result[ATR_COLUMN].iloc[15])
    close = float(result["close"].iloc[15])
    structure = float(result[STRUCTURE_COLUMN].iloc[15])
    atr_anchor = close - 1.5 * atr if side == "long" else close + 1.5 * atr
    expected = (
        min(atr_anchor, structure) if side == "long" else max(atr_anchor, structure)
    )
    assert result[ANCHOR_COLUMN].iloc[15] == pytest.approx(expected)


def test_adaptive_stop_anchor_has_no_next_bar_dependency() -> None:
    """Changing data after a signal cannot change that signal's stop anchor."""
    market = _market(entry_position=15, side="long")
    changed = market.copy()
    changed.iloc[16, changed.columns.get_loc("high")] = 1_000.0
    changed.iloc[16, changed.columns.get_loc("low")] = 1.0

    original = build_eth_adaptive_stop_market(market)
    future_changed = build_eth_adaptive_stop_market(changed)

    assert future_changed[ANCHOR_COLUMN].iloc[15] == pytest.approx(
        original[ANCHOR_COLUMN].iloc[15]
    )


def test_adaptive_stop_rejects_entry_before_indicator_warmup() -> None:
    """An entry without a complete ATR/structure window cannot silently fall back."""
    market = _market(entry_position=5, side="short")

    with pytest.raises(ValueError, match="warmup"):
        build_eth_adaptive_stop_market(market)


def test_adaptive_stop_rejects_noncausal_market_order() -> None:
    """The candidate requires unique, ordered, timezone-aware completed bars."""
    market = _market(entry_position=15, side="long").sort_index(ascending=False)

    with pytest.raises(ValueError, match="ordered"):
        build_eth_adaptive_stop_market(market)
