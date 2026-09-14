"""Partial stop exits retain exact ownership through follow-up fills and late receipts."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from native_replay_partial_protective_fixture import PartialProtectiveFixture
from test_native_partial_protective_execution import CASES
from test_native_partial_protective_recovery import assert_closed_economics, restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_order_submission import SolOrderRecoveryError
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]
STOP_CASES = [case for case in CASES if case[1] == "stop"]
RECEIPT_DELAY_MS = 10_000


@pytest.mark.parametrize("symbol,kind,last_side", STOP_CASES)
def test_partial_followup_close_retains_stop_exit_obligation_until_restart_completes_it(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """A terminal partial IOC must retain remaining exposure and original exit intent."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    engine = replay.engines[symbol]
    replay.partial_operation = "close"
    collateral = replay.collateral[symbol]
    replay.partial_close_collateral[symbol] = replace(collateral, cash_usd=collateral.cash_usd / 2)
    venue = engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    assert engine.snapshot.state is SolLiveState.EXIT_PENDING
    assert engine.snapshot.protective_progress.stop_exit_required
    assert engine.snapshot.position_size_signed == venue.position.size_signed
    assert engine.snapshot.opened_at_ms == original.opened_at_ms
    assert replay.mutations.count("close") == 1
    replay.partial_operation = None
    restart(replay, symbol)
    assert replay.mutations.count("close") == 2
    assert_closed_economics(replay, symbol)


class CrashAfterCloseAck(BaseException):
    """Interrupt after the durable follow-up close receipt and before local confirmation."""


@pytest.mark.parametrize("symbol,kind,last_side", STOP_CASES)
def test_followup_close_ack_restart_does_not_submit_another_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
    kind: str,
    last_side: bool,
) -> None:
    """Recover the already-executed close's identity from its exact durable intent."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    engine = replay.engines[symbol]
    emit_ack = engine._events.emit_ack

    def crash_after_ack(
        operation: str,
        ack: HyperliquidOrderAck,
        *,
        event_type: str = "order_acknowledgement",
    ) -> None:
        emit_ack(operation, ack, event_type=event_type)
        if operation == "reduce_only_close":
            raise CrashAfterCloseAck()

    monkeypatch.setattr(engine._events, "emit_ack", crash_after_ack)
    with pytest.raises(CrashAfterCloseAck):
        engine.reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    assert replay.mutations.count("close") == 1
    restart(replay, symbol)
    assert replay.mutations.count("close") == 1
    assert_closed_economics(replay, symbol)


@pytest.mark.parametrize("symbol,kind,last_side", STOP_CASES)
def test_lost_followup_close_response_recovers_exactly_once(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """Delayed status after a lost response cannot authorize a duplicate reduce-only order."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    replay.lost, replay.recovery_delay_ms = "close", RECEIPT_DELAY_MS
    with pytest.raises((SolOrderRecoveryError, SolLiveEngineError)):
        replay.engines[symbol].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    assert replay.mutations.count("close") == 1
    replay.clock.advance_to(replay.clock.now_ms + RECEIPT_DELAY_MS)
    restart(replay, symbol)
    assert replay.mutations.count("close") == 1
    assert_closed_economics(replay, symbol)


def _delay_selected_fills(
    replay: PartialProtectiveFixture,
    *,
    delayed_oids: set[int] | None,
    prior_oids: set[int],
    release_ms: int,
) -> None:
    def selected(address: str) -> list[dict[str, object]]:
        rows = replay._visible_fills(address)
        if replay.clock.now_ms >= release_ms:
            return rows
        if delayed_oids is not None:
            return [row for row in rows if row["oid"] not in delayed_oids]
        return [row for row in rows if row["oid"] in prior_oids]

    replay._info.user_fills.side_effect = selected


@pytest.mark.parametrize("symbol,kind,last_side", CASES)
def test_late_partial_protective_fill_history_restores_original_owner(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """A read-only observation failure must retain the original context for exact later proof."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    oid = original.target_oid if kind == "target" else original.stop_oid
    release = replay.clock.now_ms + RECEIPT_DELAY_MS
    _delay_selected_fills(replay, delayed_oids={oid}, prior_oids=set(), release_ms=release)
    with pytest.raises(SolLiveEngineError):
        replay.engines[symbol].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    assert replay.mutations.count("close") == 0
    for _ in range(2):
        with pytest.raises(SolLiveEngineError):
            restart(replay, symbol)
    replay.clock.advance_to(release)
    engine = restart(replay, symbol)
    if kind == "target":
        assert engine.snapshot.state is SolLiveState.OPEN
        assert engine.snapshot.opened_at_ms == original.opened_at_ms
        assert replay.mutations.count("close") == 0
    else:
        assert replay.mutations.count("close") == 1
        assert_closed_economics(replay, symbol)


@pytest.mark.parametrize("symbol,kind,last_side", STOP_CASES)
def test_late_followup_close_fills_recover_without_duplicate_exit(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """An acknowledgement and flat exposure cannot replace the missing owned fill receipts."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, Decimal("0.5"))
    release = replay.clock.now_ms + RECEIPT_DELAY_MS
    prior = {original.entry_oid, original.stop_oid, original.target_oid} - {None}
    _delay_selected_fills(replay, delayed_oids=None, prior_oids=prior, release_ms=release)
    with pytest.raises(SolLiveEngineError):
        replay.engines[symbol].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    assert replay.mutations.count("close") == 1
    for _ in range(2):
        with pytest.raises(SolLiveEngineError):
            restart(replay, symbol)
    replay.clock.advance_to(release)
    restart(replay, symbol)
    assert replay.mutations.count("close") == 1
    assert_closed_economics(replay, symbol)


def test_partial_target_then_partial_commanded_close_keeps_receipts_across_target_replacement(
    tmp_path: Path,
) -> None:
    """A replacement target must not discard fills from the previous target or partial IOC."""
    replay, original = _partial_fixture(tmp_path, "BTC", "target", False, Decimal("0.5"))
    engine = replay.engines["BTC"]
    engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    replay.partial_operation = "close"
    replay.partial_close_collateral["BTC"] = replay.collateral["BTC"]
    replay.prepare_close("BTC")
    engine.exit(mark_price=100, reason="fixture_fixed_hold")
    assert engine.snapshot.state is SolLiveState.OPEN
    assert engine.snapshot.target_oid != original.target_oid
    engine = restart(replay, "BTC")
    assert engine.snapshot.opened_at_ms == original.opened_at_ms
    replay.fill_owned_order(engine.snapshot.target_oid, history_delay_ms=0)
    engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    assert_closed_economics(replay, "BTC")


@pytest.mark.parametrize("kind", ["stop", "target"])
def test_delayed_final_protection_after_partial_target_survives_repeated_restart(
    tmp_path: Path, kind: str
) -> None:
    """Credited partial receipts cannot make a delayed full exit appear oversized forever."""
    replay, original = _partial_fixture(tmp_path, "BTC", "target", False, Decimal("0.5"))
    engine = replay.engines["BTC"]
    engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    oid = original.stop_oid if kind == "stop" else original.target_oid
    replay.fill_owned_order(oid, history_delay_ms=RECEIPT_DELAY_MS)
    release = replay.clock.now_ms + RECEIPT_DELAY_MS
    before = list(replay.mutations)
    with pytest.raises(SolLiveEngineError):
        engine.reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    for _ in range(2):
        with pytest.raises(SolLiveEngineError):
            restart(replay, "BTC")
    replay.clock.advance_to(release)
    restart(replay, "BTC")
    assert replay.mutations.count("close") == before.count("close")
    assert_closed_economics(replay, "BTC")
