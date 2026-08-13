"""Order-price attribution checks for Apex MM live evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math


Record = Mapping[str, object]


def audit_quality_attribution(records: Sequence[Record]) -> dict[str, object]:
    """Compare every quality price with its acknowledged order intent."""
    intent_prices = _intent_prices(records)
    order_prices = _acknowledged_order_prices(records, intent_prices)
    checked: set[int] = set()
    mismatched: set[int] = set()
    unresolved: set[int] = set()
    for row in records:
        if row.get("event_type") != "execution_quality":
            continue
        payload = _payload(row)
        oid = _oid(payload.get("oid"))
        raw_expected = payload.get("expected_quote_price")
        if raw_expected is None:
            unresolved.add(oid)
            continue
        expected = _number(raw_expected, "expected_quote_price")
        submitted = order_prices.get(oid)
        if submitted is None:
            unresolved.add(oid)
            continue
        checked.add(oid)
        if not math.isclose(expected, submitted, rel_tol=0.0, abs_tol=1e-9):
            mismatched.add(oid)
    return {
        "checked_oids": sorted(checked),
        "mismatched_oids": sorted(mismatched),
        "unresolved_oids": sorted(unresolved),
    }


def quality_attribution_gaps(attribution: Mapping[str, object]) -> list[str]:
    """Return explicit technical gaps for invalid quality attribution."""
    gaps: list[str] = []
    if attribution.get("mismatched_oids"):
        gaps.append("slippage_expected_price_mismatch")
    if attribution.get("unresolved_oids"):
        gaps.append("slippage_order_attribution_missing")
    return gaps


def metric_coverage_status(
    required: int,
    observed: int,
    orphan_oids: set[object],
) -> str:
    """Describe fill metric coverage without accepting orphan rows."""
    if orphan_oids:
        return "invalid_orphan_metrics"
    if required == 0:
        return "not_applicable_no_fills"
    return "observed" if observed >= required else "missing"


def _intent_prices(records: Sequence[Record]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in records:
        if row.get("event_type") != "order_intent":
            continue
        payload = _payload(row)
        identity = payload.get("client_order_id")
        limit = payload.get("limit_price")
        if isinstance(identity, str) and identity and limit is not None:
            prices[identity] = _number(limit, "order intent limit_price")
    return prices


def _acknowledged_order_prices(
    records: Sequence[Record],
    intent_prices: Mapping[str, float],
) -> dict[int, float]:
    prices: dict[int, float] = {}
    for row in records:
        if row.get("event_type") != "order_acknowledgement":
            continue
        payload = _payload(row)
        identity = payload.get("client_order_id")
        if payload.get("accepted") is not True or not isinstance(identity, str):
            continue
        if identity in intent_prices:
            prices[_oid(payload.get("oid"))] = intent_prices[identity]
    return prices


def _payload(record: Record) -> Mapping[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("live record payload must be an object")
    return payload


def _oid(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("quality attribution oid must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    observed = float(value)
    if not math.isfinite(observed):
        raise ValueError(f"{label} must be finite")
    return observed
