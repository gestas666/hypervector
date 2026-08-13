"""Strict value and ledger helpers for cohort live-run audits."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
import math

Record = Mapping[str, object]


def expected_provider_pairs(identity: Record) -> set[str]:
    """Return every provider/symbol pair declared by cohort identity."""
    providers = object_list(payload(identity), "providers")
    return {
        f"{text(provider.get('strategy_id'), 'provider strategy')}|{symbol}"
        for provider in providers
        for symbol in text_list(provider.get("symbols"), "provider symbols")
    }


def executable_provider_pairs(identity: Record) -> set[str]:
    """Return provider/symbol pairs granted explicit canary authority."""
    providers = object_list(payload(identity), "providers")
    pairs: set[str] = set()
    for provider in providers:
        strategy = text(provider.get("strategy_id"), "provider strategy")
        observed = set(text_list(provider.get("symbols"), "provider symbols"))
        executable = text_list(
            provider.get("execution_symbols"),
            "provider execution symbols",
        )
        if not set(executable).issubset(observed):
            raise ValueError("provider execution scope exceeds observed symbols")
        pairs.update(f"{strategy}|{symbol}" for symbol in executable)
    if not pairs:
        raise ValueError("cohort identity has no executable provider scope")
    return pairs


def provider_cadence_minutes(identity: Record) -> dict[str, int] | None:
    """Return complete provider cadences, or unavailable for legacy identities."""
    result: dict[str, int] = {}
    for provider in object_list(payload(identity), "providers"):
        if "timeframe" not in provider:
            return None
        strategy = text(provider.get("strategy_id"), "provider strategy")
        cadence = _minute_timeframe(
            text(provider.get("timeframe"), "provider timeframe")
        )
        prior = result.get(strategy)
        if prior is not None and prior != cadence:
            raise ValueError("provider strategy has conflicting timeframes")
        result[strategy] = cadence
    if not result:
        raise ValueError("cohort identity has no provider cadence")
    return result


def configured_symbols(identity: Record) -> tuple[str, ...]:
    """Return the unique configured symbol order."""
    symbols = tuple(text_list(payload(identity).get("enabled_symbols"), "symbols"))
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("cohort enabled symbols must be unique and non-empty")
    return symbols


def object_list(values: Record, key: str, *, required: bool = True) -> list[Record]:
    """Return one required or optional list of object values."""
    value = values.get(key)
    if value is None and not required:
        return []
    return mapping_list(value, key)


def mapping_list(value: object, label: str) -> list[Record]:
    """Validate and return a list of mappings."""
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{label} must be a list of objects")
    return list(value)


def text_list(value: object, label: str) -> list[str]:
    """Validate and return a list of text values."""
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return [text(item, label) for item in value]


def text_counter(records: Sequence[Record], key: str) -> dict[str, int]:
    """Count one required text key across records."""
    return dict(sorted(Counter(text(row.get(key), key) for row in records).items()))


def event_rows(records: Sequence[Record], event_type: str) -> tuple[Record, ...]:
    """Return rows matching one event type."""
    return tuple(row for row in records if row.get("event_type") == event_type)


def latest(records: Sequence[Record], event_type: str) -> Record | None:
    """Return the latest matching row when present."""
    return next(
        (row for row in reversed(records) if row.get("event_type") == event_type), None
    )


def payload(record: Record) -> Record:
    """Return one validated ledger payload."""
    return mapping(record.get("payload"), "ledger payload")


def mapping(value: object, label: str) -> Record:
    """Validate and return an object mapping."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def is_armed_live(record: Record) -> bool:
    """Return whether a ledger row carries armed-mainnet authority."""
    return (
        record.get("execution_mode") == "live"
        and record.get("live_armed") is True
        and record.get("execution_authority") == "hyperliquid_mainnet"
    )


def run_id(record: Record) -> str:
    """Return one required run identity."""
    return text(record.get("run_id"), "run_id")


def timestamp(record: Record) -> datetime:
    """Parse one timezone-aware ledger observation timestamp."""
    value = text(record.get("observed_at_utc"), "observed_at_utc")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    return parsed


def fraction(value: object) -> float:
    """Return a finite unit-interval fraction."""
    result = number(value, "readiness fraction")
    if not 0.0 <= result <= 1.0:
        raise ValueError("readiness fraction must be within [0, 1]")
    return result


def positive_int(value: object, label: str) -> int:
    """Return a strictly positive integer."""
    result = _integer_value(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def nonnegative_int(value: object, label: str) -> int:
    """Return a nonnegative integer."""
    result = _integer_value(value, label)
    if result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def integer(values: Mapping[str, object], key: str) -> int:
    """Return one required integer field from a mapping."""
    return _integer_value(values.get(key), key)


def number(value: object, label: str) -> float:
    """Return one finite numeric value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def text(value: object, label: str) -> str:
    """Return one non-empty text value."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _minute_timeframe(value: str) -> int:
    if not value.endswith("m") or not value[:-1].isdigit():
        raise ValueError("provider timeframe must be expressed in whole minutes")
    minutes = int(value[:-1])
    if minutes < 1:
        raise ValueError("provider timeframe minutes must be positive")
    return minutes
