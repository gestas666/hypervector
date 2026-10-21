"""Cumulative protective receipts for partial-position reconciliation.

Callers must establish original order ownership and checkpoint provenance. This
pure component proves reduction evidence; it does not verify remaining orders,
authorize mutations, authenticate venue data or estimate collateral release.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
import math

from hypervector.live.hyperliquid_fill_identity import (
    HyperliquidFillIdentityError,
    fill_trade_id,
)
from hypervector.live.hyperliquid_protocol import HyperliquidFill

_QUANTITY_TOLERANCE = 1e-9


class ProtectiveExecutionEvidenceError(ValueError):
    """Protective receipts do not explain the owned position reduction."""


@dataclass(frozen=True)
class ProtectiveExecutionProgress:
    """Retain credited receipts and a stop's outstanding exit obligation."""

    fills: tuple[HyperliquidFill, ...] = ()
    stop_exit_required: bool = False

    def __post_init__(self) -> None:
        """Reject malformed receipt collections before they become durable credit."""
        if not isinstance(self.fills, tuple):
            raise ProtectiveExecutionEvidenceError("credited protective fills must be a tuple")
        if type(self.stop_exit_required) is not bool:
            raise ProtectiveExecutionEvidenceError("stop exit obligation must be boolean")
        if self.stop_exit_required and not self.fills:
            raise ProtectiveExecutionEvidenceError("stop exit obligation requires fill evidence")
        _receipt_map(self.fills)

    def as_payload(self) -> dict[str, object]:
        """Serialize the exact receipt checkpoint for durable lifecycle recovery."""
        return {
            "fills": [asdict(fill) for fill in self.fills],
            "stop_exit_required": self.stop_exit_required,
        }

    @classmethod
    def from_payload(cls, value: object) -> ProtectiveExecutionProgress:
        """Reject malformed checkpoints before restoring credited execution."""
        body = _exact_fields(value, {"fills", "stop_exit_required"}, "protective progress")
        rows, obligation = body["fills"], body["stop_exit_required"]
        if not isinstance(rows, list) or type(obligation) is not bool:
            raise ProtectiveExecutionEvidenceError(
                "protective progress requires fill list and boolean"
            )
        return cls(tuple(_receipt_from_payload(row) for row in rows), obligation)


def observe_protective_execution(
    *,
    previous_size_signed: float,
    current_size_signed: float,
    opened_at_ms: int,
    observed_at_ms: int,
    stop_oid: int,
    target_oid: int | None,
    prior: ProtectiveExecutionProgress,
    fills: tuple[HyperliquidFill, ...],
    additional_exit_oids: tuple[int, ...] = (),
) -> ProtectiveExecutionProgress:
    """Credit only unique owned fills explaining the exact current position delta."""
    owned = _position_contract(
        previous_size_signed,
        current_size_signed,
        opened_at_ms,
        observed_at_ms,
        stop_oid,
        target_oid,
    )
    for oid in additional_exit_oids:
        identity = _integer(oid, "follow-up close oid", minimum=1)
        if identity in owned or not prior.stop_exit_required:
            raise ProtectiveExecutionEvidenceError(
                "follow-up close requires distinct stop-exit ownership"
            )
        owned.add(identity)
    credited = _receipt_map(prior.fills)
    observed = _observed_receipts(fills, owned, set(credited))
    for trade_id, fill in observed.items():
        if trade_id in credited and fill != credited[trade_id]:
            raise ProtectiveExecutionEvidenceError(f"credited protective trade {trade_id} changed")
    new = tuple(fill for trade_id, fill in observed.items() if trade_id not in credited)
    combined = prior.fills + new
    _verify_receipt_context(combined, previous_size_signed, opened_at_ms, observed_at_ms)
    _verify_position_delta(new, previous_size_signed, current_size_signed)
    return ProtectiveExecutionProgress(
        combined, prior.stop_exit_required or any(fill.oid == stop_oid for fill in new)
    )


def _verify_position_delta(new: tuple[HyperliquidFill, ...], previous: float, current: float) -> None:
    if bool(new) != (previous != current):
        raise ProtectiveExecutionEvidenceError(
            "owned protective fills do not explain unchanged or unobserved execution"
        )
    try:
        filled = math.fsum(fill.size for fill in new)
    except OverflowError as exc:
        raise ProtectiveExecutionEvidenceError("protective fill sum exceeds finite range") from exc
    if not math.isclose(
        filled,
        abs(previous) - abs(current),
        rel_tol=0.0,
        abs_tol=_QUANTITY_TOLERANCE,
    ):
        raise ProtectiveExecutionEvidenceError(
            "owned protective fills do not explain position delta"
        )


def _position_contract(
    previous: float,
    current: float,
    opened_ms: int,
    observed_ms: int,
    stop_oid: int,
    target_oid: int | None,
) -> set[int]:
    before = _number(previous, "previous position")
    after = _number(current, "current position")
    opposite_side = after != 0.0 and (before > 0.0) != (after > 0.0)
    if before == 0.0 or opposite_side or abs(after) > abs(before):
        raise ProtectiveExecutionEvidenceError("protective execution requires an owned reduction")
    start, end = (
        _integer(opened_ms, "entry clock"),
        _integer(observed_ms, "observation clock"),
    )
    if start > end:
        raise ProtectiveExecutionEvidenceError("protective observation precedes the entry clock")
    owned = {_integer(stop_oid, "stop oid", minimum=1)}
    if target_oid is not None:
        target = _integer(target_oid, "target oid", minimum=1)
        if target in owned:
            raise ProtectiveExecutionEvidenceError("protective order identities must be distinct")
        owned.add(target)
    return owned


def _observed_receipts(
    fills: tuple[HyperliquidFill, ...], owned: set[int], credited: set[int]
) -> dict[int, HyperliquidFill]:
    selected = _receipt_map(tuple(fill for fill in fills if fill.oid in owned))
    identities = set(selected) | credited
    relevant = tuple(
        fill
        for fill in fills
        if fill.oid in owned or (isinstance(fill.trade_id, int) and fill.trade_id in identities)
    )
    return _receipt_map(relevant)


def _receipt_map(fills: tuple[HyperliquidFill, ...]) -> dict[int, HyperliquidFill]:
    result: dict[int, HyperliquidFill] = {}
    for fill in fills:
        _validate_receipt(fill)
        try:
            identity = fill_trade_id(fill)
        except HyperliquidFillIdentityError as exc:
            raise ProtectiveExecutionEvidenceError(str(exc)) from exc
        if identity in result:
            raise ProtectiveExecutionEvidenceError(
                f"duplicate protective trade identity {identity}"
            )
        result[identity] = fill
    return result


def _validate_receipt(fill: HyperliquidFill) -> None:
    if not isinstance(fill, HyperliquidFill):
        raise ProtectiveExecutionEvidenceError("protective receipt must be a normalized HyperliquidFill")
    _integer(fill.oid, "fill oid", minimum=1)
    _integer(fill.timestamp_ms, "fill timestamp")
    if _number(fill.size, "fill size") <= 0 or _number(fill.price, "fill price") <= 0:
        raise ProtectiveExecutionEvidenceError("protective fill size and price must be positive")
    _number(fill.fee_usd, "fill fee")
    _number(fill.closed_pnl_usd, "fill closed P&L")
    _text(fill.fee_token, "fill fee token")
    _text(fill.transaction_hash, "fill transaction hash")
    direction = _text(fill.direction, "fill direction").strip().lower()
    side = _text(fill.side, "fill side")
    if type(fill.crossed) is not bool or side not in {"A", "B"}:
        raise ProtectiveExecutionEvidenceError("protective fill crossed/side fields are invalid")
    expected = "close long" if fill.side == "A" else "close short"
    if direction != expected:
        raise ProtectiveExecutionEvidenceError("protective fill direction conflicts with its side")


def _verify_receipt_context(
    fills: tuple[HyperliquidFill, ...], size: float, opened_ms: int, observed_ms: int
) -> None:
    side = "A" if size > 0 else "B"
    for fill in fills:
        if fill.side != side or not opened_ms <= fill.timestamp_ms <= observed_ms:
            raise ProtectiveExecutionEvidenceError(
                "protective fill conflicts with position or clock"
            )


def _receipt_from_payload(value: object) -> HyperliquidFill:
    body = _exact_fields(value, {field.name for field in fields(HyperliquidFill)}, "protective receipt")
    crossed = body["crossed"]
    if type(crossed) is not bool:
        raise ProtectiveExecutionEvidenceError("protective fill crossed flag must be boolean")
    return HyperliquidFill(
        oid=_integer(body["oid"], "fill oid", minimum=1),
        price=_number(body["price"], "fill price"),
        size=_number(body["size"], "fill size"),
        side=_text(body["side"], "fill side"),
        timestamp_ms=_integer(body["timestamp_ms"], "fill timestamp"),
        fee_usd=_number(body["fee_usd"], "fill fee"),
        fee_token=_text(body["fee_token"], "fill fee token"),
        closed_pnl_usd=_number(body["closed_pnl_usd"], "fill closed P&L"),
        crossed=crossed,
        direction=_text(body["direction"], "fill direction"),
        transaction_hash=_text(body["transaction_hash"], "fill transaction hash"),
        trade_id=_integer(body["trade_id"], "fill trade_id", minimum=1),
    )


def _exact_fields(value: object, names: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != names:
        raise ProtectiveExecutionEvidenceError(f"{label} has missing or unexpected fields")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtectiveExecutionEvidenceError(f"{label} must be a finite number")
    try:
        parsed = float(value)
    except OverflowError as exc:
        raise ProtectiveExecutionEvidenceError(f"{label} exceeds finite numeric range") from exc
    if not math.isfinite(parsed):
        raise ProtectiveExecutionEvidenceError(f"{label} must be a finite number")
    return parsed


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ProtectiveExecutionEvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtectiveExecutionEvidenceError(f"{label} must be nonempty text")
    return value
