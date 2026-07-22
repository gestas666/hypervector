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
