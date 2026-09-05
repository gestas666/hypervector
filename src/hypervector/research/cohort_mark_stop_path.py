"""Report-only exact venue-mark stop-path diagnostics for one lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from statistics import median

Record = dict[str, object]
_EXACT_SOURCE = "hyperliquid_ws_activeAssetCtx"


@dataclass(frozen=True)
class MarkStopPathSpec:
    """Frozen identity, time window, and stop contract for one mark path."""

    symbol: str
    side: str
    entry_time_ms: int
    as_of_time_ms: int
    stop_price: float
    maximum_gap_ms: int

    def __post_init__(self) -> None:
        """Reject ambiguous or noncausal path contracts."""
        if not self.symbol:
            raise ValueError("mark-stop symbol must be non-empty")
        if self.side not in {"long", "short"}:
            raise ValueError("mark-stop side must be long or short")
        if self.entry_time_ms < 0 or self.as_of_time_ms <= self.entry_time_ms:
            raise ValueError("mark-stop as-of time must be later than entry")
        if not math.isfinite(self.stop_price) or self.stop_price <= 0.0:
            raise ValueError("mark-stop price must be positive and finite")
        if self.maximum_gap_ms <= 0:
            raise ValueError("mark-stop maximum gap must be positive")


@dataclass(frozen=True)
class _Mark:
    observed_ms: int
    received_ns: int
    price: float


def build_mark_stop_path(
    rows: Sequence[Mapping[str, object]], spec: MarkStopPathSpec
) -> Record:
    """Summarize observed exact marks without claiming unobserved continuity."""
    marks = tuple(sorted((_mark(row, spec) for row in rows), key=_receipt_key))
    if not marks:
        raise ValueError("mark-stop path has no exact websocket marks")
    gaps = _gaps(marks, spec)
    first_cross = next((mark for mark in marks if _crossed(mark, spec)), None)
    minimum = min(marks, key=lambda mark: mark.price)
    maximum = max(marks, key=lambda mark: mark.price)
    continuous = max(gap["gap_ms"] for gap in gaps) <= spec.maximum_gap_ms
    return {
        "symbol": spec.symbol,
        "side": spec.side,
        "entry_time_ms": spec.entry_time_ms,
        "as_of_time_ms": spec.as_of_time_ms,
        "stop_price": spec.stop_price,
        "source": _EXACT_SOURCE,
        "mark_rows": len(marks),
        "first_observed_time_ms": marks[0].observed_ms,
        "last_observed_time_ms": marks[-1].observed_ms,
        "minimum_mark_price": minimum.price,
        "minimum_mark_time_ms": minimum.observed_ms,
        "maximum_mark_price": maximum.price,
        "maximum_mark_time_ms": maximum.observed_ms,
        "observed_stop_crossed": first_cross is not None,
        "first_observed_stop_cross_time_ms": _time(first_cross),
        "first_observed_stop_cross_receipt_ns": _receipt(first_cross),
        "maximum_gap_bound_ms": spec.maximum_gap_ms,
        "maximum_receipt_gap_ms": max(gap["gap_ms"] for gap in gaps),
        "median_receipt_gap_ms": median(gap["gap_ms"] for gap in gaps),
        "p99_receipt_gap_ms": _percentile([float(gap["gap_ms"]) for gap in gaps], 0.99),
        "continuous_at_declared_gap_bound": continuous,
        "largest_receipt_gaps": sorted(
            gaps, key=lambda gap: float(gap["gap_ms"]), reverse=True
        )[:10],
        "path_status": _status(first_cross, continuous),
        "unobserved_stop_cross_ruled_out": False,
    }


def _mark(row: Mapping[str, object], spec: MarkStopPathSpec) -> _Mark:
    if row.get("symbol") != spec.symbol:
        raise ValueError("mark-stop row does not match exact symbol")
    if row.get("source") != _EXACT_SOURCE:
        raise ValueError("mark-stop row is not exact websocket activeAssetCtx")
    observed = _integer(row.get("observed_ts_ms"), "observed timestamp")
    received = _integer(row.get("received_ts_ns"), "received timestamp")
    price = _number(row.get("mark_price"), "mark price")
    receipt_ms = received / 1_000_000.0
    if receipt_ms < spec.entry_time_ms or receipt_ms > spec.as_of_time_ms:
        raise ValueError("mark-stop row is outside the frozen receipt window")
    if price <= 0.0:
        raise ValueError("mark-stop mark price must be positive")
    return _Mark(observed, received, price)


def _gaps(marks: Sequence[_Mark], spec: MarkStopPathSpec) -> list[Record]:
    boundaries = [
        (spec.entry_time_ms * 1_000_000, None),
        *((mark.received_ns, mark) for mark in marks),
        (spec.as_of_time_ms * 1_000_000, None),
    ]
    return [
        _gap(left_ns, right_ns, left_mark, right_mark)
        for (left_ns, left_mark), (right_ns, right_mark) in zip(
            boundaries, boundaries[1:]
        )
    ]


def _gap(
    left_ns: int,
    right_ns: int,
    left: _Mark | None,
    right: _Mark | None,
) -> Record:
    return {
        "gap_ms": (right_ns - left_ns) / 1_000_000.0,
        "left_observed_time_ms": _time(left),
        "left_mark_price": None if left is None else left.price,
        "right_observed_time_ms": _time(right),
        "right_mark_price": None if right is None else right.price,
        "boundary_gap": left is None or right is None,
    }


def _crossed(mark: _Mark, spec: MarkStopPathSpec) -> bool:
    return (
        mark.price <= spec.stop_price
        if spec.side == "long"
        else mark.price >= spec.stop_price
    )


def _status(first_cross: _Mark | None, continuous: bool) -> str:
    if first_cross is not None:
        return "observed_stop_cross"
    return "no_observed_stop_cross" if continuous else "incomplete_no_observed_cross"


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _receipt_key(mark: _Mark) -> int:
    return mark.received_ns


def _time(mark: _Mark | None) -> int | None:
    return None if mark is None else mark.observed_ms


def _receipt(mark: _Mark | None) -> int | None:
    return None if mark is None else mark.received_ns


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"mark-stop {label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"mark-stop {label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"mark-stop {label} must be finite")
    return parsed
