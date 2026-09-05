"""Causal report-only lag diagnostics for HIP-3 REST mark responses."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_mark_source_parity import (
    REST_SOURCE,
    WEBSOCKET_SOURCE,
)


@dataclass(frozen=True)
class Hip3MarkResponseLagSpec:
    """Frozen symbol and minimum independent REST response count."""

    symbol: str
    minimum_rest_rows: int

    def __post_init__(self) -> None:
        """Reject aliased symbols and success-shaped overlap thresholds."""
        validate_market_symbol(self.symbol, "hip3")
        if self.minimum_rest_rows <= 0:
            raise ValueError("minimum_rest_rows must be positive")


@dataclass(frozen=True)
class _Context:
    mark_price: float
    oracle_price: float
    funding_rate_hourly: float
    open_interest: float
    mid_price: float | None


@dataclass(frozen=True)
class _Observation:
    source: str
    received_ts_ns: int
    context: _Context


def build_hip3_mark_response_lag(
    rows: Iterable[Mapping[str, object]],
    spec: Hip3MarkResponseLagSpec,
) -> dict[str, object]:
    """Measure each REST context against only causally prior WebSocket rows."""
    observations = _validated_observations(rows, spec.symbol)
    rest = tuple(row for row in observations if row.source == REST_SOURCE)
    websocket = tuple(row for row in observations if row.source == WEBSOCKET_SOURCE)
    records = _lag_records(rest, websocket)
    resolved = len(rest) >= spec.minimum_rest_rows and bool(websocket)
    stale = sum(record["context_relation"] == "stale_prior_match" for record in records)
    future = sum(
        record["context_relation"] == "future_only_match" for record in records
    )
    unmatched = sum(
        record["context_relation"] == "no_matching_context" for record in records
    )
    latest = sum(
        record["context_relation"] == "latest_prior_match" for record in records
    )
    lag = _numeric_values(records, "matching_prior_context_lag_ms")
    age = _numeric_values(records, "latest_websocket_age_ms")
    difference = _numeric_values(records, "mark_difference_to_latest_websocket_bps")
    return {
        "schema_version": "hip3_mark_response_lag_v1",
        "symbol": spec.symbol,
        "status": "resolved" if resolved else "insufficient_overlap",
        "disposition": _disposition(resolved, stale, future, unmatched),
        "rest_rows": len(rest),
        "websocket_rows": len(websocket),
        "minimum_rest_rows": spec.minimum_rest_rows,
        "latest_context_match_rows": latest,
        "stale_context_rows": stale,
        "future_only_context_rows": future,
        "no_matching_context_rows": unmatched,
        **_distribution("matching_context_lag_ms", lag),
        **_distribution("latest_websocket_age_ms", age),
        **_distribution("mark_difference_to_latest_websocket_bps", difference),
        "records": records,
        "execution_authority": "none",
        "report_only": True,
        "automatic_live_change": False,
    }


def _validated_observations(
    rows: Iterable[Mapping[str, object]], symbol: str
) -> tuple[_Observation, ...]:
    unique: dict[tuple[str, int], _Observation] = {}
    for row in rows:
        observation = _validated_observation(row, symbol)
        key = (observation.source, observation.received_ts_ns)
        existing = unique.get(key)
        if existing is not None and existing.context != observation.context:
            raise ValueError("HIP-3 mark response has a conflicting duplicate receipt")
        unique[key] = observation
    return tuple(sorted(unique.values(), key=lambda row: row.received_ts_ns))


def _validated_observation(row: Mapping[str, object], symbol: str) -> _Observation:
    if row.get("symbol") != symbol:
        raise ValueError(f"HIP-3 mark response must match exact symbol {symbol}")
    source = row.get("source")
    if source not in {REST_SOURCE, WEBSOCKET_SOURCE}:
        raise ValueError("HIP-3 mark response has an unsupported source")
    received = row.get("received_ts_ns")
    if isinstance(received, bool) or not isinstance(received, int) or received <= 0:
        raise ValueError("HIP-3 mark response receipt must be a positive integer")
    context = _Context(
        _number(row, "mark_price", positive=True),
        _number(row, "oracle_price", positive=True),
        _number(row, "funding_rate_hourly"),
        _number(row, "open_interest", positive=True),
        _optional_number(row, "mid_price", positive=True),
    )
    return _Observation(str(source), received, context)


def _lag_records(
    rest: Sequence[_Observation], websocket: Sequence[_Observation]
) -> list[dict[str, object]]:
    websocket_times = [row.received_ts_ns for row in websocket]
    times_by_context: dict[_Context, list[int]] = defaultdict(list)
    for row in websocket:
        times_by_context[row.context].append(row.received_ts_ns)
    output: list[dict[str, object]] = []
    for row in rest:
        latest_index = bisect_right(websocket_times, row.received_ts_ns) - 1
        latest = websocket[latest_index] if latest_index >= 0 else None
        matching = times_by_context.get(row.context, [])
        prior_index = bisect_right(matching, row.received_ts_ns) - 1
        prior = matching[prior_index] if prior_index >= 0 else None
        future_index = bisect_right(matching, row.received_ts_ns)
        future = matching[future_index] if future_index < len(matching) else None
        output.append(_lag_record(row, latest, prior, future))
    return output


def _lag_record(
    rest: _Observation,
    latest: _Observation | None,
    matching_prior: int | None,
    matching_future: int | None,
) -> dict[str, object]:
    relation = _context_relation(rest, latest, matching_prior, matching_future)
    return {
        "rest_received_ts_ns": rest.received_ts_ns,
        "context_relation": relation,
        "latest_websocket_received_ts_ns": _timestamp(latest),
        "latest_websocket_age_ms": _age(rest.received_ts_ns, _timestamp(latest)),
        "matching_prior_websocket_received_ts_ns": matching_prior,
        "matching_prior_context_lag_ms": _age(rest.received_ts_ns, matching_prior),
        "matching_future_websocket_received_ts_ns": matching_future,
        "mark_difference_to_latest_websocket_bps": _mark_difference(rest, latest),
    }


def _context_relation(
    rest: _Observation,
    latest: _Observation | None,
    prior: int | None,
    future: int | None,
) -> str:
    if latest is not None and latest.context == rest.context:
        return "latest_prior_match"
    if prior is not None:
        return "stale_prior_match"
    if future is not None:
        return "future_only_match"
    return "no_matching_context"


def _mark_difference(
    rest: _Observation, websocket: _Observation | None
) -> float | None:
    if websocket is None:
        return None
    midpoint = (rest.context.mark_price + websocket.context.mark_price) / 2.0
    return (
        abs(rest.context.mark_price - websocket.context.mark_price) / midpoint * 10_000
    )


def _distribution(label: str, values: Sequence[float]) -> dict[str, float | None]:
    return {
        f"median_{label}": _quantile(values, 0.5),
        f"p90_{label}": _quantile(values, 0.9),
        f"p99_{label}": _quantile(values, 0.99),
        f"maximum_{label}": max(values, default=None),
    }


def _quantile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _numeric_values(records: Sequence[Mapping[str, object]], key: str) -> list[float]:
    return [
        float(value) for row in records if isinstance((value := row.get(key)), float)
    ]


def _disposition(resolved: bool, stale: int, future: int, unmatched: int) -> str:
    if not resolved:
        return "collect_more_overlap"
    if stale or future or unmatched:
        return "rest_receipt_cannot_certify_exact_mark_time"
    return "no_mismatch_observed_not_source_promotion"


def _number(row: Mapping[str, object], key: str, *, positive: bool = False) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 mark response {key} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise ValueError(f"HIP-3 mark response {key} is invalid")
    return result


def _optional_number(
    row: Mapping[str, object], key: str, *, positive: bool = False
) -> float | None:
    return None if row.get(key) is None else _number(row, key, positive=positive)


def _timestamp(value: _Observation | None) -> int | None:
    return value.received_ts_ns if value is not None else None


def _age(later: int, earlier: int | None) -> float | None:
    return None if earlier is None else (later - earlier) / 1_000_000.0
