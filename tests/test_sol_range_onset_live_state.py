"""Deterministic transition tests for the SOL live execution lifecycle."""

from __future__ import annotations

import pytest

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.sol_range_onset_state import (
    SolLiveState,
    SolLiveStateError,
    SolLiveStateMachine,
)


def test_happy_path_requires_protection_before_open_and_flat_before_reentry() -> None:
    """Entry, protection, and close states occur in the required order."""
    machine = SolLiveStateMachine()

    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry()
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=0.30, opened_at_ms=1_000)
    machine.confirm_protection(stop_oid=202)

    assert machine.snapshot.state is SolLiveState.OPEN
    assert machine.snapshot.entry_oid == 101
    assert machine.snapshot.stop_oid == 202
    assert machine.snapshot.position_size_signed == pytest.approx(0.30)
    assert machine.snapshot.opened_at_ms == 1_000

    machine.begin_exit()
    machine.acknowledge_close(303)
    machine.confirm_flat()

    assert machine.snapshot.state is SolLiveState.FLAT
    assert machine.snapshot.entry_oid is None
    assert machine.snapshot.stop_oid is None
    assert machine.snapshot.close_oid is None
    assert machine.snapshot.position_size_signed == 0.0
    assert machine.snapshot.opened_at_ms is None


def test_provider_execution_plan_survives_the_open_lifecycle() -> None:
    """The selected strategy contract remains attached through protection."""
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=60.0,
        target_policy="none",
        maximum_hold_seconds=172_800,
    ).bind(strategy_id="range", stop_anchor=None)
    machine = SolLiveStateMachine()

    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry(execution_plan=plan)
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=0.30, opened_at_ms=1_000)
    machine.confirm_protection(stop_oid=202)

    assert machine.snapshot.execution_plan == plan


def test_target_plan_requires_exact_target_before_open() -> None:
    """A target-bearing plan cannot report OPEN with only its stop placed."""
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="hulk", stop_anchor=None)
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry(execution_plan=plan)
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=-0.30, opened_at_ms=1_000)

    machine.begin_target(stop_oid=202, target_price=71.45)

    assert machine.snapshot.state is SolLiveState.TARGET_PENDING
    assert machine.snapshot.stop_oid == 202
    assert machine.snapshot.target_oid is None
    assert machine.snapshot.target_price == pytest.approx(71.45)

    machine.confirm_target(target_oid=203)

    assert machine.snapshot.state is SolLiveState.OPEN
    assert machine.snapshot.target_oid == 203


def test_disarmed_or_pending_state_cannot_skip_lifecycle_steps() -> None:
    """Illegal transitions fail rather than becoming success-shaped fallbacks."""
    machine = SolLiveStateMachine()

    with pytest.raises(SolLiveStateError, match="DISARMED.*begin_entry"):
        machine.begin_entry()

    machine.begin_preflight()
    with pytest.raises(SolLiveStateError, match="PREFLIGHT.*begin_entry"):
        machine.begin_entry()

    machine.confirm_preflight_flat()
    machine.begin_entry()
    with pytest.raises(SolLiveStateError, match="ENTRY_PENDING.*confirm_protection"):
        machine.confirm_protection(stop_oid=202)


def test_fault_preserves_known_order_and_exposure_identity() -> None:
    """A fault remains auditable and does not pretend the venue is flat."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry()
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=-0.30, opened_at_ms=1_000)

    machine.fault("protective stop rejected")

    assert machine.snapshot.state is SolLiveState.FAULTED
    assert machine.snapshot.entry_oid == 101
    assert machine.snapshot.position_size_signed == pytest.approx(-0.30)
    assert machine.snapshot.last_fault == "protective stop rejected"


def test_operator_stop_preserves_protective_order_for_open_position() -> None:
    """Stopping the process cannot imply cancellation of a venue-native stop."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry()
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=0.30, opened_at_ms=1_000)
    machine.confirm_protection(stop_oid=202)

    machine.stop("operator_stop")

    assert machine.snapshot.state is SolLiveState.STOPPED
    assert machine.snapshot.stop_oid == 202
    assert machine.snapshot.position_size_signed == pytest.approx(0.30)
    assert machine.snapshot.stop_reason == "operator_stop"


def test_unprotected_exposure_cannot_be_reported_as_cleanly_stopped() -> None:
    """A stop request during protection becomes an explicit technical fault."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry()
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=0.30, opened_at_ms=1_000)

    with pytest.raises(SolLiveStateError, match="unprotected"):
        machine.stop("operator_stop")
    assert machine.snapshot.state is SolLiveState.PROTECTING


def test_restart_can_restore_only_a_verified_protected_position() -> None:
    """Recovery accepts an explicit owned entry and stop, never unknown exposure."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.restore_protected_position(
        entry_oid=101,
        stop_oid=202,
        position_size_signed=-0.30,
        opened_at_ms=1_000,
    )

    assert machine.snapshot.state is SolLiveState.OPEN
    assert machine.snapshot.position_size_signed == pytest.approx(-0.30)

    other = SolLiveStateMachine()
    other.begin_preflight()
    with pytest.raises(SolLiveStateError, match="nonzero"):
        other.restore_protected_position(
            entry_oid=101,
            stop_oid=202,
            position_size_signed=0.0,
            opened_at_ms=1_000,
        )


def test_restart_can_restore_a_verified_pending_entry_identity() -> None:
    """A committed entry can resume protection without a second submission."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()

    machine.restore_pending_entry(entry_oid=101)

    assert machine.snapshot.state is SolLiveState.ENTRY_PENDING
    assert machine.snapshot.entry_oid == 101


def test_restart_can_restore_protecting_and_exit_pending_context() -> None:
    """Interrupted stop or close work retains the exact owned position context."""
    protecting = SolLiveStateMachine()
    protecting.begin_preflight()
    protecting.restore_protecting_position(
        entry_oid=101,
        position_size_signed=0.30,
        opened_at_ms=1_000,
    )

    assert protecting.snapshot.state is SolLiveState.PROTECTING
    assert protecting.snapshot.entry_oid == 101

    exiting = SolLiveStateMachine()
    exiting.begin_preflight()
    exiting.restore_exit_pending(
        entry_oid=101,
        stop_oid=202,
        position_size_signed=0.30,
        opened_at_ms=1_000,
    )

    assert exiting.snapshot.state is SolLiveState.EXIT_PENDING
    assert exiting.snapshot.stop_oid == 202


def test_verified_protective_stop_fill_transitions_open_to_flat() -> None:
    """A venue-confirmed owned stop fill clears the sole position lifecycle."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry()
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=0.30, opened_at_ms=1_000)
    machine.confirm_protection(stop_oid=202)

    machine.confirm_protective_stop_fill(stop_oid=202)

    assert machine.snapshot.state is SolLiveState.FLAT
    assert machine.snapshot.position_size_signed == 0.0
    assert machine.snapshot.stop_oid is None


def test_immediate_protective_stop_fill_transitions_protecting_to_flat() -> None:
    """A stop filled before visibility cannot leave a false unprotected fault."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.confirm_preflight_flat()
    machine.begin_entry()
    machine.acknowledge_entry(101)
    machine.begin_protection(position_size_signed=0.30, opened_at_ms=1_000)

    machine.confirm_protective_stop_fill_during_protection(stop_oid=202)

    assert machine.snapshot.state is SolLiveState.FLAT
    assert machine.snapshot.position_size_signed == 0.0
    assert machine.snapshot.stop_oid is None


def test_replacement_stop_fill_transitions_exit_pending_to_flat() -> None:
    """A replacement stop may close residual exposure during a failed exit."""
    machine = SolLiveStateMachine()
    machine.begin_preflight()
    machine.restore_protected_position(
        entry_oid=101,
        stop_oid=202,
        position_size_signed=0.30,
        opened_at_ms=1_000,
    )
    machine.begin_exit()

    machine.confirm_protective_stop_fill_during_exit(stop_oid=204)

    assert machine.snapshot.state is SolLiveState.FLAT
    assert machine.snapshot.position_size_signed == 0.0
