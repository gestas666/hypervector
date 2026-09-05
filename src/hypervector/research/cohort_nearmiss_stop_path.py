"""Causal completed-candle and executable-BBO evidence for a near miss."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.research.cohort_forward_paths import causal_path_start_ms
from hypervector.research.cohort_nearmiss_stop_path_reporting import (
    nearmiss_report_contract,
    nearmiss_report_limitations,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000


@dataclass(frozen=True)
class NearMissPathSpec:
    """Frozen identity, risk, and cost assumptions for one near-miss path."""

    run_id: str
    profile_id: str
    profile_fingerprint: str
    strategy_id: str
    symbol: str
    side: str
    decision_time_ms: int
    available_time_ms: int
    reference_price: float
    stop_bps: float
    soft_maximum_hold_seconds: int
    modeled_round_trip_hurdle_bps: float
    notional_usd: float
    target_bps: float | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous identity, direction, timing, or risk geometry."""
        for value, label in (
            (self.run_id, "run id"),
            (self.profile_id, "profile id"),
            (self.profile_fingerprint, "profile fingerprint"),
            (self.strategy_id, "strategy id"),
            (self.symbol, "symbol"),
        ):
            _text(value, label)
        if self.side not in {"long", "short"}:
            raise ValueError("near-miss side must be long or short")
        _nonnegative_integer(self.decision_time_ms, "decision time")
        _nonnegative_integer(self.available_time_ms, "available time")
        causal_path_start_ms(self.decision_time_ms, self.available_time_ms)
        _positive(self.reference_price, "reference price")
        _positive(self.stop_bps, "stop bps")
        _positive_integer(self.soft_maximum_hold_seconds, "soft maximum hold")
        _nonnegative(self.modeled_round_trip_hurdle_bps, "modeled hurdle")
        _positive(self.notional_usd, "notional")
        if self.target_bps is not None:
            _positive(self.target_bps, "target bps")


def build_nearmiss_stop_path(
    cohort_records: Sequence[Record],
    asset_records: Sequence[Record],
    spec: NearMissPathSpec,
) -> dict[str, object]:
    """Resolve a near miss without claiming an unobserved venue-mark trigger."""
    bars, duplicates, conflicts = _completed_bars(cohort_records, spec)
    gaps = _bar_gaps(bars, spec, conflicts)
    stop_price = _stop_price(spec)
    target_price = _target_price(spec)
    stop_candle = _first_candle_cross(bars, spec.side, stop_price, "stop")
    target_candle = _first_candle_cross(bars, spec.side, target_price, "target")
    stop_book = _first_book_cross(asset_records, spec, stop_price, "stop")
    target_book = _first_book_cross(asset_records, spec, target_price, "target")
    technical = {
        "complete": not gaps,
        "technical_gaps": gaps,
        "completed_candles": len(bars),
        "identical_duplicate_candles": duplicates,
        "conflicting_duplicate_candles": conflicts,
    }
    risk = _risk_path(
        bars,
        spec,
        stop_price,
        target_price,
        stop_candle,
        target_candle,
        stop_book,
        target_book,
    )
    status = _status(technical, risk)
    return {
        "schema_version": 1,
        "mode": "cohort_nearmiss_stop_path",
        "contract": nearmiss_report_contract(),
        "identity": _identity(spec),
        "technical": technical,
        "risk_path": risk,
        "economics": _economics(spec, risk),
        "status": status,
        "limitations": nearmiss_report_limitations(),
    }


def _completed_bars(
    records: Sequence[Record], spec: NearMissPathSpec
) -> tuple[list[Record], int, int]:
    indexed: dict[int, Record] = {}
    duplicates = conflicts = 0
    for row in records:
        if (
            row.get("run_id") != spec.run_id
            or row.get("event_type") != "market_candles"
        ):
            continue
        if row.get("profile_id") != spec.profile_id:
            raise ValueError("near-miss cohort profile identity mismatch")
        if row.get("profile_fingerprint") != spec.profile_fingerprint:
            raise ValueError("near-miss cohort profile fingerprint mismatch")
        payload = _mapping(row.get("payload"), "candle payload")
        if payload.get("timeframe") != "1m":
            continue
        symbol_bars = _mapping(payload.get("bars"), "candle symbol map").get(
            spec.symbol
        )
        if symbol_bars is None:
            continue
        for bar in _object_list(symbol_bars, f"{spec.symbol} candles"):
            timestamp = _nonnegative_integer(bar.get("timestamp_ms"), "bar timestamp")
            if timestamp < _path_start_ms(spec):
                continue
            normalized = _validated_bar(bar)
            if timestamp in indexed:
                duplicates += 1
                conflicts += indexed[timestamp] != normalized
            else:
                indexed[timestamp] = normalized
    return [indexed[key] for key in sorted(indexed)], duplicates, conflicts


def _bar_gaps(
    bars: Sequence[Record], spec: NearMissPathSpec, conflicts: int
) -> list[str]:
    gaps: list[str] = []
    if conflicts:
        gaps.append("conflicting_completed_candle")
    if not bars:
        gaps.append("completed_candle_path_missing")
        return gaps
    timestamps = [_integer(bar.get("timestamp_ms"), "bar timestamp") for bar in bars]
    if timestamps[0] != _path_start_ms(spec):
        gaps.append("causal_path_start_candle_missing")
    if any(
        right - left != _MINUTE_MS for left, right in zip(timestamps, timestamps[1:])
    ):
        gaps.append("completed_candle_gap")
    return sorted(gaps)


def _first_candle_cross(
    bars: Sequence[Record], side: str, price: float | None, barrier: str
) -> Record | None:
    if price is None:
        return None
    for bar in bars:
        low = _positive(bar.get("low"), "bar low")
        high = _positive(bar.get("high"), "bar high")
        if _barrier_crossed(side, barrier, price, low, high):
            return bar
    return None


def _first_book_cross(
    records: Sequence[Record],
    spec: NearMissPathSpec,
    barrier_price: float | None,
    barrier: str,
) -> dict[str, object] | None:
    if barrier_price is None:
        return None
    candidates: list[dict[str, object]] = []
    for row in records:
        if (
            row.get("run_id") != spec.run_id
            or row.get("event_type") != "book_observation"
        ):
            continue
        payload = _mapping(row.get("payload"), "book payload")
        timestamp = _nonnegative_integer(payload.get("exchange_ts_ms"), "book time")
        if timestamp < spec.available_time_ms:
            continue
        bid = _top_price(payload.get("bids"), "bid")
        ask = _top_price(payload.get("asks"), "ask")
        if bid >= ask:
            raise ValueError("near-miss book is crossed or locked")
        price = bid if spec.side == "long" else ask
        if _quote_crossed(spec.side, barrier, barrier_price, price):
            candidates.append(
                {
                    "timestamp_ms": timestamp,
                    "observed_at_utc": row.get("observed_at_utc"),
                    "bid": bid,
                    "ask": ask,
                    "executable_exit_price": price,
                }
            )
    return (
        min(candidates, key=lambda value: value["timestamp_ms"]) if candidates else None
    )


def _barrier_crossed(
    side: str, barrier: str, price: float, low: float, high: float
) -> bool:
    if barrier == "stop":
        return low <= price if side == "long" else high >= price
    if barrier == "target":
        return high >= price if side == "long" else low <= price
    raise ValueError("barrier must be stop or target")


def _quote_crossed(side: str, barrier: str, level: float, price: float) -> bool:
    if barrier == "stop":
        return price <= level if side == "long" else price >= level
    if barrier == "target":
        return price >= level if side == "long" else price <= level
    raise ValueError("barrier must be stop or target")


def _first_candle_barrier(
    stop: Record | None, target: Record | None
) -> tuple[str | None, bool]:
    stop_time, target_time = _timestamp(stop), _timestamp(target)
    if stop_time is not None and stop_time == target_time:
        return None, True
    if stop_time is None:
        return ("target" if target_time is not None else None), False
    if target_time is None or stop_time < target_time:
        return "stop", False
    return "target", False


def _confirmed_barrier(
    barrier: str | None,
    stop_candle: Record | None,
    target_candle: Record | None,
    stop_book: Record | None,
    target_book: Record | None,
) -> tuple[str | None, Record | None]:
    if barrier not in {"stop", "target"}:
        return None, None
    book = stop_book if barrier == "stop" else target_book
    opposing = target_candle if barrier == "stop" else stop_candle
    if book is None:
        return None, None
    opposing_time = _timestamp(opposing)
    if opposing_time is not None and _timestamp(book) >= opposing_time:
        return None, None
    return barrier, book


def _timestamp(record: Record | None) -> int | None:
    return (
        _nonnegative_integer(record.get("timestamp_ms"), "evidence timestamp")
        if record is not None
        else None
    )


def _risk_path(
    bars: Sequence[Record],
    spec: NearMissPathSpec,
    stop_price: float,
    target_price: float | None,
    stop_candle: Record | None,
    target_candle: Record | None,
    stop_book: Record | None,
    target_book: Record | None,
) -> dict[str, object]:
    candle_barrier, same_candle = _first_candle_barrier(stop_candle, target_candle)
    barrier, book = _confirmed_barrier(
        candle_barrier, stop_candle, target_candle, stop_book, target_book
    )
    candle_times = [
        _integer(row.get("timestamp_ms"), "cross timestamp")
        for row in (stop_candle, target_candle)
        if row is not None
    ]
    boundary = min(candle_times) if candle_times else None
    path = [
        bar
        for bar in bars
        if boundary is None
        or _integer(bar.get("timestamp_ms"), "bar timestamp") <= boundary
    ]
    mfe, mae = _excursions(path, spec) if path else (None, None)
    return {
        "stop_price": stop_price,
        "target_price": target_price,
        "first_candle_cross_timestamp_ms": _timestamp(stop_candle),
        "first_candle_cross_low": stop_candle.get("low") if stop_candle else None,
        "first_candle_cross_high": stop_candle.get("high") if stop_candle else None,
        "first_executable_cross_timestamp_ms": _timestamp(stop_book),
        "first_executable_cross": stop_book,
        "first_target_candle_cross_timestamp_ms": _timestamp(target_candle),
        "first_target_executable_cross_timestamp_ms": _timestamp(target_book),
        "first_target_executable_cross": target_book,
        "first_candle_barrier": candle_barrier,
        "first_observed_barrier": barrier,
        "first_barrier_executable_cross": book,
        "same_candle_barrier_ambiguity": same_candle,
        "maximum_favorable_excursion_bps": mfe,
        "maximum_adverse_excursion_bps": mae,
        "soft_deadline_timestamp_ms": spec.available_time_ms
        + spec.soft_maximum_hold_seconds * 1_000,
        "actual_mark_trigger_observed": False,
        "venue_stop_fill_observed": False,
    }


def _excursions(bars: Sequence[Record], spec: NearMissPathSpec) -> tuple[float, float]:
    high = max(_positive(bar.get("high"), "bar high") for bar in bars)
    low = min(_positive(bar.get("low"), "bar low") for bar in bars)
    if spec.side == "long":
        return (
            max(0.0, (high / spec.reference_price - 1.0) * 10_000),
            max(0.0, (1.0 - low / spec.reference_price) * 10_000),
        )
    return (
        max(0.0, (1.0 - low / spec.reference_price) * 10_000),
        max(0.0, (high / spec.reference_price - 1.0) * 10_000),
    )


def _economics(spec: NearMissPathSpec, risk: Record) -> dict[str, object]:
    barrier = risk.get("first_observed_barrier")
    book_cross = risk.get("first_barrier_executable_cross")
    if barrier not in {"stop", "target"} or not isinstance(book_cross, Mapping):
        gross = after = dollars = None
    else:
        price = _positive(book_cross.get("executable_exit_price"), "exit proxy")
        direction = 1.0 if spec.side == "long" else -1.0
        gross = direction * (price / spec.reference_price - 1.0) * 10_000
        after = gross - spec.modeled_round_trip_hurdle_bps
        dollars = after * spec.notional_usd / 10_000
    return {
        "notional_usd": spec.notional_usd,
        "modeled_round_trip_hurdle_bps": spec.modeled_round_trip_hurdle_bps,
        "exit_proxy_barrier": barrier,
        "gross_exit_proxy_bps": gross,
        "after_hurdle_exit_proxy_bps": after,
        "after_hurdle_exit_proxy_usd": dollars,
    }


def _status(technical: Record, risk: Record) -> str:
    if technical.get("complete") is not True:
        return "technical_evidence_incomplete"
    if risk.get("same_candle_barrier_ambiguity") is True:
        return "barrier_order_ambiguous_within_candle"
    barrier = risk.get("first_observed_barrier")
    if barrier == "target":
        return "profit_target_proxy_crossed"
    if barrier == "stop":
        return "protective_stop_proxy_crossed"
    if risk.get("first_candle_barrier") == "target":
        return "profit_target_candle_proxy_only"
    if risk.get("first_candle_barrier") == "stop":
        return "protective_stop_candle_proxy_only"
    return "protective_stop_not_observed_in_available_path"


def _identity(spec: NearMissPathSpec) -> dict[str, object]:
    return {
        "run_id": spec.run_id,
        "profile_id": spec.profile_id,
        "profile_fingerprint": spec.profile_fingerprint,
        "strategy_id": spec.strategy_id,
        "symbol": spec.symbol,
        "side": spec.side,
        "decision_time_ms": spec.decision_time_ms,
        "available_time_ms": spec.available_time_ms,
        "causal_path_start_time_ms": _path_start_ms(spec),
        "reference_price": spec.reference_price,
        "stop_bps": spec.stop_bps,
        "target_bps": spec.target_bps,
    }


def _stop_price(spec: NearMissPathSpec) -> float:
    direction = -1.0 if spec.side == "long" else 1.0
    return spec.reference_price * (1.0 + direction * spec.stop_bps / 10_000)


def _path_start_ms(spec: NearMissPathSpec) -> int:
    return causal_path_start_ms(spec.decision_time_ms, spec.available_time_ms)


def _target_price(spec: NearMissPathSpec) -> float | None:
    if spec.target_bps is None:
        return None
    direction = 1.0 if spec.side == "long" else -1.0
    return spec.reference_price * (1.0 + direction * spec.target_bps / 10_000)


def _validated_bar(value: Record) -> dict[str, object]:
    output = {
        "timestamp_ms": _nonnegative_integer(value.get("timestamp_ms"), "bar time"),
        "open": _positive(value.get("open"), "bar open"),
        "high": _positive(value.get("high"), "bar high"),
        "low": _positive(value.get("low"), "bar low"),
        "close": _positive(value.get("close"), "bar close"),
        "volume": _nonnegative(value.get("volume"), "bar volume"),
    }
    if output["low"] > min(output["open"], output["close"]):
        raise ValueError("bar low exceeds its body")
    if output["high"] < max(output["open"], output["close"]):
        raise ValueError("bar high is below its body")
    return output


def _top_price(value: object, label: str) -> float:
    rows = _object_list(value, f"book {label}s")
    if not rows:
        raise ValueError(f"book {label}s must not be empty")
    return _positive(rows[0].get("price"), f"top {label}")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _object_list(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{label} must be a list of objects")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    output = _integer(value, label)
    if output < 0:
        raise ValueError(f"{label} must be nonnegative")
    return output


def _positive_integer(value: object, label: str) -> int:
    output = _integer(value, label)
    if output <= 0:
        raise ValueError(f"{label} must be positive")
    return output


def _positive(value: object, label: str) -> float:
    output = _number(value, label)
    if output <= 0.0:
        raise ValueError(f"{label} must be positive")
    return output


def _nonnegative(value: object, label: str) -> float:
    output = _number(value, label)
    if output < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return output


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    return output
