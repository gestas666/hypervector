"""Owned partial stops and resting targets cannot strand the current native lifecycle."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

import pytest
from native_replay_engine_fixture import FEE_RATE
from native_replay_partial_protective_fixture import PartialProtectiveFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_state import SolLiveState
from hypervector.live.sol_range_onset_live_journal import build_live_journal

__all__ = ["deny_external_ports"]
D = Decimal
CASES = [
    (symbol, "stop", last_side)
    for symbol in ("BTC", "ETH", "SOL", "HYPE", "xyz:BBB", "xyz:CCC", "xyz:EEE")
    for last_side in ((False, True) if symbol.startswith("xyz:") else (False,))
]
CASES.append(("BTC", "target", False))
MAKER_FEE_RATE = D("0.00015")
ACCOUNT_DECIMAL_TOLERANCE = Fraction(1, 10**40)


def assert_partial_economics(replay: PartialProtectiveFixture) -> None:
    """Independently recompute remaining inventory and cash with rational arithmetic."""
    entries = [f for f in replay.fills if f["dir"].startswith("Open")]
    exits = [f for f in replay.fills if f["dir"].startswith("Close")]
    quantity = sum(Fraction(f["sz"]) for f in entries)
    entry_price = sum(Fraction(f["sz"]) * Fraction(f["px"]) for f in entries) / quantity
    sign = 1 if entries[0]["side"] == "B" else -1
    gross = sign * sum(Fraction(f["sz"]) * (Fraction(f["px"]) - entry_price) for f in exits)
    fees = sum(Fraction(f["fee"]) for f in replay.fills)
    expected = Fraction(5000) + gross - fees
    assert abs(Fraction(replay.account.snapshot().cash_usd) - expected) < ACCOUNT_DECIMAL_TOLERANCE
    remaining = quantity - sum(Fraction(f["sz"]) for f in exits)
    actual = sum(
        abs(Fraction(p.quantity_signed)) for p in replay.account.snapshot().positions.values()
    )
    assert actual == remaining
    replay.assert_native_account_agreement()


@pytest.mark.parametrize("symbol,kind,last_side", CASES)
@pytest.mark.parametrize("collateral_fraction", [D("0.5"), D(1)])
def test_native_partial_protection_preserves_or_completes_owned_lifecycle(
    tmp_path: Path, symbol: str, kind: str, last_side: bool, collateral_fraction: Decimal
) -> None:
    """Prescribed partial fills must not reset ownership or abandon the remaining stop exit."""
    replay = PartialProtectiveFixture(tmp_path)
    original = replay.enter_current(replay.assets[symbol], last_side=last_side)
    oid = original.target_oid if kind == "target" else original.stop_oid
    assert oid is not None
    prior = replay.collateral[symbol]
    replay.fill_partial_protection(
        oid,
        remaining_collateral=replace(prior, cash_usd=prior.cash_usd * collateral_fraction),
        history_delay_ms=0,
        remainder_open=kind == "target",
        fee_rate=MAKER_FEE_RATE if kind == "target" else FEE_RATE,
    )
    assert_partial_economics(replay)
    engine = replay.engines[symbol]
    venue = engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
    )
    if kind == "target":
        assert engine.snapshot.state is SolLiveState.OPEN
        assert engine.snapshot.position_size_signed == venue.position.size_signed
        assert engine.snapshot.opened_at_ms == original.opened_at_ms
        assert engine.snapshot.stop_oid == original.stop_oid and engine.snapshot.target_oid == oid
        assert replay.mutations.count("close") == 0
        restarted = replay.engine(replay.assets[symbol]).start()
        assert restarted.state is SolLiveState.OPEN
        assert restarted.opened_at_ms == original.opened_at_ms
    else:
        assert engine.snapshot.state is SolLiveState.FLAT and venue.is_flat
        assert replay.mutations.count("close") == 1
        rows = [json.loads(line) for line in engine._ledger.path.read_text().splitlines()]
        report = build_live_journal(rows)
        assert len(report["trades"]) == 1 and not report["open_lifecycles"]
        assert report["trades"][0]["net_pnl_usd"] == pytest.approx(
            float(replay.account.snapshot().cash_usd) - 5000
        )
    assert_partial_economics(replay)
