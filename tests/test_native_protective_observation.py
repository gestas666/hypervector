"""Protective execution between polls must leave current, economically consistent telemetry."""

from fractions import Fraction
import json
from pathlib import Path

import pytest
from native_replay_protective_fixture import ProtectiveEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_state import SolLiveState
from hypervector.live.sol_range_onset_live_journal import build_live_journal

__all__ = ["deny_external_ports"]
SYMBOLS = ["BTC", "ETH", "SOL", "HYPE", "xyz:BBB", "xyz:CCC", "xyz:EEE"]


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("last_side", [False, True])
@pytest.mark.parametrize("history_delay_ms", [0, 500])
def test_intrapoll_stop_fill_returns_final_flat_snapshot(
    tmp_path: Path, symbol: str, last_side: bool, history_delay_ms: int
) -> None:
    """Native stop receipts reach flat with no synthetic close or stale sibling order."""
    replay = ProtectiveEngineFixture(tmp_path)
    original = replay.enter_current(replay.assets[symbol], last_side=last_side)
    replay.fill_owned_order(original.stop_oid, history_delay_ms=history_delay_ms)
    engine = replay.engines[symbol]
    venue = engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    assert engine.snapshot.state is SolLiveState.FLAT
    assert venue.is_flat, "returned reconciliation must reflect completed sibling cleanup"
    assert not replay.orders and not replay.account.snapshot().positions
    assert replay.mutations.count("close") == 0
    replay.assert_native_account_agreement()
    assert_exact_cash(replay)
    assert_current_flat_ledger(replay, symbol)


@pytest.mark.parametrize("history_delay_ms", [0, 500])
def test_intrapoll_target_fill_cancels_stop_and_returns_current_flat_snapshot(
    tmp_path: Path, history_delay_ms: int
) -> None:
    """An explicitly prescribed target fill is not inferred from a price touch."""
    replay = ProtectiveEngineFixture(tmp_path)
    original = replay.enter_current(replay.assets["BTC"])
    assert original.target_oid is not None
    replay.fill_owned_order(original.target_oid, history_delay_ms=history_delay_ms)
    venue = replay.engines["BTC"].reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    assert replay.engines["BTC"].snapshot.state is SolLiveState.FLAT
    assert venue.is_flat and not replay.orders
    assert replay.mutations.count("close") == 0
    assert_exact_cash(replay)
    assert_current_flat_ledger(replay, "BTC")


def assert_exact_cash(replay: ProtectiveEngineFixture) -> None:
    """Recompute cash from fill prices/quantities with independent rational arithmetic."""
    entries = [row for row in replay.fills if row["dir"].startswith("Open")]
    exits = [row for row in replay.fills if row["dir"].startswith("Close")]
    quantity = sum(Fraction(row["sz"]) for row in entries)
    quote = sum(Fraction(row["sz"]) * Fraction(row["px"]) for row in entries)
    assert sum(Fraction(row["sz"]) for row in exits) == quantity
    sign = 1 if entries[0]["side"] == "B" else -1
    gross = sign * (sum(Fraction(row["sz"]) * Fraction(row["px"]) for row in exits) - quote)
    fees = sum(Fraction(row["fee"]) for row in replay.fills)
    assert Fraction(replay.account.snapshot().cash_usd) == Fraction(5000) + gross - fees


def assert_current_flat_ledger(replay: ProtectiveEngineFixture, symbol: str) -> None:
    """The last durable account row and closed journal must describe final cleanup."""
    path = replay.root / "live/bidirectional_cohort" / f"{symbol}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    reconciliations = [row["payload"] for row in rows if row["event_type"] == "reconciliation"]
    assert reconciliations[-1]["open_order_ids"] == []
    assert reconciliations[-1]["open_orders"] == []
    report = build_live_journal(rows)
    assert len(report["trades"]) == 1 and not report["open_lifecycles"]
    assert report["trades"][0]["net_pnl_usd"] == pytest.approx(
        float(replay.account.snapshot().cash_usd) - 5000
    )
