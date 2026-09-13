"""Journal economics must include every owned reduction in a native lifecycle."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_order_submission import SolOrderRecoveryError
from hypervector.live.sol_range_onset_live_journal import build_live_journal
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]


def records(root: Path, symbol: str) -> list[dict[str, object]]:
    """Read the actual engine's synthetic append-only native ledger."""
    path = root / "live/bidirectional_cohort" / f"{symbol}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize("symbol", ["BTC", "xyz:SNDK"])
def test_partial_then_final_close_journal_matches_shared_account_economics(
    tmp_path: Path, symbol: str
) -> None:
    """Two real engine close orders form one complete lifecycle with all paid fees."""
    replay = ScheduledEngineFixture(tmp_path, lost=None, partial_operation="close")
    asset = replay.assets[symbol]
    original = replay.enter_current(asset)
    collateral = replay.collateral[symbol]
    replay.partial_close_collateral[symbol] = replace(collateral, cash_usd=collateral.cash_usd / 2)
    replay.prepare_close(symbol)
    assert (
        replay.engines[symbol].exit(mark_price=100, reason="first_partial").state
        is SolLiveState.OPEN
    )
    journal = build_live_journal(records(tmp_path, symbol))
    assert not journal["trades"] and len(journal["open_lifecycles"]) == 1
    assert journal["open_lifecycles"][0]["fees_usd"] == pytest.approx(
        float(replay.account.snapshot().fees_usd)
    )
    replay.partial_operation = None
    replay.prepare_close(symbol)
    assert (
        replay.engines[symbol].exit(mark_price=100, reason="remaining_close").state
        is SolLiveState.FLAT
    )
    journal = build_live_journal(records(tmp_path, symbol))
    assert not journal["open_lifecycles"] and len(journal["trades"]) == 1
    trade = journal["trades"][0]
    view = replay.account.snapshot()
    assert trade["exit"]["size"] == pytest.approx(abs(original.position_size_signed))
    assert trade["fees_usd"] == pytest.approx(float(view.fees_usd))
    assert trade["net_pnl_usd"] == pytest.approx(float(view.cash_usd) - 5000)
    close_fills = [fill for fill in replay.fills if fill["dir"].startswith("Close")]
    assert trade["exit_oids"] == sorted({fill["oid"] for fill in close_fills})
    assert trade["exit"]["venue_timestamp_ms"] == max(fill["time"] for fill in close_fills)


def test_recovered_entry_is_present_once_in_the_native_journal(tmp_path: Path) -> None:
    """An entry acknowledged only during restart must still be accounted for."""
    replay = ScheduledEngineFixture(
        tmp_path,
        lost="entry",
        recovery_delay_ms=5000,
        partial_operation="entry",
        partial_status="canceled",
    )
    asset = replay.assets["BTC"]
    with pytest.raises(SolOrderRecoveryError):
        replay.enter_current(asset)
    replay.clock.advance_to(replay.clock.now_ms + 6000)
    assert replay.engine(asset).start().state is SolLiveState.OPEN
    journal = build_live_journal(records(tmp_path, asset.symbol))
    assert not journal["trades"] and len(journal["open_lifecycles"]) == 1
    trade = journal["open_lifecycles"][0]
    assert trade["status"] == "open"
    view = replay.account.snapshot()
    assert trade["entry"]["size"] == pytest.approx(
        float(abs(view.positions[asset.symbol].quantity_signed))
    )
    assert trade["fees_usd"] == pytest.approx(float(view.fees_usd))
