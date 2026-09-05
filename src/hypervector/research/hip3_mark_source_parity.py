"""Report-only parity checks for independent HIP-3 mark transports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math

from hypervector.data.oxa_api import validate_market_symbol

REST_SOURCE = "hyperliquid_info_metaAndAssetCtxs"
WEBSOCKET_SOURCE = "hyperliquid_ws_activeAssetCtx"
_SOURCES = (REST_SOURCE, WEBSOCKET_SOURCE)


@dataclass(frozen=True)
class Hip3MarkParitySpec:
    """Frozen symbol, receipt-time tolerance, and acceptance thresholds."""

    symbol: str
    maximum_pair_age_ms: int
    minimum_pairs: int
    maximum_mark_difference_bps: float

    def __post_init__(self) -> None:
        """Reject an unusable or success-shaped parity specification."""
        validate_market_symbol(self.symbol, "hip3")
        if self.maximum_pair_age_ms < 0:
            raise ValueError("maximum_pair_age_ms must be nonnegative")
        if self.minimum_pairs <= 0:
            raise ValueError("minimum_pairs must be positive")
        if not math.isfinite(self.maximum_mark_difference_bps):
            raise ValueError("maximum_mark_difference_bps must be finite")
        if self.maximum_mark_difference_bps < 0.0:
            raise ValueError("maximum_mark_difference_bps must be nonnegative")


@dataclass(frozen=True)
class _Mark:
    source: str
    received_ts_ns: int
    mark_price: float


def build_hip3_mark_source_parity(
    rows: Iterable[Mapping[str, object]],
    spec: Hip3MarkParitySpec,
) -> dict[str, object]:
    """Compare exact REST and websocket marks by one-to-one receipt proximity."""
    marks = _validated_marks(rows, spec.symbol)
    rest = tuple(mark for mark in marks if mark.source == REST_SOURCE)
    websocket = tuple(mark for mark in marks if mark.source == WEBSOCKET_SOURCE)
    pairs = _nearest_pairs(rest, websocket, spec.maximum_pair_age_ms)
    ages = tuple(
        abs(left.received_ts_ns - right.received_ts_ns) / 1e6 for left, right in pairs
    )
    differences = tuple(_difference_bps(left, right) for left, right in pairs)
    resolved = len(pairs) >= spec.minimum_pairs
    maximum_difference = max(differences, default=None)
    return {
        "schema_version": "hip3_mark_source_parity_v1",
        "symbol": spec.symbol,
        "status": "resolved" if resolved else "insufficient_overlap",
        "parity_passed": bool(
            resolved
            and maximum_difference is not None
            and maximum_difference <= spec.maximum_mark_difference_bps
        ),
        "rest_source": REST_SOURCE,
        "websocket_source": WEBSOCKET_SOURCE,
        "rest_rows": len(rest),
        "websocket_rows": len(websocket),
        "matched_pairs": len(pairs),
        "minimum_pairs": spec.minimum_pairs,
        "maximum_allowed_pair_age_ms": spec.maximum_pair_age_ms,
        "maximum_pair_age_ms": max(ages, default=None),
        "median_pair_age_ms": _median(ages),
        "maximum_allowed_mark_difference_bps": spec.maximum_mark_difference_bps,
        "maximum_mark_difference_bps": maximum_difference,
        "median_mark_difference_bps": _median(differences),
        "first_pair_received_ts_ns": _first_pair_time(pairs),
        "last_pair_received_ts_ns": _last_pair_time(pairs),
        "execution_authority": "none",
        "report_only": True,
        "automatic_live_change": False,
    }


def _validated_marks(
    rows: Iterable[Mapping[str, object]], symbol: str
) -> tuple[_Mark, ...]:
    unique: dict[tuple[str, int], _Mark] = {}
    for row in rows:
        mark = _validated_mark(row, symbol)
        key = (mark.source, mark.received_ts_ns)
        existing = unique.get(key)
        if existing is not None and existing.mark_price != mark.mark_price:
            raise ValueError("HIP-3 mark source has a conflicting duplicate receipt")
        unique[key] = mark
    return tuple(
        sorted(unique.values(), key=lambda item: (item.source, item.received_ts_ns))
    )


def _validated_mark(row: Mapping[str, object], symbol: str) -> _Mark:
    if row.get("symbol") != symbol:
        raise ValueError(f"HIP-3 mark row must match exact symbol {symbol}")
    source = row.get("source")
    if source not in _SOURCES:
        raise ValueError("HIP-3 mark row has an unsupported source identity")
    received_ts_ns = row.get("received_ts_ns")
    if not isinstance(received_ts_ns, int) or isinstance(received_ts_ns, bool):
        raise ValueError("HIP-3 mark receipt timestamp must be an integer")
    if received_ts_ns <= 0:
        raise ValueError("HIP-3 mark receipt timestamp must be positive")
    mark_price = row.get("mark_price")
    if not isinstance(mark_price, (int, float)) or isinstance(mark_price, bool):
        raise ValueError("HIP-3 mark price must be numeric")
    price = float(mark_price)
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("HIP-3 mark price must be finite and positive")
    return _Mark(str(source), received_ts_ns, price)


def _nearest_pairs(
    rest: tuple[_Mark, ...], websocket: tuple[_Mark, ...], maximum_age_ms: int
) -> tuple[tuple[_Mark, _Mark], ...]:
    maximum_age_ns = maximum_age_ms * 1_000_000
    pairs: list[tuple[_Mark, _Mark]] = []
    cursor = 0
    for mark in rest:
        cursor = _nearest_cursor(mark, websocket, cursor)
        if cursor >= len(websocket):
            break
        candidate = websocket[cursor]
        if abs(mark.received_ts_ns - candidate.received_ts_ns) <= maximum_age_ns:
            pairs.append((mark, candidate))
            cursor += 1
    return tuple(pairs)


def _nearest_cursor(mark: _Mark, rows: tuple[_Mark, ...], cursor: int) -> int:
    while cursor + 1 < len(rows):
        current = abs(mark.received_ts_ns - rows[cursor].received_ts_ns)
        following = abs(mark.received_ts_ns - rows[cursor + 1].received_ts_ns)
        if following >= current:
            break
        cursor += 1
    return cursor


def _difference_bps(left: _Mark, right: _Mark) -> float:
    midpoint = (left.mark_price + right.mark_price) / 2.0
    return abs(right.mark_price - left.mark_price) / midpoint * 10_000.0


def _median(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _first_pair_time(pairs: tuple[tuple[_Mark, _Mark], ...]) -> int | None:
    return min(
        (max(left.received_ts_ns, right.received_ts_ns) for left, right in pairs),
        default=None,
    )


def _last_pair_time(pairs: tuple[tuple[_Mark, _Mark], ...]) -> int | None:
    return max(
        (max(left.received_ts_ns, right.received_ts_ns) for left, right in pairs),
        default=None,
    )
