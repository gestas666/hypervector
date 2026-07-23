"""ExplicitFillEngine: bar_close_slippage_v1 fills + funding decision rows."""

from pathlib import Path

from hypervector.paper.costs import CostProvider
from hypervector.paper.fills import ExplicitFillEngine


def test_buy_fill_pays_slippage_and_fee(tmp_path: Path):
    cp = CostProvider(fee_tier=0, slippage_bps=10.0)  # 10 bps
    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=cp,
        run_id="r1",
        export_id="e1",
        strategy_name="crown_stack_short",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
    )
    rec = eng.apply_market_fill(
        feed_ts="2026-07-22T00:00:00Z",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=100_000.0,
    )
    assert rec["execution_mode"] == "paper"
    assert rec["fill_model_id"] == "bar_close_slippage_v1"
    assert rec["fill_px"] == 100_000.0 * (1 + 10 / 10_000)
    assert rec["fee_usd"] > 0
    assert eng.position.qty == 0.01


def test_funding_on_open_long_drag(tmp_path: Path):
    cp = CostProvider(fee_tier=0, funding_rate_hourly=0.0001)
    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=cp,
        run_id="r1",
        export_id="e1",
        strategy_name="s",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
    )
    eng.apply_market_fill(
        feed_ts="t0", action="enter_long", side="buy", qty=1.0, mark_px=50_000.0
    )
    fre = eng.apply_funding(feed_ts="t1", oracle_px=50_000.0)
    assert fre is not None
    assert fre["action"] == "funding"
    assert fre["funding_payment_usd"] == 5.0  # 1 * 50000 * 0.0001


def test_sandbox_flag_on_record_does_not_change_fill(tmp_path: Path):
    """sandbox_enabled is shadow-only: fill_px stays explicit-model truth."""
    mark = 100_000.0
    slip_bps = 10.0
    expected_px = mark * (1.0 + slip_bps / 10_000.0)

    def _engine(*, sandbox: bool) -> ExplicitFillEngine:
        return ExplicitFillEngine(
            tmp_path / ("data_on" if sandbox else "data_off"),
            cost_provider=CostProvider(fee_tier=0, slippage_bps=slip_bps),
            run_id="r1",
            export_id="e1",
            strategy_name="crown_stack_short",
            symbol="BTC",
            timeframe="1m",
            conviction=0.5,
            sandbox_enabled=sandbox,
        )

    rec_off = _engine(sandbox=False).apply_market_fill(
        feed_ts="2026-07-22T00:00:00Z",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=mark,
    )
    rec_on = _engine(sandbox=True).apply_market_fill(
        feed_ts="2026-07-22T00:00:00Z",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=mark,
    )

    assert rec_off["sandbox_enabled"] is False
    assert rec_on["sandbox_enabled"] is True
    assert rec_on["fill_px"] == expected_px
    assert rec_on["fill_px"] == rec_off["fill_px"]
    assert rec_on["fee_usd"] == rec_off["fee_usd"]
    # Real Nautilus sandbox client deferred; shadow key present and null.
    assert rec_on["sandbox_fill_px"] is None
    assert rec_off["sandbox_fill_px"] is None


def test_l2_walk_zero_fill_skips_ledger(tmp_path: Path):
    """fill_qty==0 (empty walked side) → skip position + ledger; no invented depth."""
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1, L2WalkFillModel

    # Bids only — buy walk has no asks.
    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 5.0),),
        asks=(),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=CostProvider(fee_tier=0, slippage_bps=0.0),
        run_id="r1",
        export_id="e1",
        strategy_name="s",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        preferred_fill_model=FILL_MODEL_L2_WALK_V1,
    )
    rec = eng.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        book=book,
        fill_model=L2WalkFillModel(),
    )
    assert rec.get("skipped") is True
    assert rec["fill_qty"] == 0.0
    assert eng.position.qty == 0.0
    # Ledger must record the skip for audit (model id + shortfall, no invent).
    decisions = tmp_path / "data" / "paper" / "decisions"
    assert decisions.is_dir()
    text = (decisions / "decisions.jsonl").read_text(encoding="utf-8")
    assert "enter_long" in text
    assert "skipped" in text
    assert "l2_walk_v1" in text


def test_shadow_market_fill_has_intent_and_submitted_false(tmp_path: Path):
    from hypervector.paper.costs import CostProvider
    from hypervector.paper.fills import ExplicitFillEngine

    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=CostProvider(fee_tier=0, slippage_bps=0.0),
        run_id="r1",
        export_id="e1",
        strategy_name="s",
        symbol="BTC-PERP",
        timeframe="1m",
        conviction=0.5,
        execution_mode="shadow",
    )
    rec = eng.apply_market_fill(
        feed_ts="t0", action="enter_long", side="buy", qty=0.01, mark_px=100.0
    )
    assert rec["execution_mode"] == "shadow"
    assert rec["submitted"] is False
    assert rec["network"] == "mainnet"
    oi = rec["order_intent"]
    assert oi["schema"] == "hv_order_intent_v1"
    assert oi["submit_enabled"] is False
    assert oi["side"] == "buy"
    assert oi["qty"] == 0.01
    # persisted
    text = (tmp_path / "data" / "paper" / "decisions" / "decisions.jsonl").read_text()
    assert "shadow" in text
    assert "order_intent" in text
