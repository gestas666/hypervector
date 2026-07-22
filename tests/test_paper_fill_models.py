"""FillModel protocol: bar_close_slippage_v1 + select_fill_model scaffold."""

from hypervector.paper.fill_models import (
    FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
    FILL_MODEL_TOP_BPS_V1,
    BarCloseSlippageFillModel,
    FillResult,
    select_fill_model,
)


def test_bar_close_buy_applies_slippage():
    m = BarCloseSlippageFillModel()
    r = m.fill(side="buy", qty=1.0, mark_px=100.0, book=None, slippage_bps=10.0)
    assert r.fill_model_id == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1
    assert abs(r.fill_px - 100.0 * 1.001) < 1e-9
    assert r.fill_qty == 1.0
    assert r.levels_used == 0
    assert r.shortfall_qty == 0.0


def test_bar_close_sell_applies_slippage():
    m = BarCloseSlippageFillModel()
    r = m.fill(side="sell", qty=2.0, mark_px=100.0, book=None, slippage_bps=10.0)
    assert abs(r.fill_px - 100.0 * 0.999) < 1e-9
    assert r.fill_qty == 2.0
    assert r.requested_qty == 2.0
    assert r.bbo_bid is None
    assert r.bbo_ask is None
    assert r.book_age_ms is None
    assert r.fill_fallback_reason is None


def test_bar_close_fill_result_shape():
    m = BarCloseSlippageFillModel()
    r = m.fill(side="buy", qty=0.5, mark_px=50_000.0, book=None, slippage_bps=0.0)
    assert isinstance(r, FillResult)
    assert r.fill_model_id == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1
    assert r.fill_px == 50_000.0
    assert r.fill_qty == 0.5
    assert r.requested_qty == 0.5
    assert r.levels_used == 0
    assert r.shortfall_qty == 0.0


def test_select_fill_model_prefers_bar_close():
    model, reason = select_fill_model(
        preferred=FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
        book=None,
        max_book_age_ms=3000.0,
    )
    assert isinstance(model, BarCloseSlippageFillModel)
    assert reason is None


def test_select_fill_model_book_missing_fallback():
    model, reason = select_fill_model(
        preferred=FILL_MODEL_TOP_BPS_V1,
        book=None,
        max_book_age_ms=3000.0,
    )
    assert isinstance(model, BarCloseSlippageFillModel)
    assert reason == "book_missing"


def test_top_bps_buy_uses_ask():
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import TopBpsFillModel

    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 2.0),),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = TopBpsFillModel().fill(side="buy", qty=1.0, mark_px=100.0, book=book, slippage_bps=0.0)
    assert r.fill_model_id == FILL_MODEL_TOP_BPS_V1
    assert abs(r.fill_px - 100.1) < 1e-9
    assert r.bbo_ask == 100.1 and r.bbo_bid == 100.0
    assert r.levels_used == 1
    assert r.fill_qty == 1.0
    assert r.shortfall_qty == 0.0


def test_top_bps_sell_uses_bid():
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import TopBpsFillModel

    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 2.0),),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = TopBpsFillModel().fill(side="sell", qty=0.5, mark_px=100.0, book=book, slippage_bps=10.0)
    # sell = best_bid * (1 - slip) = 100.0 * 0.999
    assert abs(r.fill_px - 100.0 * 0.999) < 1e-9
    assert r.bbo_bid == 100.0 and r.bbo_ask == 100.1
    assert r.levels_used == 1


def test_top_bps_empty_book_raises():
    from hypervector.paper.book import BookSnapshot
    from hypervector.paper.fill_models import TopBpsFillModel

    book = BookSnapshot(
        symbol="X",
        bids=(),
        asks=(),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    try:
        TopBpsFillModel().fill(side="buy", qty=1.0, mark_px=100.0, book=book, slippage_bps=0.0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_select_falls_back_when_stale():
    from hypervector.paper.book import BookLevel, BookSnapshot

    book = BookSnapshot(
        symbol="X",
        bids=(BookLevel(1.0, 1.0),),
        asks=(BookLevel(1.1, 1.0),),
        ts_recv_ms=0.0,
        ts_exchange_ms=0.0,
        source="t",
    )
    model, reason = select_fill_model(
        preferred=FILL_MODEL_TOP_BPS_V1,
        book=book,
        max_book_age_ms=3000,
        now_ms=10_000,
    )
    assert model.fill_model_id == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1
    assert reason == "book_stale"


def test_select_top_bps_when_fresh():
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import TopBpsFillModel

    book = BookSnapshot(
        symbol="X",
        bids=(BookLevel(1.0, 1.0),),
        asks=(BookLevel(1.1, 1.0),),
        ts_recv_ms=9_500.0,
        ts_exchange_ms=9_500.0,
        source="t",
    )
    model, reason = select_fill_model(
        preferred=FILL_MODEL_TOP_BPS_V1,
        book=book,
        max_book_age_ms=3000,
        now_ms=10_000,
    )
    assert isinstance(model, TopBpsFillModel)
    assert reason is None


def test_select_l2_walk_when_fresh():
    """preferred l2_walk_v1 with fresh book → L2WalkFillModel."""
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1, L2WalkFillModel

    book = BookSnapshot(
        symbol="X",
        bids=(BookLevel(1.0, 1.0),),
        asks=(BookLevel(1.1, 1.0),),
        ts_recv_ms=9_500.0,
        ts_exchange_ms=9_500.0,
        source="t",
    )
    model, reason = select_fill_model(
        preferred=FILL_MODEL_L2_WALK_V1,
        book=book,
        max_book_age_ms=3000,
        now_ms=10_000,
    )
    assert isinstance(model, L2WalkFillModel)
    assert reason is None


def test_select_empty_book_is_missing():
    from hypervector.paper.book import BookSnapshot

    book = BookSnapshot(
        symbol="X",
        bids=(),
        asks=(),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    model, reason = select_fill_model(
        preferred=FILL_MODEL_TOP_BPS_V1,
        book=book,
        max_book_age_ms=3000,
        now_ms=1.0,
    )
    assert model.fill_model_id == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1
    assert reason == "book_missing"


def test_l2_walk_buy_vwap_two_levels():
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1, L2WalkFillModel

    # ask 100.1 x 2.0, 100.2 x 1.0; buy qty 3 → full
    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 5.0),),
        asks=(BookLevel(100.1, 2.0), BookLevel(100.2, 1.0)),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = L2WalkFillModel().fill(side="buy", qty=3.0, mark_px=100.0, book=book, slippage_bps=0.0)
    assert r.fill_model_id == FILL_MODEL_L2_WALK_V1
    # VWAP = (2*100.1 + 1*100.2) / 3 = 100.1333...
    assert abs(r.fill_px - (2 * 100.1 + 1 * 100.2) / 3.0) < 1e-9
    assert r.fill_qty == 3.0
    assert r.shortfall_qty == 0.0
    assert r.levels_used == 2


def test_l2_walk_shortfall_no_invented_depth():
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import L2WalkFillModel

    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 1.0),),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = L2WalkFillModel().fill(side="buy", qty=5.0, mark_px=100.0, book=book, slippage_bps=0.0)
    assert r.fill_qty == 1.0
    assert r.shortfall_qty == 4.0
    assert r.levels_used == 1
