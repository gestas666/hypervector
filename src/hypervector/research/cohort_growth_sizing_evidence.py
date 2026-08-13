"""Validated fee, funding, and visible-depth inputs for cohort sizing stress."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose, isfinite

from hypervector.research.cohort_growth_sizing_stress import VisibleCostQuantiles

Record = Mapping[str, object]


def visible_quantiles(profile: Record) -> VisibleCostQuantiles:
    """Parse conservative adverse one-way exit depth from recent live evidence."""
    samples = _positive_integer(profile.get("snapshot_count"), "snapshot count")
    return _side_quantiles(profile, samples=samples, prefix="visible")


def hip3_visible_quantiles(
    document: Record,
    *,
    notional_usd: float,
) -> VisibleCostQuantiles:
    """Parse exact-notional adverse one-way exit depth from HIP-3 evidence."""
    _require_report_only(document, "HIP-3 liquidity report")
    requested_notional = _positive(notional_usd, "requested HIP-3 notional")
    profile = _mapping(document.get("profile"), "HIP-3 liquidity profile")
    rows = _object_sequence(profile.get("notionals"), "HIP-3 notionals")
    matching = [
        row
        for row in rows
        if isclose(
            _positive(row.get("notional_usd"), "HIP-3 notional"),
            requested_notional,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
    ]
    if len(matching) != 1:
        raise ValueError("HIP-3 liquidity report requires one exact notional")
    row = matching[0]
    samples = _positive_integer(row.get("samples"), "HIP-3 samples")
    return _side_quantiles(row, samples=samples, prefix="HIP-3")


def resolve_one_way_taker_fee_bps(
    records: Sequence[Record],
    *,
    symbol: str,
    profile_id: str,
    profile_fingerprint: str,
    hip3_roster: Record | None,
) -> tuple[float, dict[str, object]]:
    """Resolve one-way taker fees from exact core or HIP-3 evidence."""
    if symbol.startswith("xyz:"):
        if hip3_roster is None:
            raise ValueError(f"HIP-3 fee roster is required for {symbol}")
        market = _hip3_market(hip3_roster, symbol)
        venue = _mapping(market.get("venue"), "HIP-3 venue")
        if venue.get("effective_fee_status") == "resolved":
            rate = _nonnegative(venue.get("taker_fee_rate"), "HIP-3 taker rate")
            return rate * 10_000.0, {
                "source": "hip3_roster_effective_fee",
                "effective_fee_status": "resolved",
                "taker_fee_rate": rate,
            }
        return _observed_fill_fee(
            records,
            profile_id=profile_id,
            profile_fingerprint=profile_fingerprint,
        )
    return _core_schedule_fee(records, profile_id, profile_fingerprint)


def latest_funding_rate(
    rows: Sequence[Record],
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> float:
    """Return the latest ordered exact-symbol funding row inside explicit bounds."""
    start = _nonnegative_integer(start_ms, "funding start")
    end = _nonnegative_integer(end_ms, "funding end")
    if start > end:
        raise ValueError("funding start must not exceed end")
    if not rows:
        raise ValueError(f"official funding history is empty for {symbol}")
    times: list[int] = []
    for row in rows:
        if row.get("coin") != symbol:
            raise ValueError("official funding symbol does not match request")
        timestamp = _nonnegative_integer(row.get("time"), "funding timestamp")
        if not start <= timestamp <= end:
            raise ValueError("official funding timestamp is outside requested bounds")
        times.append(timestamp)
    if times != sorted(set(times)):
        raise ValueError("official funding timestamps must be ordered and unique")
    return _finite(rows[-1].get("fundingRate"), "funding rate")


def _side_quantiles(
    row: Record,
    *,
    samples: int,
    prefix: str,
) -> VisibleCostQuantiles:
    buy = _distribution(row, "buy", samples, prefix)
    sell = _distribution(row, "sell", samples, prefix)
    count = min(buy["count"], sell["count"])
    return VisibleCostQuantiles(
        sample_count=count,
        complete_rate=count / samples,
        p50=max(buy["p50"], sell["p50"]),
        p90=max(buy["p90"], sell["p90"]),
        p99=max(buy["p99"], sell["p99"]),
    )


def _distribution(
    row: Record,
    side: str,
    samples: int,
    prefix: str,
) -> dict[str, float | int]:
    distribution = _mapping(
        row.get(f"{side}_visible_cost_bps"), f"{prefix} {side} distribution"
    )
    count = _positive_integer(distribution.get("count"), f"{prefix} {side} count")
    if count > samples:
        raise ValueError(f"{prefix} {side} count cannot exceed samples")
    declared_rate = _unit_interval(
        row.get(f"{side}_complete_rate"), f"{prefix} {side} completion rate"
    )
    tolerance = 1.0 / samples
    if abs(count / samples - declared_rate) > tolerance:
        raise ValueError(f"{prefix} {side} count conflicts with completion rate")
    return {
        "count": count,
        "p50": _nonnegative(distribution.get("p50"), f"{prefix} {side} p50"),
        "p90": _nonnegative(distribution.get("p90"), f"{prefix} {side} p90"),
        "p99": _nonnegative(distribution.get("p99"), f"{prefix} {side} p99"),
    }


def _hip3_market(document: Record, symbol: str) -> Record:
    if (
        document.get("status") != "available"
        or document.get("report_only") is not True
        or document.get("execution_authority") != "none"
    ):
        raise ValueError("HIP-3 roster contract is invalid")
    markets = _object_sequence(document.get("markets"), "HIP-3 roster markets")
    matching = [row for row in markets if row.get("symbol") == symbol]
    if len(matching) != 1:
        raise ValueError(f"HIP-3 roster requires one exact market for {symbol}")
    return matching[0]


def _observed_fill_fee(
    records: Sequence[Record],
    *,
    profile_id: str,
    profile_fingerprint: str,
) -> tuple[float, dict[str, object]]:
    fills = [
        row
        for row in records
        if row.get("event_type") == "fill"
        and row.get("profile_id") == profile_id
        and row.get("profile_fingerprint") == profile_fingerprint
        and _mapping(row.get("payload"), "fill payload").get("crossed") is True
    ]
    if not fills:
        raise ValueError("unresolved HIP-3 fee requires a compatible taker fill")
    payload = _mapping(fills[-1].get("payload"), "fill payload")
    if payload.get("fee_token") != "USDC":
        raise ValueError("compatible HIP-3 fill fee must be denominated in USDC")
    price = _positive(payload.get("price"), "fill price")
    size = _positive(payload.get("size"), "fill size")
    fee = _nonnegative(payload.get("fee_usd"), "fill fee")
    fee_bps = fee / (price * size) * 10_000.0
    return fee_bps, {
        "source": "compatible_profile_observed_taker_fill",
        "trade_id": payload.get("trade_id"),
        "venue_timestamp_ms": payload.get("venue_timestamp_ms"),
        "fee_usd": fee,
        "notional_usd": price * size,
    }


def _core_schedule_fee(
    records: Sequence[Record], profile_id: str, profile_fingerprint: str
) -> tuple[float, dict[str, object]]:
    schedules = [
        row
        for row in records
        if row.get("event_type") == "fee"
        and row.get("profile_id") == profile_id
        and row.get("profile_fingerprint") == profile_fingerprint
        and _mapping(row.get("payload"), "fee payload").get("source")
        == "venue_fee_schedule"
    ]
    if not schedules:
        raise ValueError("selected core asset has no exact-profile fee schedule")
    payload = _mapping(schedules[-1].get("payload"), "fee payload")
    rate = _nonnegative(payload.get("taker_rate"), "taker fee rate")
    return rate * 10_000.0, {
        "source": "core_venue_fee_schedule",
        "taker_fee_rate": rate,
    }


def _require_report_only(document: Record, label: str) -> None:
    if (
        document.get("ok") is not True
        or document.get("report_only") is not True
        or document.get("execution_authority") != "none"
    ):
        raise ValueError(f"{label} contract is invalid")


def _object_sequence(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative(value: object, label: str) -> float:
    number = _finite(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _unit_interval(value: object, label: str) -> float:
    number = _finite(value, label)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
