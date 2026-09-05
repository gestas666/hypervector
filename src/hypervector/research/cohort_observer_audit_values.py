"""Strict value parsing for disarmed cohort observer audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

Record = Mapping[str, object]
Evaluation = tuple[Record, Record]
Pair = tuple[str, str]
_PREACTIVATION_READINESS_REASON = "pre_activation_readiness_seed"


def _symbols(identity: Record) -> tuple[str, ...]:
    values = _payload(identity).get("enabled_symbols")
    if not isinstance(values, list) or not values:
        raise ValueError("observer identity enabled_symbols must be a non-empty list")
    symbols = tuple(_text(value, "enabled symbol") for value in values)
    if len(set(symbols)) != len(symbols):
        raise ValueError("observer identity enabled_symbols must be unique")
    return symbols


def _expected_pairs(identity: Record) -> frozenset[Pair]:
    providers = _object_list(_payload(identity), "providers")
    pairs = [
        (
            _text(provider.get("strategy_id"), "provider strategy"),
            _text(symbol, "provider symbol"),
        )
        for provider in providers
        for symbol in _list(provider.get("symbols"), "provider symbols")
    ]
    if not pairs:
        raise ValueError("observer identity provider coverage is empty")
    if len(set(pairs)) != len(pairs):
        raise ValueError("observer identity provider/symbol pairs must be unique")
    return frozenset(pairs)


def _evaluations(cycles: Sequence[Record]) -> list[Evaluation]:
    return [
        (cycle, evaluation)
        for cycle in cycles
        for evaluation in _cycle_evaluations(cycle)
    ]


def _cycle_evaluations(cycle: Record) -> list[Record]:
    return _object_list(_payload(cycle), "evaluations")


def _pairs(evaluations: Sequence[Record]) -> list[Pair]:
    return [_pair(value) for value in evaluations]


def _pair(evaluation: Record) -> Pair:
    return (
        _text(evaluation.get("strategy_id"), "evaluation strategy"),
        _text(evaluation.get("symbol"), "evaluation symbol"),
    )


def _evaluation_identities(
    evaluations: Sequence[Evaluation],
) -> list[tuple[str, str, int]]:
    return [
        (*_pair(value), _integer(value.get("decision_time_ms"), "decision time"))
        for _, value in evaluations
    ]


def _is_preactivation_seed(evaluation: Record) -> bool:
    return (
        evaluation.get("backend_non_action_reason") == _PREACTIVATION_READINESS_REASON
    )


def _is_future(arrival: Record, evaluation: Record) -> bool:
    decision_ms = _integer(evaluation.get("decision_time_ms"), "decision time")
    return decision_ms > int(_timestamp(arrival).timestamp() * 1_000)


def _initial_candle_symbols(records: Sequence[Record]) -> frozenset[str]:
    candles = _event_rows(records, "market_candles")
    if not candles:
        return frozenset()
    bars = _mapping(_payload(candles[0]).get("bars"), "market candle bars")
    return frozenset(
        symbol
        for symbol, values in bars.items()
        if isinstance(symbol, str) and isinstance(values, list) and bool(values)
    )


def _numeric_summary(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {"status": "not_observed", "count": 0}
    return {
        "status": "observed",
        "count": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": sum(values) / len(values),
    }


def _event_rows(records: Sequence[Record], event_type: str) -> tuple[Record, ...]:
    return tuple(row for row in records if row.get("event_type") == event_type)


def _strategy_name(identity: Record) -> str | None:
    value = _payload(identity).get("strategy_name")
    return value if isinstance(value, str) else None


def _is_disarmed(record: Record) -> bool:
    return (
        record.get("live_armed") is False
        and record.get("execution_authority") == "none"
    )


def _payload(record: Record) -> Record:
    return _mapping(record.get("payload"), "ledger payload")


def _timestamp(record: Record) -> datetime:
    value = _text(record.get("observed_at_utc"), "observed_at_utc")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    return parsed


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _object_list(payload: Record, key: str) -> list[Record]:
    return [
        _mapping(value, f"{key} item") for value in _list(payload.get(key, []), key)
    ]


def _text_list(value: object, label: str) -> list[str]:
    return [_text(item, f"{label} item") for item in _list(value, label)]


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if result != result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return result
