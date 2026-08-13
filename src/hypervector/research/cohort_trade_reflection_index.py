"""Strict indexes for cohort trade-reflection evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_STRATEGIES,
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    object_list,
    payload,
    text,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000


@dataclass(frozen=True)
class Candle:
    """One validated completed one-minute candle."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ReflectionEvidenceIndex:
    """Strict cohort evaluation and completed-candle evidence indexes."""

    evaluations: Mapping[tuple[str, str, str, int], Record]
    latest_by_run: Mapping[tuple[str, str, str], Record]
    timelines: Mapping[tuple[str, str], tuple[Record, ...]]
    candles: Mapping[str, Mapping[int, Candle]]


def exact_canonical_evaluation(
    index: ReflectionEvidenceIndex,
    run_id: str,
    symbol: str,
    decision_time_ms: int,
) -> Record | None:
    """Return exact-time canonical context, preferring the independent source."""
    for strategy in CANONICAL_REGIME_STRATEGIES:
        value = index.evaluations.get((run_id, strategy, symbol, decision_time_ms))
        if value is not None:
            return value
    return None


def latest_canonical_for_run(
    index: ReflectionEvidenceIndex,
    run_id: str,
    symbol: str,
) -> Record | None:
    """Return the newest canonical evaluation within one exact live run."""
    values = [
        value
        for strategy in CANONICAL_REGIME_STRATEGIES
        if (value := index.latest_by_run.get((run_id, strategy, symbol))) is not None
    ]
    return _newest_canonical(values)


def latest_canonical_at_or_before(
    index: ReflectionEvidenceIndex,
    symbol: str,
    timestamp_ms: int,
) -> Record | None:
    """Return the newest canonical row available by an exact causal timestamp."""
    values = [
        value
        for strategy in CANONICAL_REGIME_STRATEGIES
        for value in index.timelines.get((strategy, symbol), ())
        if _evaluation_time(value) <= timestamp_ms
    ]
    return _newest_canonical(values)


def canonical_timeline(
    index: ReflectionEvidenceIndex,
    symbol: str,
) -> tuple[Record, ...]:
    """Merge legacy and independent canonical histories without duplicate closes."""
    by_decision: dict[int, Record] = {}
    for strategy in CANONICAL_REGIME_STRATEGIES:
        for value in index.timelines.get((strategy, symbol), ()):
            by_decision.setdefault(_evaluation_time(value), value)
    return tuple(by_decision[key] for key in sorted(by_decision))


def build_reflection_evidence_index(
    records: Sequence[Record],
) -> ReflectionEvidenceIndex:
    """Index exact, latest-per-run, timeline, and candle reflection evidence."""
    evaluations: dict[tuple[str, str, str, int], Record] = {}
    latest_by_run: dict[tuple[str, str, str], Record] = {}
    timelines: dict[tuple[str, str], list[Record]] = {}
    timeline_decisions: set[tuple[str, str, int]] = set()
    candles: dict[str, dict[int, Candle]] = {}
    candle_versions: dict[tuple[str, str, int], Candle] = {}
    for row in records:
        values = payload(row)
        if row.get("event_type") in {
            "intent_routing",
            "canonical_regime_evaluations",
        }:
            _index_evaluations(
                row,
                values,
                evaluations,
                latest_by_run,
                timelines,
                timeline_decisions,
            )
        elif row.get("event_type") == "market_candles":
            _index_candles(row, values, candles, candle_versions)
    ordered = {
        key: tuple(sorted(items, key=_evaluation_time))
        for key, items in timelines.items()
    }
    return ReflectionEvidenceIndex(evaluations, latest_by_run, ordered, candles)


def _index_evaluations(
    row: Record,
    values: Record,
    evaluations: dict[tuple[str, str, str, int], Record],
    latest_by_run: dict[tuple[str, str, str], Record],
    timelines: dict[tuple[str, str], list[Record]],
    timeline_decisions: set[tuple[str, str, int]],
) -> None:
    run_id = text(row.get("run_id"), "cohort run id")
    for evaluation in object_list(values, "evaluations", required=False):
        strategy = text(evaluation.get("strategy_id"), "evaluation strategy")
        symbol = text(evaluation.get("symbol"), "evaluation symbol")
        decision_ms = nonnegative_int(
            evaluation.get("decision_time_ms"), "evaluation decision time"
        )
        key = (run_id, strategy, symbol, decision_ms)
        prior = evaluations.get(key)
        if prior is not None:
            if prior != evaluation:
                raise ValueError("conflicting duplicate trade-reflection evaluation")
            continue
        evaluations[key] = evaluation
        latest_by_run[(run_id, strategy, symbol)] = evaluation
        timeline_key = (strategy, symbol, decision_ms)
        if timeline_key not in timeline_decisions:
            timelines.setdefault((strategy, symbol), []).append(evaluation)
            timeline_decisions.add(timeline_key)


def _index_candles(
    row: Record,
    values: Record,
    candles: dict[str, dict[int, Candle]],
    versions: dict[tuple[str, str, int], Candle],
) -> None:
    if values.get("timeframe") != "1m":
        raise ValueError("trade reflections require one-minute candles")
    run_id = text(row.get("run_id"), "market candle run id")
    bars = mapping(values.get("bars"), "market candle symbols")
    for raw_symbol, raw_bars in bars.items():
        symbol = text(raw_symbol, "market candle symbol")
        target = candles.setdefault(symbol, {})
        for raw in mapping_list(raw_bars, f"{symbol} market candles"):
            candle = _parse_candle(raw)
            version_key = (run_id, symbol, candle.timestamp_ms)
            prior_version = versions.get(version_key)
            if prior_version is not None and prior_version != candle:
                raise ValueError("conflicting duplicate trade-reflection candle")
            versions[version_key] = candle
            target.setdefault(candle.timestamp_ms, candle)


def _parse_candle(raw: Record) -> Candle:
    timestamp_ms = nonnegative_int(raw.get("timestamp_ms"), "candle timestamp")
    if timestamp_ms % _MINUTE_MS:
        raise ValueError("trade-reflection candle must align to a minute boundary")
    open_price = number(raw.get("open"), "candle open")
    high = number(raw.get("high"), "candle high")
    low = number(raw.get("low"), "candle low")
    close = number(raw.get("close"), "candle close")
    if min(open_price, high, low, close) <= 0.0:
        raise ValueError("trade-reflection candle prices must be positive")
    if high < max(open_price, close) or low > min(open_price, close) or low > high:
        raise ValueError("trade-reflection candle OHLC values are invalid")
    return Candle(timestamp_ms, open_price, high, low, close)


def _evaluation_time(record: Record) -> int:
    return nonnegative_int(record.get("decision_time_ms"), "evaluation decision time")


def _newest_canonical(values: Sequence[Record]) -> Record | None:
    return max(
        values,
        key=lambda value: (
            _evaluation_time(value),
            value.get("strategy_id") == CANONICAL_REGIME_TELEMETRY_STRATEGY,
        ),
        default=None,
    )
