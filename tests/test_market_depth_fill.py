"""Market-order fill tests against finite visible order-book depth."""

from __future__ import annotations

import pytest

from hypervector.research.market_depth_fill import DepthLevel, walk_market_order


def test_buy_walks_asks_and_reports_vwap_impact() -> None:
    """A market buy must consume asks from lowest to highest price."""
    levels = (DepthLevel(100.0, 1.0), DepthLevel(101.0, 2.0))

    fill = walk_market_order(levels, side="buy", quantity=2.0)

    assert fill.complete is True
    assert fill.filled_quantity == pytest.approx(2.0)
    assert fill.unfilled_quantity == pytest.approx(0.0)
    assert fill.vwap == pytest.approx(100.5)
    assert fill.best_price == pytest.approx(100.0)
    assert fill.worst_price == pytest.approx(101.0)
    assert fill.impact_bps == pytest.approx(50.0)


def test_sell_walks_bids_and_reports_finite_shortfall() -> None:
    """A market sell must consume bids from highest to lowest price."""
    levels = (DepthLevel(100.0, 1.0), DepthLevel(99.0, 0.5))

    fill = walk_market_order(levels, side="sell", quantity=2.0)

    assert fill.complete is False
    assert fill.filled_quantity == pytest.approx(1.5)
    assert fill.unfilled_quantity == pytest.approx(0.5)
    assert fill.vwap == pytest.approx((100.0 + 49.5) / 1.5)
    assert fill.worst_price == pytest.approx(99.0)


def test_depth_levels_reject_invalid_values() -> None:
    """Non-positive or non-finite book values must fail closed."""
    with pytest.raises(ValueError, match="price"):
        DepthLevel(0.0, 1.0)
    with pytest.raises(ValueError, match="size"):
        DepthLevel(100.0, float("nan"))


@pytest.mark.parametrize("side", ["hold", "", 3])
def test_market_walk_rejects_invalid_side(side: object) -> None:
    """Only explicit buy and sell market sides are accepted."""
    with pytest.raises(ValueError, match="side"):
        walk_market_order((DepthLevel(100.0, 1.0),), side=side, quantity=1.0)


def test_market_walk_rejects_unsorted_or_duplicate_levels() -> None:
    """Malformed level ordering must not produce success-shaped fills."""
    asks = (DepthLevel(101.0, 1.0), DepthLevel(100.0, 1.0))
    bids = (DepthLevel(99.0, 1.0), DepthLevel(100.0, 1.0))
    duplicate = (DepthLevel(100.0, 1.0), DepthLevel(100.0, 2.0))

    with pytest.raises(ValueError, match="ascending"):
        walk_market_order(asks, side="buy", quantity=1.0)
    with pytest.raises(ValueError, match="descending"):
        walk_market_order(bids, side="sell", quantity=1.0)
    with pytest.raises(ValueError, match="ascending"):
        walk_market_order(duplicate, side="buy", quantity=1.0)


def test_market_walk_requires_visible_depth_and_positive_quantity() -> None:
    """Empty depth and invalid order quantities fail closed."""
    with pytest.raises(ValueError, match="levels"):
        walk_market_order((), side="buy", quantity=1.0)
    with pytest.raises(ValueError, match="quantity"):
        walk_market_order((DepthLevel(100.0, 1.0),), side="buy", quantity=0.0)
