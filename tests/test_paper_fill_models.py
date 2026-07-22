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
