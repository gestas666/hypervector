"""Restart ownership and venue reconciliation tests for the per-asset live engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.hyperliquid_protocol import (
    HyperliquidAccountSnapshot,
    HyperliquidFill,
    HyperliquidOpenOrder,
    HyperliquidPositionSnapshot,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_reconcile import (
    AssetStartupReconciliationError,
    reconcile_asset_startup,
)

_CURRENT_PROFILE = "a" * 64
_PRIOR_PROFILE = "b" * 64


def _position(size: float) -> HyperliquidPositionSnapshot:
    return HyperliquidPositionSnapshot(
        size_signed=size,
        entry_price=73.1 if size else None,
        liquidation_price=60.5 if size else None,
        margin_used_usd=4.386 if size else 0.0,
        position_value_usd=21.93 if size else 0.0,
        unrealized_pnl_usd=0.12 if size else 0.0,
        leverage_type="isolated" if size else None,
        leverage=5 if size else None,
    )


def _stop(oid: int = 202, size: float = 0.30, side: str = "A") -> HyperliquidOpenOrder:
    return HyperliquidOpenOrder(
        oid=oid,
        size=size,
        original_size=size,
        side=side,
        reduce_only=True,
        is_trigger=True,
        trigger_price=72.4,
        order_type="Stop Market",
        timestamp_ms=1_785_495_600_456,
    )


def _target(
    oid: int = 203,
    size: float = 0.30,
    side: str = "A",
    price: float = 74.0,
) -> HyperliquidOpenOrder:
    return HyperliquidOpenOrder(
        oid=oid,
        size=size,
        original_size=size,
        side=side,
        reduce_only=True,
        is_trigger=False,
        trigger_price=None,
        order_type="Limit",
        timestamp_ms=1_785_495_600_456,
        limit_price=price,
    )


def _venue(
    size: float,
    orders: Sequence[HyperliquidOpenOrder] = (),
    fills: Sequence[HyperliquidFill] = (),
) -> HyperliquidReconciliationSnapshot:
    return HyperliquidReconciliationSnapshot(
        account=HyperliquidAccountSnapshot(
            account_value_usd=150.0,
            withdrawable_usd=145.614,
            total_margin_used_usd=4.386 if size else 0.0,
            total_notional_position_usd=21.93 if size else 0.0,
            position=_position(size),
        ),
        open_orders=tuple(orders),
        fills=tuple(fills),
    )


def _stop_fill(oid: int = 202, size: float = 0.30) -> HyperliquidFill:
    return HyperliquidFill(
        oid=oid,
        price=72.4,
        size=size,
        side="A",
        timestamp_ms=1_785_499_200_123,
        fee_usd=0.0098,
        fee_token="USDC",
        closed_pnl_usd=-0.21,
        crossed=True,
        direction="Close Long",
        transaction_hash="0xstop",
        trade_id=10_202,
    )


def _record(
    state: str,
    *,
    entry_oid: int | None = None,
    stop_oid: int | None = None,
    position_size_signed: float = 0.0,
    opened_at_ms: int | None = None,
    execution_plan: object | None = None,
    target_oid: int | None = None,
    target_price: float | None = None,
    profile_fingerprint: str | None = None,
) -> Mapping[str, object]:
    record: dict[str, object] = {
        "sequence": 1,
        "event_type": "state_transition",
        "payload": {
            "state": state,
            "entry_oid": entry_oid,
            "stop_oid": stop_oid,
            "position_size_signed": position_size_signed,
            "opened_at_ms": opened_at_ms,
            "execution_plan": execution_plan,
            "target_oid": target_oid,
            "target_price": target_price,
        },
    }
    if profile_fingerprint is not None:
        record["profile_fingerprint"] = profile_fingerprint
    return record


def test_new_or_previously_flat_ledger_accepts_only_venue_flat() -> None:
    """No local ownership plus no venue state is safe to initialize as flat."""
    empty = reconcile_asset_startup(records=[], venue=_venue(0.0))
    flat = reconcile_asset_startup(records=[_record("FLAT")], venue=_venue(0.0))

    assert empty.disposition == "flat"
    assert flat.disposition == "flat"
    assert empty.ownership is None


def test_preflight_only_restart_accepts_authoritative_venue_flat() -> None:
    """A crash before any durable mutation can restart from verified flat state."""
    outcome = reconcile_asset_startup(
        records=[_record("PREFLIGHT")],
        venue=_venue(0.0),
    )

    assert outcome.disposition == "flat"
    assert outcome.ownership is None


def test_preflight_fault_without_mutation_accepts_authoritative_venue_flat() -> None:
    """A startup fault after preflight remains recoverable when no order began."""
    outcome = reconcile_asset_startup(
        records=[_record("PREFLIGHT"), _record("FAULTED")],
        venue=_venue(0.0),
    )

    assert outcome.disposition == "flat"


def test_fault_after_durable_mutation_remains_ambiguous() -> None:
    """A preflight label cannot erase evidence that a venue mutation began."""
    records = [
        _record("PREFLIGHT"),
        {"event_type": "order_intent", "payload": {"operation": "entry"}},
        _record("FAULTED"),
    ]

    with pytest.raises(AssetStartupReconciliationError, match="FAULTED"):
        reconcile_asset_startup(records=records, venue=_venue(0.0))


def test_definitive_ioc_no_fill_fault_recovers_only_with_venue_flat() -> None:
    """The recorded IOC no-match pattern must not poison a flat restart."""
    client_order_id = "0x11111111111111111111111111111111"
    records = [
        _record("ENTRY_PENDING"),
        {
            "event_type": "order_intent",
            "payload": {
                "operation": "entry",
                "client_order_id": client_order_id,
            },
        },
        {
            "event_type": "order_acknowledgement",
            "payload": {
                "operation": "entry",
                "accepted": False,
                "oid": None,
                "status": "error",
                "error": (
                    "Order could not immediately match against any resting orders. "
                    "asset=214"
                ),
                "client_order_id": client_order_id,
            },
        },
        {
            "event_type": "fault",
            "payload": {
                "reason": (
                    "entry rejected: Order could not immediately match against any "
                    "resting orders. asset=214"
                )
            },
        },
        _record("FAULTED"),
    ]

    outcome = reconcile_asset_startup(records=records, venue=_venue(0.0))

    assert outcome.disposition == "flat"
    assert outcome.ownership is None
    with pytest.raises(AssetStartupReconciliationError, match="unknown venue exposure"):
        reconcile_asset_startup(records=records, venue=_venue(0.30))


def test_verified_owned_position_and_exact_stop_can_be_restored() -> None:
    """Restart restores only matching position size and protective-order identity."""
    outcome = reconcile_asset_startup(
        records=[
            _record(
                "OPEN",
                entry_oid=101,
                stop_oid=202,
                position_size_signed=0.30,
                opened_at_ms=1_785_495_600_000,
            )
        ],
        venue=_venue(0.30, [_stop()]),
    )

    assert outcome.disposition == "restore_open"
    assert outcome.ownership is not None
    assert outcome.ownership.entry_oid == 101
    assert outcome.ownership.stop_oid == 202
    assert outcome.ownership.position_size_signed == pytest.approx(0.30)
    assert outcome.ownership.opened_at_ms == 1_785_495_600_000


def test_same_profile_interrupted_restart_restores_owned_position() -> None:
    """An exact profile match preserves protected restart ownership."""
    outcome = reconcile_asset_startup(
        records=[
            _record(
                "OPEN",
                entry_oid=101,
                stop_oid=202,
                position_size_signed=0.30,
                opened_at_ms=1_785_495_600_000,
                profile_fingerprint=_CURRENT_PROFILE,
            )
        ],
        venue=_venue(0.30, [_stop()]),
        expected_profile_fingerprint=_CURRENT_PROFILE,
    )

    assert outcome.disposition == "restore_open"


def test_changed_profile_cannot_adopt_prior_protected_position() -> None:
    """Foreign-profile ownership is not authority for current-profile recovery."""
    with pytest.raises(
        AssetStartupReconciliationError,
        match="without local ownership",
    ):
        reconcile_asset_startup(
            records=[
                _record(
                    "OPEN",
                    entry_oid=101,
                    stop_oid=202,
                    position_size_signed=0.30,
                    opened_at_ms=1_785_495_600_000,
                    profile_fingerprint=_PRIOR_PROFILE,
                )
            ],
            venue=_venue(0.30, [_stop()]),
            expected_profile_fingerprint=_CURRENT_PROFILE,
        )


def test_restart_ownership_restores_the_original_provider_plan() -> None:
    """A later configuration edit cannot rewrite an already-open contract."""
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=60.0,
        target_policy="none",
        maximum_hold_seconds=172_800,
    ).bind(strategy_id="range", stop_anchor=None)

    outcome = reconcile_asset_startup(
        records=[
            _record(
                "OPEN",
                entry_oid=101,
                stop_oid=202,
                position_size_signed=0.30,
                opened_at_ms=1_785_495_600_000,
                execution_plan=plan.as_payload(),
            )
        ],
        venue=_venue(0.30, [_stop()]),
    )

    assert outcome.ownership is not None
    assert outcome.ownership.execution_plan == plan


def test_verified_owned_position_and_exact_target_bracket_can_be_restored() -> None:
    """A target-bearing plan requires both exact reduce-only venue orders."""
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    outcome = reconcile_asset_startup(
        records=[
            _record(
                "OPEN",
                entry_oid=101,
                stop_oid=202,
                target_oid=203,
                target_price=74.0,
                position_size_signed=0.30,
                opened_at_ms=1_785_495_600_000,
                execution_plan=plan.as_payload(),
            )
        ],
        venue=_venue(0.30, [_stop(), _target()]),
    )

    assert outcome.disposition == "restore_open"
    assert outcome.ownership is not None
    assert outcome.ownership.target_oid == 203
    assert outcome.ownership.target_price == pytest.approx(74.0)


@pytest.mark.parametrize(
    ("records", "venue", "message"),
    [
        ([], _venue(0.30, [_stop()]), "unknown venue exposure"),
        ([_record("FLAT")], _venue(0.0, [_stop()]), "unknown venue order"),
        (
            [
                _record(
                    "OPEN",
                    entry_oid=101,
                    stop_oid=202,
                    position_size_signed=0.30,
                    opened_at_ms=1,
                )
            ],
            _venue(0.30),
            "protective stop 202 is missing",
        ),
        (
            [
                _record(
                    "OPEN",
                    entry_oid=101,
                    stop_oid=202,
                    position_size_signed=0.30,
                    opened_at_ms=1,
                )
            ],
            _venue(0.25, [_stop(size=0.25)]),
            "position size mismatch",
        ),
        (
            [
                _record(
                    "OPEN",
                    entry_oid=101,
                    stop_oid=202,
                    position_size_signed=0.30,
                    opened_at_ms=1,
                )
            ],
            _venue(0.30, [_stop(), _stop(oid=999)]),
            "unknown additional order",
        ),
        (
            [_record("PROTECTING", entry_oid=101, position_size_signed=0.30)],
            _venue(0.30),
            "ambiguous local state PROTECTING",
        ),
    ],
)
def test_ambiguous_or_mismatched_startup_state_fails_closed(
    records: Sequence[Mapping[str, object]],
    venue: HyperliquidReconciliationSnapshot,
    message: str,
) -> None:
    """Unknown ownership, missing protection, or mismatched size is a fault."""
    with pytest.raises(AssetStartupReconciliationError, match=message):
        reconcile_asset_startup(records=records, venue=venue)


def test_stopped_but_protected_position_remains_recoverable() -> None:
    """Operator shutdown preserves the venue stop and ownership record."""
    outcome = reconcile_asset_startup(
        records=[
            _record(
                "STOPPED",
                entry_oid=101,
                stop_oid=202,
                position_size_signed=-0.30,
                opened_at_ms=1_785_495_600_000,
            )
        ],
        venue=_venue(-0.30, [_stop(side="B")]),
    )

    assert outcome.disposition == "restore_open"
    assert outcome.ownership is not None
    assert outcome.ownership.position_size_signed == pytest.approx(-0.30)


def test_restart_recognizes_exact_owned_protective_stop_fill() -> None:
    """Flat venue plus the exact complete owned stop fill is unambiguous recovery."""
    outcome = reconcile_asset_startup(
        records=[
            _record(
                "OPEN",
                entry_oid=101,
                stop_oid=202,
                position_size_signed=0.30,
                opened_at_ms=1_785_495_600_000,
            )
        ],
        venue=_venue(0.0, fills=[_stop_fill()]),
    )

    assert outcome.disposition == "protective_stop_filled"
    assert outcome.ownership is not None
    assert outcome.ownership.stop_oid == 202
