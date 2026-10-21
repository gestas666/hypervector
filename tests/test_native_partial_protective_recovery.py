"""Partial protection must survive native restart and cumulative final closure."""

from decimal import Decimal
import json
from pathlib import Path

import pytest
from native_replay_partial_protective_fixture import PartialProtectiveFixture
from test_native_partial_protective_execution import CASES, assert_partial_economics
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_live_journal import build_live_journal
from hypervector.live.asset_state import AssetLiveState
from hypervector.live.multi_asset_cohort_history import fill_payloads

__all__ = ["deny_external_ports"]


def assert_closed_economics(replay: PartialProtectiveFixture, symbol: str) -> None:
    """Compare native journal receipts with independent complete account economics."""
    engine = replay.engines[symbol]
    records = [json.loads(line) for line in engine._ledger.path.read_text().splitlines()]
    journal = build_live_journal(records)
    assert engine.snapshot.state is AssetLiveState.FLAT
    assert not journal["open_lifecycles"] and len(journal["trades"]) == 1
    assert journal["trades"][0]["net_pnl_usd"] == pytest.approx(
        float(replay.account.snapshot().cash_usd) - 5000
    )
    assert_partial_economics(replay)


def restart(replay: PartialProtectiveFixture, symbol: str) -> AssetLiveEngine:
    """Replace only the local consumer, retaining its original ledger and venue ports."""
    engine = replay.engine(replay.assets[symbol])
    replay.engines[symbol] = engine
    engine.start()
    return engine


@pytest.mark.parametrize("symbol,kind,last_side", CASES)
def test_restart_observes_previously_unacknowledged_partial_protection(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """A partial fill during downtime cannot invalidate the last exact OPEN owner."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    engine = restart(replay, symbol)
    if kind == "target":
        assert engine.snapshot.state is AssetLiveState.OPEN
        assert engine.snapshot.position_size_signed == float(
            replay.account.snapshot().positions[symbol].quantity_signed
        )
        assert engine.snapshot.opened_at_ms == original.opened_at_ms
        assert replay.mutations.count("close") == 0
    else:
        assert replay.mutations.count("close") == 1
        assert_closed_economics(replay, symbol)


@pytest.mark.parametrize("final_exit", ["target", "stop", "commanded"])
def test_repeated_target_partials_restart_and_final_close_retain_every_fill(
    tmp_path: Path, final_exit: str
) -> None:
    """Repeated target receipts cannot be recredited, omitted or compared with only the remainder."""
    replay, original = _partial_fixture(tmp_path, "BTC", "target", False, Decimal("0.5"))
    engine = replay.engines["BTC"]
    for iteration in range(2):
        engine.reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
        assert engine.snapshot.opened_at_ms == original.opened_at_ms
        engine = restart(replay, "BTC")
        if iteration == 0:
            replay.fill_partial_protection(
                original.target_oid,
                remaining_collateral=replay.collateral["BTC"],
                history_delay_ms=0,
                remainder_open=True,
                fee_rate=Decimal("0.00015"),
            )
    if final_exit == "commanded":
        engine.record_strategy_decision({"strategy_id": "cohort_maximum_hold"})
        replay.prepare_close("BTC")
        engine.exit(mark_price=100, reason="fixture_fixed_hold")
    else:
        oid = original.target_oid if final_exit == "target" else original.stop_oid
        replay.fill_owned_order(oid, history_delay_ms=0)
        engine.reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    assert_closed_economics(replay, "BTC")
    fills = fill_payloads("BTC", engine._ledger.read_all())
    assert {fill["strategy_id"] for fill in fills} == {fills[0]["strategy_id"]}
    count = replay.mutations.count("close")
    assert restart(replay, "BTC").snapshot.state is AssetLiveState.FLAT
    assert replay.mutations.count("close") == count


class CrashAfterStopCheckpoint(BaseException):
    """Stop the local process after its durable obligation and before order dispatch."""


@pytest.mark.parametrize("kind", ["stop", "target"])
def test_scheduled_exit_observes_completed_protection_after_a_partial_target(
    tmp_path: Path, kind: str
) -> None:
    """An exit request must reconcile intervening owned completion before any close submission."""
    replay, original = _partial_fixture(tmp_path, "BTC", "target", False, Decimal("0.5"))
    engine = replay.engines["BTC"]
    engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    replay.fill_owned_order(
        original.stop_oid if kind == "stop" else original.target_oid, history_delay_ms=0
    )
    assert engine.exit(mark_price=100, reason="fixture_fixed_hold").state is AssetLiveState.FLAT
    assert replay.mutations.count("close") == 0
    assert_closed_economics(replay, "BTC")


@pytest.mark.parametrize("symbol,kind,last_side", [case for case in CASES if case[1] == "stop"])
def test_partial_stop_checkpoint_restart_completes_one_exact_remaining_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
    kind: str,
    last_side: bool,
) -> None:
    """A crash after recording a consumed stop cannot restore it as ordinary strategy exposure."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    engine = replay.engines[symbol]
    emit_state = engine._events.emit_state

    def crash_after_checkpoint() -> None:
        emit_state()
        progress = getattr(engine.snapshot, "protective_progress", None)
        if progress is not None and progress.stop_exit_required:
            raise CrashAfterStopCheckpoint()

    monkeypatch.setattr(engine._events, "emit_state", crash_after_checkpoint)
    with pytest.raises(CrashAfterStopCheckpoint):
        engine.reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    assert replay.mutations.count("close") == 0
    restart(replay, symbol)
    assert replay.mutations.count("close") == 1
    assert_closed_economics(replay, symbol)
