"""Shared causal completed-candle paths for report-only cohort research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    payload,
    text,
)

Record = Mapping[str, object]
MINUTE_MS = 60_000


@dataclass(frozen=True)
class Candle:
    """Validated completed one-minute candle used by causal diagnostics."""

    timestamp_ms: int
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class DirectionalPath:
    """Side-relative path from one decision-time reference price."""

    decision_time_ms: int
    directional_close_return_bps: float
    favorable_excursion_bps: float
    adverse_excursion_bps: float
    path_start_time_ms: int = -1

    def __post_init__(self) -> None:
        """Default direct fixtures to a path beginning at decision time."""
        if self.path_start_time_ms == -1:
            object.__setattr__(self, "path_start_time_ms", self.decision_time_ms)
        if self.path_start_time_ms < self.decision_time_ms:
            raise ValueError("path start cannot precede its decision")
        if self.path_start_time_ms % MINUTE_MS:
            raise ValueError("path start must align to a minute boundary")


def validated_horizons(values: Sequence[int]) -> tuple[int, ...]:
    """Return unique positive horizons in ascending order."""
    horizons = tuple(values)
    if not horizons or len(set(horizons)) != len(horizons):
        raise ValueError("forward horizons must be unique and non-empty")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in horizons
    ):
        raise ValueError("forward horizons must be positive integer minutes")
    return tuple(sorted(horizons))


def build_candle_index(records: Sequence[Record]) -> dict[str, dict[int, Candle]]:
    """Index validated completed one-minute candles by symbol and open time."""
    output: dict[str, dict[int, Candle]] = {}
    for row in event_rows(records, "market_candles"):
        values = payload(row)
        if values.get("timeframe") != "1m":
            raise ValueError("forward diagnostics require one-minute candles")
        bars = mapping(values.get("bars"), "market candle symbols")
        for symbol_value, raw_bars in bars.items():
            symbol = text(symbol_value, "market candle symbol")
            index = output.setdefault(symbol, {})
            _add_candles(index, mapping_list(raw_bars, f"{symbol} market candles"))
    return output


def resolve_directional_path(
    *,
    decision_time_ms: int,
    reference_price: float,
    side: str,
    candles: Mapping[int, Candle],
    horizon_minutes: int,
    available_time_ms: int | None = None,
) -> tuple[str, DirectionalPath | None]:
    """Resolve only a complete contiguous future path from decision time."""
    path_start_ms = causal_path_start_ms(decision_time_ms, available_time_ms)
    _validate_path_request(decision_time_ms, reference_price, side, horizon_minutes)
    if not candles:
        return "missing_data", None
    expected = tuple(
        path_start_ms + offset * MINUTE_MS for offset in range(horizon_minutes)
    )
    if max(candles) < expected[-1]:
        return "censored", None
    if any(value not in candles for value in expected):
        return "missing_data", None
    return "resolved", _directional_path(
        decision_time_ms,
        path_start_ms,
        reference_price,
        side,
        tuple(candles[value] for value in expected),
    )


def causal_path_start_ms(
    decision_time_ms: int, available_time_ms: int | None = None
) -> int:
    """Return the first full minute at or after candidate availability."""
    available = decision_time_ms if available_time_ms is None else available_time_ms
    if isinstance(available, bool) or not isinstance(available, int):
        raise ValueError("candidate availability must be an integer timestamp")
    if available < decision_time_ms:
        raise ValueError("candidate availability cannot precede its decision")
    return ((available + MINUTE_MS - 1) // MINUTE_MS) * MINUTE_MS


def non_overlapping_count(
    decision_times_ms: Sequence[int], horizon_minutes: int
) -> int:
    """Count paths whose decision windows do not overlap."""
    if horizon_minutes < 1:
        raise ValueError("non-overlap horizon must be positive")
    next_available = -1
    count = 0
    for decision_time in sorted(decision_times_ms):
        if decision_time < next_available:
            continue
        count += 1
        next_available = decision_time + horizon_minutes * MINUTE_MS
    return count


def non_overlapping_paths(
    paths: Sequence[DirectionalPath], horizon_minutes: int
) -> tuple[DirectionalPath, ...]:
    """Select the earliest deterministic set of non-overlapping paths."""
    if horizon_minutes < 1:
        raise ValueError("non-overlap horizon must be positive")
    selected: list[DirectionalPath] = []
    next_available = -1
    for path in sorted(paths, key=lambda item: item.path_start_time_ms):
        if path.path_start_time_ms < next_available:
            continue
        selected.append(path)
        next_available = path.path_start_time_ms + horizon_minutes * MINUTE_MS
    return tuple(selected)


def _add_candles(index: dict[int, Candle], raw_bars: Sequence[Record]) -> None:
    for raw in raw_bars:
        candle = _candle(raw)
        prior = index.get(candle.timestamp_ms)
        if prior is not None and prior != candle:
            raise ValueError("conflicting duplicate market candle")
        index[candle.timestamp_ms] = candle


def _candle(raw: Record) -> Candle:
    timestamp_ms = nonnegative_int(raw.get("timestamp_ms"), "candle timestamp")
    if timestamp_ms % MINUTE_MS:
        raise ValueError("market candle timestamp must align to a minute boundary")
    open_price = number(raw.get("open"), "candle open")
    high = number(raw.get("high"), "candle high")
    low = number(raw.get("low"), "candle low")
    close = number(raw.get("close"), "candle close")
    if not _valid_ohlc(open_price, high, low, close):
        raise ValueError("market candle OHLC values are invalid")
    return Candle(timestamp_ms, high, low, close)


def _valid_ohlc(open_price: float, high: float, low: float, close: float) -> bool:
    return (
        min(open_price, high, low, close) > 0.0
        and high >= max(open_price, close)
        and low <= min(open_price, close)
        and low <= high
    )


def _validate_path_request(
    decision_time_ms: int,
    reference_price: float,
    side: str,
    horizon_minutes: int,
) -> None:
    if decision_time_ms < 0 or decision_time_ms % MINUTE_MS:
        raise ValueError("path decision time must be a nonnegative minute boundary")
    if reference_price <= 0.0:
        raise ValueError("path reference price must be positive")
    if side not in {"long", "short"}:
        raise ValueError("path side must be long or short")
    if horizon_minutes < 1:
        raise ValueError("path horizon must be positive")


def _directional_path(
    decision_time_ms: int,
    path_start_time_ms: int,
    reference_price: float,
    side: str,
    path: Sequence[Candle],
) -> DirectionalPath:
    direction = 1.0 if side == "long" else -1.0
    close_return = direction * (path[-1].close / reference_price - 1.0)
    upward = max(value.high for value in path) / reference_price - 1.0
    downward = 1.0 - min(value.low for value in path) / reference_price
    favorable = upward if direction > 0.0 else downward
    adverse = downward if direction > 0.0 else upward
    return DirectionalPath(
        decision_time_ms=decision_time_ms,
        directional_close_return_bps=close_return * 10_000.0,
        favorable_excursion_bps=max(0.0, favorable * 10_000.0),
        adverse_excursion_bps=max(0.0, adverse * 10_000.0),
        path_start_time_ms=path_start_time_ms,
    )
