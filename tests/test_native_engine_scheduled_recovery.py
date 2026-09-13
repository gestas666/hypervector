"""Seven actual engines consume scheduled IOC and protection/status SDK responses."""

from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_order_submission import (
    SolCancelRecoveryError,
    SolOrderRecoveryError,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("last_side", [False, True])
@pytest.mark.parametrize("lost", [None, "entry", "stop", "target", "close", "cancel"])
def test_seven_engines_recover_delayed_native_status_and_protection(
    tmp_path: Path,
    lost: str | None,
    last_side: bool,
) -> None:
    """Actual SDK parsers and engines recover without duplicate mutation or early OPEN."""
    replay = ScheduledEngineFixture(tmp_path, lost=lost)
    for asset in replay.config.assets:
        result = replay.enter_current(asset, last_side=last_side)
        assert (
            result.state is SolLiveState.OPEN
            and result.opened_at_ms == replay.decisions[asset.symbol]
        )
        assert replay.clock.now_ms >= replay.order_visible_at[result.stop_oid]
        assert sum(name == "entry" for name in replay.mutations) == len(
            replay.account.snapshot().positions
        )
    assert len(replay.account.snapshot().positions) == 7
    replay.assert_native_account_agreement()
    for asset in reversed(replay.config.assets):
        engine = replay.engine(asset)
        mutations = len(replay.mutations)
        assert engine.start().state is SolLiveState.OPEN
        assert len(replay.mutations) == mutations
        replay.prepare_close(asset.symbol)
        assert (
            engine.exit(mark_price=100, reason="scheduled_native_recovery_check").state
            is SolLiveState.FLAT
        )
        replay.assert_native_account_agreement()
    assert not replay.orders
    assert sum(name == "entry" for name in replay.mutations) == 7
    assert sum(name == "close" for name in replay.mutations) == 7
    assert len(replay.fills) == 28 and len({row["tid"] for row in replay.fills}) == 28
    assert all(item["stop_present"] for item in replay.close_requests)
    assert all(item["flat_before_cancel"] for item in replay.cancel_requests if item["is_stop"])


@pytest.mark.parametrize(
    "symbol", ["BTC", "ETH", "SOL", "HYPE", "xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL"]
)
@pytest.mark.parametrize("last_side", [False, True])
def test_pending_entry_restart_retains_the_durable_decision_clock(
    tmp_path: Path,
    symbol: str,
    last_side: bool,
) -> None:
    """A bounded lookup failure cannot move the hold origin to the later fill clock."""
    replay = ScheduledEngineFixture(tmp_path, lost="entry", recovery_delay_ms=5000)
    asset = replay.assets[symbol]
    decision = replay.clock.now_ms
    with pytest.raises(SolOrderRecoveryError):
        replay.enter_current(asset, last_side=last_side)
    assert symbol in replay.account.snapshot().positions and not replay.orders
    replay.clock.advance_to(decision + 6000)
    result = replay.engine(asset).start()
    assert result.state is SolLiveState.OPEN and result.opened_at_ms == decision
    assert sum(name == "entry" for name in replay.mutations) == 1
    assert result.execution_plan is not None
    assert replay.account.snapshot().positions[symbol].decision_time_ms == decision
    replay.assert_native_account_agreement()


@pytest.mark.parametrize(
    "symbol,operation",
    [
        ("xyz:SNDK", "stop"),
        ("BTC", "stop"),
        ("BTC", "target"),
        ("xyz:SNDK", "close"),
        ("BTC", "close"),
        ("xyz:SNDK", "cancel"),
        ("BTC", "cancel"),
    ],
)
def test_restart_after_exhausted_protection_or_exit_lookup(
    tmp_path: Path,
    symbol: str,
    operation: str,
) -> None:
    """Persisted ownership remains recoverable after the bounded response-loss fault."""
    replay = ScheduledEngineFixture(tmp_path, lost=None, recovery_delay_ms=5000)
    asset = replay.assets[symbol]
    if operation in {"stop", "target"}:
        replay.lost = operation
        with pytest.raises(SolOrderRecoveryError):
            replay.enter_current(asset)
    else:
        replay.enter_current(asset)
        replay.lost = operation
        replay.prepare_close(symbol)
        failure = SolCancelRecoveryError if operation == "cancel" else SolOrderRecoveryError
        with pytest.raises(failure):
            replay.engines[symbol].exit(mark_price=100, reason="restart_failure_injection")
    original_decision = replay.engines[symbol].snapshot.opened_at_ms
    replay.clock.advance_to(replay.clock.now_ms + 6000)
    replay.lost = None
    before = len(replay.mutations)
    result = replay.engine(asset).start()
    if operation in {"stop", "target"}:
        assert result.state is SolLiveState.OPEN and result.opened_at_ms == original_decision
        assert result.execution_plan is not None
        requires_target = result.execution_plan.target_policy != "none"
        assert (result.target_oid is not None) == requires_target
        expected_new_target = int(operation == "stop" and requires_target)
        assert len(replay.mutations) == before + expected_new_target
    elif operation == "cancel" and symbol == "BTC":
        assert result.state is SolLiveState.OPEN and result.opened_at_ms == original_decision
        assert result.target_oid is not None and len(replay.orders) == 2
        assert sum(name == "close" for name in replay.mutations) == 0
        assert replay.mutations[before:] == ["target"]
    else:
        assert result.state is SolLiveState.FLAT
        assert symbol not in replay.account.snapshot().positions and not replay.orders
        assert sum(name == "close" for name in replay.mutations) == 1
    replay.assert_native_account_agreement()


@pytest.mark.parametrize("status", ["unknownOid", "open", "filled", "rejected"])
def test_ambiguous_cancel_restart_requires_consistent_exact_venue_status(
    tmp_path: Path, status: str
) -> None:
    """Missing or contradictory cancel status cannot create a duplicate target."""
    replay = ScheduledEngineFixture(tmp_path, lost=None, recovery_delay_ms=5000)
    asset = replay.assets["BTC"]
    original = replay.enter_current(asset)
    replay.lost = "cancel"
    with pytest.raises(SolCancelRecoveryError):
        replay.engines[asset.symbol].exit(mark_price=100, reason="cancel_status_check")
    replay.clock.advance_to(replay.clock.now_ms + 6000)
    replay.lost = None
    query = replay._query_order

    def inconsistent(address: str, identity: int | str) -> dict[str, object]:
        result = query(address, identity)
        if identity == original.target_oid:
            if status == "unknownOid":
                return {"status": "unknownOid"}
            result["order"]["status"] = status
        return result

    replay._info.query_order_by_oid.side_effect = inconsistent
    before = len(replay.mutations)
    expected = SolCancelRecoveryError if status == "unknownOid" else SolLiveEngineError
    with pytest.raises(expected):
        replay.engine(asset).start()
    assert len(replay.mutations) == before


def test_cancel_restart_can_retry_after_a_second_bounded_lookup_failure(tmp_path: Path) -> None:
    """Another failed startup cannot strand the same exact unresolved cancel."""
    replay = ScheduledEngineFixture(tmp_path, lost=None, recovery_delay_ms=5000)
    asset = replay.assets["BTC"]
    original = replay.enter_current(asset)
    replay.lost = "cancel"
    with pytest.raises(SolCancelRecoveryError):
        replay.engines[asset.symbol].exit(mark_price=100, reason="repeated_cancel_timeout")
    replay.lost = None
    before = len(replay.mutations)
    with pytest.raises(SolCancelRecoveryError):
        replay.engine(asset).start()
    assert len(replay.mutations) == before
    replay.clock.advance_to(replay.clock.now_ms + 6000)
    result = replay.engine(asset).start()
    assert result.state is SolLiveState.OPEN
    assert result.opened_at_ms == original.opened_at_ms and result.stop_oid == original.stop_oid
    assert result.target_oid != original.target_oid
    assert replay.mutations[before:] == ["target"]
