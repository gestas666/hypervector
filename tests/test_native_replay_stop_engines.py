"""Actual configured engines recover stop executions from reusable SDK replay receipts."""

from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk_engines import _enter_configured, cohort_sdk, engine

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.asset_live_journal import build_live_journal
from hypervector.live.asset_state import AssetLiveState
from hypervector.research.native_replay_depth import ExactLevel, RecordedBook

__all__ = ["deny_external_ports"]
D = Decimal
SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:BBB", "xyz:CCC", "xyz:EEE")


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("last_side", [False, True])
@pytest.mark.parametrize("restart", [False, True])
def test_native_stop_reconciles_engine_cleanup_journal_and_exact_cash(
    tmp_path: Path, symbol: str, last_side: bool, restart: bool
) -> None:
    """Both telemetry and restart paths must recover actual stop OIDs without a second close."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/noncrypto_live.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    decisions: dict[str, int] = {}
    replay = cohort_sdk(config, decisions)
    asset = next(row for row in config.assets if row.symbol == symbol)
    machine = _enter_configured(replay, config, asset, tmp_path, last_side, decisions)
    original = machine.snapshot
    replay.advance_to(replay.clock.now_ms + 1000)
    row = replay.orders[original.stop_oid]
    trigger = row.trigger_price
    replay.observe_prices(symbol, source_time_ms=replay.clock.now_ms, mark=trigger, mid=trigger)
    replay.protective.activate_stop(
        row.oid,
        mark_time_ms=replay.clock.now_ms,
        execution_limit=trigger * (D("1.1") if row.is_buy else D(".9")),
    )
    book = RecordedBook(
        f"synthetic:engine-stop:{symbol}:{replay.clock.now_ms}",
        symbol,
        replay.clock.now_ms,
        D(1).scaleb(-replay.markets[symbol].metadata.size_decimals),
        (ExactLevel(trigger - D(".01"), row.quantity),),
        (ExactLevel(trigger + D(".01"), row.quantity),),
    )
    replay.protective.match_stop(row.oid, book)
    if restart:
        machine = engine(replay, asset, tmp_path)
        machine.start()
    venue = machine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    assert machine.snapshot.state is AssetLiveState.FLAT and venue.is_flat
    assert not replay.account.snapshot().positions and len(replay.fill_rows) == 2
    assert {fill["oid"] for _, fill in replay.fill_rows} == {original.entry_oid, original.stop_oid}
    _assert_cash_and_journal(replay.fill_rows, replay.account.snapshot().cash_usd, tmp_path, symbol)


def _assert_cash_and_journal(
    fills: list[tuple[int, dict[str, object]]], cash: Decimal, root: Path, symbol: str
) -> None:
    opening, closing = [row for _, row in fills]
    quantity = Fraction(opening["sz"])
    assert quantity == Fraction(closing["sz"])
    gross = (
        quantity
        * (Fraction(closing["px"]) - Fraction(opening["px"]))
        * (1 if opening["side"] == "B" else -1)
    )
    fees = sum((Fraction(row["fee"]) for _, row in fills), Fraction(0))
    assert Fraction(cash) == 5000 + gross - fees
    path = root / "live/bidirectional_cohort" / f"{symbol}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    journal = build_live_journal(rows)
    assert len(journal["trades"]) == 1 and not journal["open_lifecycles"]
    assert journal["trades"][0]["net_pnl_usd"] == pytest.approx(float(cash) - 5000)
