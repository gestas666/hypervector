"""Protective-fill attribution rejects ambiguity and preserves cumulative economics."""

from dataclasses import asdict, replace
import json

import pytest

from hypervector.live.hyperliquid_protocol import SolFill
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionEvidenceError,
    ProtectiveExecutionProgress,
    observe_protective_execution,
)

STOP_OID, TARGET_OID = 41, 42
OPENED_MS, OBSERVED_MS = 1000, 5000


def receipt(*, quantity: float = 2.0, oid: int = TARGET_OID, trade_id: int = 9) -> SolFill:
    """Create one explicit normalized closing receipt, including all economics."""
    return SolFill(
        oid, 123.5, quantity, "A", 2000, 0.25, "USDC", 3.75, False, "Close Long", "0xabc", trade_id
    )


def observe(
    fills: tuple[SolFill, ...],
    *,
    previous: float = 8.0,
    current: float = 6.0,
    prior: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
) -> ProtectiveExecutionProgress:
    """Use a declared long position and observation interval without venue I/O."""
    return observe_protective_execution(
        previous_size_signed=previous,
        current_size_signed=current,
        opened_at_ms=OPENED_MS,
        observed_at_ms=OBSERVED_MS,
        stop_oid=STOP_OID,
        target_oid=TARGET_OID,
        prior=prior,
        fills=fills,
    )


def test_multiple_target_partials_and_final_stop_preserve_receipts_once() -> None:
    """The same target can execute twice before a stop completes the residual exposure."""
    first, second, final = (
        receipt(),
        receipt(quantity=1.5, trade_id=10),
        receipt(quantity=4.5, oid=STOP_OID, trade_id=11),
    )
    initial = observe((first,))
    advanced = observe((second, first), previous=6, current=4.5, prior=initial)
    complete = observe((final, second, first), previous=4.5, current=0, prior=advanced)
    assert complete.fills == (first, second, final)
    assert complete.stop_exit_required is True
    assert sum(fill.size for fill in complete.fills) == 8
    assert sum(fill.fee_usd for fill in complete.fills) == 0.75
    assert (
        ProtectiveExecutionProgress.from_payload(json.loads(json.dumps(complete.as_payload())))
        == complete
    )


def test_prior_receipts_need_not_remain_in_bounded_recent_history() -> None:
    """Durably retained fills survive omission from a later bounded fill response."""
    first, final = receipt(), receipt(quantity=6, trade_id=10)
    initial = observe((first,))
    assert observe((), previous=6, current=6, prior=initial) == initial
    complete = observe((final,), previous=6, current=0, prior=initial)
    assert complete.fills == (first, final)
    assert not complete.stop_exit_required


def test_stop_exit_obligation_survives_later_no_change_observations() -> None:
    """Missing recent history must not erase the obligation to finish a triggered stop."""
    progress = observe((receipt(oid=STOP_OID),))
    assert progress.stop_exit_required
    assert observe((), previous=6, current=6, prior=progress).stop_exit_required


def test_unowned_fills_do_not_explain_a_position_reduction() -> None:
    """Another order's matching size does not establish local protective ownership."""
    with pytest.raises(ProtectiveExecutionEvidenceError, match="explain"):
        observe((receipt(oid=99),))


def test_unrelated_valid_fills_do_not_change_owned_attribution() -> None:
    """Only the current protective orders supply new reduction evidence."""
    owned = receipt()
    result = observe((owned, receipt(quantity=500, oid=99, trade_id=10)))
    assert result.fills == (owned,)


@pytest.mark.parametrize("previous,current", [(0, 0), (8, 9), (8, -1), (-8, 1)])
def test_non_reductions_cannot_be_adopted(previous: float, current: float) -> None:
    """A protective fill cannot establish a reversal, increase or ownerless position."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((receipt(),), previous=previous, current=current)


@pytest.mark.parametrize("previous,current", [(8, 8), (8, 7), (8, 0), (8, 5.999)])
def test_fill_size_must_explain_the_entire_delta(previous: float, current: float) -> None:
    """A real receipt cannot justify an unchanged or inconsistently changed position."""
    with pytest.raises(ProtectiveExecutionEvidenceError, match="explain"):
        observe((receipt(),), previous=previous, current=current)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "8"])
@pytest.mark.parametrize("field", ["previous", "current"])
def test_invalid_position_numbers_fail_closed(field: str, value: object) -> None:
    """Nonfinite values and implicit string/boolean conversion cannot confer ownership."""
    arguments = {"previous": 8.0, "current": 6.0, field: value}
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((receipt(),), **arguments)


@pytest.mark.parametrize(
    "change",
    [
        {"size": 0.0},
        {"size": -2.0},
        {"size": float("nan")},
        {"size": True},
        {"price": 0.0},
        {"price": float("inf")},
        {"price": "123.5"},
        {"fee_usd": float("nan")},
        {"fee_usd": True},
        {"closed_pnl_usd": float("inf")},
        {"crossed": 1},
        {"fee_token": ""},
        {"fee_token": 5},
        {"transaction_hash": ""},
        {"side": "B"},
        {"side": 0},
        {"direction": "Open Long"},
        {"direction": None},
        {"timestamp_ms": OPENED_MS - 1},
        {"timestamp_ms": OBSERVED_MS + 1},
        {"timestamp_ms": 2000.5},
        {"timestamp_ms": True},
        {"trade_id": 0},
        {"trade_id": True},
        {"trade_id": 9.5},
    ],
)
def test_invalid_owned_receipt_is_not_ignored(change: dict[str, object]) -> None:
    """Every owned row must be coherent; filtering a bad row could hide a conflict."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((replace(receipt(), **change),))


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"oid": STOP_OID},
        {"size": 1.0},
        {"timestamp_ms": 3000},
        {"fee_usd": 9.0},
        {"closed_pnl_usd": -20.0},
        {"price": 90.0},
        {"transaction_hash": "0xdef"},
        {"crossed": True},
        {"fee_token": "OTHER"},
    ],
)
def test_duplicate_trade_identity_in_one_response_is_rejected(change: dict[str, object]) -> None:
    """Duplicate rows and contradictory reuse are both rejected rather than double counted."""
    fill = receipt(quantity=1)
    with pytest.raises(ProtectiveExecutionEvidenceError, match="duplicate"):
        observe((fill, replace(fill, **change)))


@pytest.mark.parametrize(
    "change",
    [
        {"oid": 99},
        {"size": 1.0},
        {"timestamp_ms": 3000},
        {"fee_usd": 9.0},
        {"closed_pnl_usd": -20.0},
        {"price": 90.0},
        {"transaction_hash": "0xdef"},
        {"crossed": True},
        {"fee_token": "OTHER"},
        {"side": "B"},
    ],
)
def test_a_credited_receipt_cannot_change_in_a_later_response(change: dict[str, object]) -> None:
    """The same trade ID must preserve the complete receipt, even after order replacement."""
    fill = receipt()
    progress = observe((fill,))
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((replace(fill, **change),), previous=6, current=6, prior=progress)


@pytest.mark.parametrize("short", [False, True])
def test_complete_fill_direction_and_rebate_are_preserved(short: bool) -> None:
    """Short reductions reverse fill side; signed fees retain reported maker rebates."""
    fill = replace(
        receipt(quantity=8),
        fee_usd=-0.25,
        side="B" if short else "A",
        direction="Close Short" if short else "Close Long",
    )
    result = observe((fill,), previous=-8 if short else 8, current=0)
    assert result.fills == (fill,) and result.fills[0].fee_usd == -0.25


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"fills": []},
        {"fills": [], "stop_exit_required": False, "extra": 1},
        {"fills": (), "stop_exit_required": False},
        {"fills": [], "stop_exit_required": "false"},
        {"fills": [], "stop_exit_required": True},
        {"fills": [None], "stop_exit_required": False},
        {"fills": [asdict(receipt()), asdict(receipt())], "stop_exit_required": False},
    ],
)
def test_corrupt_checkpoint_is_rejected(value: object) -> None:
    """A persisted checkpoint requires exact fields, identity and boolean obligation."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        ProtectiveExecutionProgress.from_payload(value)


@pytest.mark.parametrize("field", list(SolFill.__dataclass_fields__))
def test_checkpoint_requires_every_economic_receipt_field(field: str) -> None:
    """Losing a price, fee or identity field cannot become a successful restart."""
    raw = asdict(receipt())
    del raw[field]
    with pytest.raises(ProtectiveExecutionEvidenceError):
        ProtectiveExecutionProgress.from_payload({"fills": [raw], "stop_exit_required": False})


def test_empty_checkpoint_round_trip_and_unchanged_position() -> None:
    """No activity has a strict, explicit empty checkpoint without an exit obligation."""
    empty = ProtectiveExecutionProgress()
    assert ProtectiveExecutionProgress.from_payload(empty.as_payload()) == empty
    assert observe((), current=8) == empty


@pytest.mark.parametrize(
    "change",
    [
        {"opened_at_ms": -1},
        {"opened_at_ms": True},
        {"opened_at_ms": "1000"},
        {"observed_at_ms": OPENED_MS - 1},
        {"observed_at_ms": float("nan")},
        {"stop_oid": 0},
        {"stop_oid": True},
        {"stop_oid": "41"},
        {"target_oid": 0},
        {"target_oid": STOP_OID},
        {"target_oid": True},
    ],
)
def test_malformed_ownership_contract_is_rejected(change: dict[str, object]) -> None:
    """Fill evidence cannot repair invalid ownership identities or observation clocks."""
    arguments = {
        "previous_size_signed": 8,
        "current_size_signed": 6,
        "opened_at_ms": OPENED_MS,
        "observed_at_ms": OBSERVED_MS,
        "stop_oid": STOP_OID,
        "target_oid": TARGET_OID,
        "prior": ProtectiveExecutionProgress(),
        "fills": (receipt(),),
    }
    arguments.update(change)
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe_protective_execution(**arguments)


def test_stop_only_contract_does_not_need_target_identity() -> None:
    """A native stop-only strategy establishes its own exact reduction and obligation."""
    fill = receipt(oid=STOP_OID)
    progress = observe_protective_execution(
        previous_size_signed=8,
        current_size_signed=6,
        opened_at_ms=OPENED_MS,
        observed_at_ms=OBSERVED_MS,
        stop_oid=STOP_OID,
        target_oid=None,
        prior=ProtectiveExecutionProgress(),
        fills=(fill,),
    )
    assert progress.fills == (fill,) and progress.stop_exit_required


@pytest.mark.parametrize(
    "change",
    [
        {"crossed": "false"},
        {"price": True},
        {"size": -1},
        {"side": "X"},
        {"trade_id": 0},
        {"oid": True},
        {"timestamp_ms": -1},
        {"fee_token": ""},
        {"transaction_hash": None},
        {"direction": "Open Long"},
        {"unknown_field": 1},
    ],
)
def test_checkpoint_cannot_smuggle_malformed_receipts(change: dict[str, object]) -> None:
    """Parsing applies the same receipt constraints as a fresh venue observation."""
    raw = asdict(receipt()) | change
    with pytest.raises(ProtectiveExecutionEvidenceError):
        ProtectiveExecutionProgress.from_payload({"fills": [raw], "stop_exit_required": False})


@pytest.mark.parametrize(
    "arguments",
    [
        {"fills": []},
        {"fills": (None,)},
        {"stop_exit_required": 1},
        {"stop_exit_required": True},
        {"fills": (receipt(), receipt())},
    ],
)
def test_invalid_in_memory_checkpoint_is_rejected(arguments: dict[str, object]) -> None:
    """The immutable checkpoint itself cannot contain a malformed credit collection."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        ProtectiveExecutionProgress(**arguments)


def test_conflicting_unowned_row_cannot_reuse_current_owned_trade_id() -> None:
    """Identity conflicts are detected across both owned and otherwise unrelated rows."""
    fill = receipt(quantity=1)
    with pytest.raises(ProtectiveExecutionEvidenceError, match="duplicate"):
        observe((fill, replace(fill, oid=99)))


def test_tiny_reversed_position_cannot_pass_through_float_underflow() -> None:
    """Sign comparison remains meaningful when multiplying tiny sizes underflows."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((), previous=1e-200, current=-1e-200)


def test_position_integer_overflow_is_a_controlled_evidence_error() -> None:
    """An unrepresentable numeric input must report a specific evidence failure."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((), previous=10**1000, current=0)


def test_prior_checkpoint_cannot_belong_to_another_position_clock() -> None:
    """Even omitted recent receipts remain bound to the original execution interval."""
    progress = observe((receipt(),))
    with pytest.raises(ProtectiveExecutionEvidenceError, match="clock"):
        observe_protective_execution(
            previous_size_signed=6,
            current_size_signed=6,
            opened_at_ms=3000,
            observed_at_ms=OBSERVED_MS,
            stop_oid=STOP_OID,
            target_oid=TARGET_OID,
            prior=progress,
            fills=(),
        )


def test_small_delta_still_requires_a_new_owned_receipt() -> None:
    """Quantity tolerance does not authorize an unexplained small reduction."""
    with pytest.raises(ProtectiveExecutionEvidenceError, match="explain"):
        observe((), previous=1e-10, current=0)


def test_small_new_receipt_cannot_explain_an_unchanged_position() -> None:
    """A nonzero receipt must correspond to an actual observed position reduction."""
    with pytest.raises(ProtectiveExecutionEvidenceError, match="explain"):
        observe((receipt(quantity=1e-10),), previous=8, current=8)


def test_sum_overflow_is_a_controlled_evidence_error() -> None:
    """Individually finite receipts cannot overflow aggregate execution validation."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe(
            (receipt(quantity=1e308), receipt(quantity=1e308, trade_id=10)),
            previous=1e308,
            current=0,
        )


def test_invalid_container_side_is_a_controlled_evidence_error() -> None:
    """Malformed normalized input is reported without leaking a container type error."""
    with pytest.raises(ProtectiveExecutionEvidenceError):
        observe((replace(receipt(), side=[]),))
