"""Late protective recovery requires original ownership and unambiguous execution."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_asset_live_engine import _order, _stop_fill, _venue

from hypervector.live.asset_order_restart import AssetOrderRestartError
from hypervector.live.asset_protective_restart_context import (
    UNRESOLVED_PROTECTIVE_EXIT,
    records_for_late_protective_exit,
)


def _records(*, bracket: bool = False) -> list[dict[str, object]]:
    original = {
        "state": "OPEN",
        "entry_oid": 101,
        "stop_oid": 202,
        "close_oid": None,
        "position_size_signed": 0.3,
        "opened_at_ms": 1000,
        "execution_plan": None,
        "target_oid": 203 if bracket else None,
        "target_price": 105 if bracket else None,
    }
    reason = (
        "flat reconciliation lacks a complete owned exit fill"
        if bracket
        else "continuous reconciliation failed: position size mismatch: local=0.3 venue=0"
    )
    return [
        {"event_type": "state_transition", "payload": original},
        {"event_type": "fault", "payload": {"reason": reason}},
        {
            "event_type": "state_transition",
            "payload": {**original, "state": "FAULTED", "last_fault": reason},
        },
    ]


@pytest.mark.parametrize("bracket", [False, True])
def test_exact_late_exit_returns_original_records_without_mutating_history(bracket: bool) -> None:
    """A completed exact owned fill yields a recovery view; the audit trail is retained."""
    records = _records(bracket=bracket)
    before = deepcopy(records)
    assert (
        records_for_late_protective_exit(records, _venue(0, fills=(_stop_fill(),))) == records[:1]
    )
    assert records == before


@pytest.mark.parametrize("state", [None, "FLAT", "STOPPED", "EXIT_PENDING", "PREFLIGHT"])
def test_unrelated_lifecycles_are_not_rewound(state: str | None) -> None:
    """Recovery does not manufacture an OPEN ownership record."""
    records = (
        [] if state is None else [{"event_type": "state_transition", "payload": {"state": state}}]
    )
    assert records_for_late_protective_exit(records, _venue(0)) is records


def test_open_without_fault_and_unrelated_fault_keep_existing_recovery() -> None:
    """The exception applies only to the exact read-only protective observation fault."""
    records = _records()
    before = records[:1]
    assert records_for_late_protective_exit(before, _venue(0)) is before
    records[1]["payload"] = {"reason": "unrelated fault"}
    assert records_for_late_protective_exit(records, _venue(0)) is records


@pytest.mark.parametrize(
    "tail",
    [
        {"event_type": "order_intent", "payload": {}},
        {"event_type": "cancel_intent", "payload": {}},
        {"event_type": "close", "payload": {}},
        {"event_type": "fault", "payload": {"reason": "different fault"}},
        {
            "event_type": "state_transition",
            "payload": {"state": "FAULTED", "last_fault": "different"},
        },
        {"event_type": "unknown", "payload": None},
    ],
)
def test_later_execution_or_conflicting_fault_blocks_recovery(tail: dict[str, object]) -> None:
    """A flat venue cannot justify discarding later contradictory execution evidence."""
    records = _records() + [tail]
    with pytest.raises(AssetOrderRestartError, match="protective restart"):
        records_for_late_protective_exit(records, _venue(0, fills=(_stop_fill(),)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("entry_oid", 999),
        ("stop_oid", 999),
        ("target_oid", 999),
        ("target_price", 999),
        ("position_size_signed", 0.2),
        ("opened_at_ms", 2000),
        ("execution_plan", {}),
    ],
)
def test_fault_snapshot_must_preserve_all_original_identity(field: str, value: object) -> None:
    """Ownership, quantity, clock and bound strategy plan cannot change during a retry."""
    records = _records()
    records[-1]["payload"][field] = value
    with pytest.raises(AssetOrderRestartError, match="contradictory"):
        records_for_late_protective_exit(records, _venue(0, fills=(_stop_fill(),)))


@pytest.mark.parametrize(
    "reason",
    [
        UNRESOLVED_PROTECTIVE_EXIT,
        "ambiguous local state FAULTED",
        "unknown venue order exists without local ownership",
    ],
)
def test_read_only_repeated_preflight_failures_preserve_original_ownership(reason: str) -> None:
    """Known unsuccessful restart attempts can neither clear nor replace the old position."""
    records = _records()
    blank = {key: None for key in records[0]["payload"]}
    blank.update(state="PREFLIGHT", position_size_signed=0)
    records.extend(
        [
            {"event_type": "session_start", "payload": {}},
            {"event_type": "state_transition", "payload": blank},
            {"event_type": "fault", "payload": {"reason": reason}},
            {
                "event_type": "state_transition",
                "payload": {**blank, "state": "FAULTED", "last_fault": reason},
            },
        ]
    )
    assert (
        records_for_late_protective_exit(records, _venue(0, fills=(_stop_fill(),))) == records[:1]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"oid": 999},
        {"size": 0.1},
        {"size": -0.3},
        {"size": float("nan")},
        {"side": "B"},
        {"direction": "Open Short"},
        {"timestamp_ms": 999},
        {"trade_id": 0},
    ],
)
def test_missing_or_invalid_execution_attribution_stays_unresolved(
    changes: dict[str, object],
) -> None:
    """Position disappearance is insufficient without complete valid owned fill receipts."""
    fill = replace(_stop_fill(), **changes)
    with pytest.raises(AssetOrderRestartError, match=UNRESOLVED_PROTECTIVE_EXIT):
        records_for_late_protective_exit(_records(), _venue(0, fills=(fill,)))


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "nonflat", "foreign_order", "stop_remains"]
)
def test_ambiguous_venue_observations_stay_unresolved(kind: str) -> None:
    """Duplicate receipts and unexplained live orders cannot authorize a recovered close."""
    fills = () if kind == "missing" else (_stop_fill(),) * (2 if kind == "duplicate" else 1)
    orders = (
        (_order(999 if kind == "foreign_order" else 202, size=0.3, reduce_only=True, trigger=True),)
        if kind.endswith(("order", "remains"))
        else ()
    )
    with pytest.raises(AssetOrderRestartError, match=UNRESOLVED_PROTECTIVE_EXIT):
        records_for_late_protective_exit(
            _records(), _venue(0.3 if kind == "nonflat" else 0, orders, fills)
        )


@pytest.mark.parametrize("duplicate_identity", [False, True])
def test_mixed_bracket_exit_requires_unique_trade_identity_across_orders(
    duplicate_identity: bool,
) -> None:
    """Two independent owned orders cannot claim the same physical execution receipt."""
    stop = _stop_fill(size=0.1)
    target = replace(
        _stop_fill(oid=203, size=0.2), trade_id=stop.trade_id if duplicate_identity else 999
    )
    venue = _venue(0, fills=(stop, target))
    if duplicate_identity:
        with pytest.raises(AssetOrderRestartError, match=UNRESOLVED_PROTECTIVE_EXIT):
            records_for_late_protective_exit(_records(bracket=True), venue)
    else:
        records = _records(bracket=True)
        assert records_for_late_protective_exit(records, venue) == records[:1]


@pytest.mark.parametrize("stop_oid", [None, 203])
def test_protective_identities_must_be_present_and_distinct(stop_oid: int | None) -> None:
    """An incomplete or aliased bracket identity cannot authorize any cleanup."""
    records = _records(bracket=True)
    records[0]["payload"]["stop_oid"] = stop_oid
    records[2]["payload"]["stop_oid"] = stop_oid
    with pytest.raises(AssetOrderRestartError, match="distinct owned"):
        records_for_late_protective_exit(records, _venue(0, fills=(_stop_fill(),)))


def test_bracket_recovery_rejects_duplicate_open_order_rows() -> None:
    """Repeated residual order rows cannot authorize multiple cancellation intents."""
    order = _order(203, size=0.3, reduce_only=True, trigger=False)
    with pytest.raises(AssetOrderRestartError, match=UNRESOLVED_PROTECTIVE_EXIT):
        records_for_late_protective_exit(
            _records(bracket=True), _venue(0, orders=(order, order), fills=(_stop_fill(),))
        )


def test_preflight_cannot_silently_claim_the_original_position() -> None:
    """A restart preflight must retain its empty state until ownership is validated."""
    records = _records()
    records.append(
        {
            "event_type": "state_transition",
            "payload": {**records[0]["payload"], "state": "PREFLIGHT"},
        }
    )
    with pytest.raises(AssetOrderRestartError, match="contradictory"):
        records_for_late_protective_exit(records, _venue(0, fills=(_stop_fill(),)))


def test_malformed_state_payload_is_an_explicit_recovery_error() -> None:
    """Malformed durable ownership cannot be interpreted as an empty account."""
    with pytest.raises(AssetOrderRestartError, match="payload must be an object"):
        records_for_late_protective_exit(
            [{"event_type": "state_transition", "payload": None}], _venue(0)
        )
