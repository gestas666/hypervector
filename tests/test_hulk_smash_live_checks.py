"""Pure attribution tests for Hulk venue reconciliation."""

from hypervector.live.hulk_smash_live_checks import filled_exit_reason, filled_oid
from hypervector.live.hulk_smash_live_models import (
    HulkSmashLiveSnapshot,
    HulkSmashLiveState,
)
from hypervector.live.hyperliquid_protocol import (
    SolAccountSnapshot,
    SolFill,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
)


def test_mixed_bracket_fills_are_not_reported_as_a_full_target() -> None:
    """A partial target followed by a stop is one mixed bracket exit."""
    venue = _venue(
        _fill(202, timestamp_ms=1_000, size=0.25),
        _fill(201, timestamp_ms=2_000, size=0.50),
    )

    assert filled_exit_reason(_snapshot(), venue) == "mixed_bracket_exit"
    assert filled_oid(_snapshot(), venue) == 201


def test_simultaneous_mixed_bracket_fills_do_not_invent_terminal_oid() -> None:
    """Equal exchange timestamps leave the final closing order ambiguous."""
    venue = _venue(
        _fill(202, timestamp_ms=2_000, size=0.25),
        _fill(201, timestamp_ms=2_000, size=0.50),
    )

    assert filled_exit_reason(_snapshot(), venue) == "mixed_bracket_exit"
    assert filled_oid(_snapshot(), venue) is None


def _snapshot() -> HulkSmashLiveSnapshot:
    return HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.OPEN,
        entry_oid=101,
        stop_oid=201,
        target_oid=202,
        position_size_signed=-0.75,
    )


def _venue(*fills: SolFill) -> SolReconciliationSnapshot:
    position = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    account = SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, position)
    return SolReconciliationSnapshot(account, (), fills)


def _fill(oid: int, *, timestamp_ms: int, size: float) -> SolFill:
    return SolFill(
        oid=oid,
        price=100.0,
        size=size,
        side="B",
        timestamp_ms=timestamp_ms,
        fee_usd=0.01,
        fee_token="USDC",
        closed_pnl_usd=0.0,
        crossed=True,
        direction="Close Short",
        transaction_hash=f"0x{oid:064x}",
        trade_id=timestamp_ms + oid,
    )
