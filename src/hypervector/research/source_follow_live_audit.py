"""Report-only audit primitives for an event-sourced source-follow live run."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
import math
from pathlib import Path
from statistics import median

from hypervector.research.source_follow_live_market_audit import (
    LedgerCandle,
    l2_quality,
    trade_bar_parity,
)

_CANDLE_EVENT_TYPES = frozenset({"regime_history", "regime_decision"})


def audit_source_follow_live_run(
    rows: Sequence[Mapping[str, object]],
    *,
    database_path: Path | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    """Audit one identified live run without constructing execution authority."""
    selected_id, selected = _select_run(rows, run_id)
    identity = _configuration_identity(selected)
    profile_id = _single_profile(selected)
    candles = _candles(selected)
    symbol = _payload(identity).get("symbol")
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "run": {
            "run_id": selected_id,
            "profile_id": profile_id,
            "row_count": len(selected),
            "first_observed_at_utc": selected[0].get("observed_at_utc"),
            "last_observed_at_utc": selected[-1].get("observed_at_utc"),
            "symbol": symbol,
        },
        "history": _history_summary(selected),
        "decisions": _decision_summary(selected),
        "decision_latency": _decision_latency_summary(selected),
        "regime_diagnostics": _regime_diagnostics_summary(selected),
        "lifecycle": _lifecycle_summary(selected),
        "market_parity": None
        if database_path is None
        else trade_bar_parity(
            database_path,
            candles,
            _required_text(symbol, "configuration symbol"),
        ),
        "l2_quality": None
        if database_path is None
        else l2_quality(
            database_path,
            candles,
            _required_text(symbol, "configuration symbol"),
        ),
    }


def _history_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    history = [row for row in rows if row.get("event_type") == "regime_history"]
    violations = [
        detail for row in history if (detail := _history_violation(row)) is not None
    ]
    return {
        "rows": len(history),
        "all_ohlcv_valid": True,
        "all_non_executable": not violations,
        "authority_violation_count": len(violations),
        "authority_violations": violations,
        "regime_distribution": _distribution(
            _text_or(_payload(row).get("primary_regime"), "UNKNOWN") for row in history
        ),
    }


def _history_violation(row: Mapping[str, object]) -> dict[str, object] | None:
    payload = _payload(row)
    fields = {
        "entry_allowed": payload.get("entry_allowed"),
        "regime_admitted": payload.get("regime_admitted"),
        "long_entry": payload.get("long_entry"),
        "short_entry": payload.get("short_entry"),
        "decision_action": payload.get("decision_action"),
    }
    booleans = ("entry_allowed", "regime_admitted", "long_entry", "short_entry")
    violates = any(fields[name] is True for name in booleans)
    violates = violates or fields["decision_action"] != "history_only"
    if not violates:
        return None
    return {
        "sequence": row.get("sequence"),
        "feed_ts": payload.get("feed_ts"),
        **fields,
    }


def _decision_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    decisions = [row for row in rows if row.get("event_type") == "regime_decision"]
    payloads = [_payload(row) for row in decisions]
    return {
        "rows": len(decisions),
        "primary_regime_distribution": _distribution(
            _text_or(payload.get("primary_regime"), "UNKNOWN") for payload in payloads
        ),
        "decision_action_distribution": _distribution(
            _text_or(payload.get("decision_action"), "missing") for payload in payloads
        ),
        "exclusion_reason_distribution": _distribution(
            _text_or(payload.get("regime_reason"), "missing") for payload in payloads
        ),
        "direction_distribution": _distribution(
            _text_or(payload.get("entry_direction"), "none") for payload in payloads
        ),
        "primary_onsets": sum(
            payload.get("primary_onset") is True for payload in payloads
        ),
        "source_events": sum(
            payload.get("source_event") is True for payload in payloads
        ),
        "eligible_signals": sum(
            payload.get("entry_allowed") is True for payload in payloads
        ),
    }


def _decision_latency_summary(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    decisions = [row for row in rows if row.get("event_type") == "regime_decision"]
    timings: list[tuple[float, float, bool, object]] = []
    missing = 0
    for row in decisions:
        payload = _payload(row)
        values = (
            row.get("observed_at_utc"),
            payload.get("available_at_utc"),
            payload.get("entry_pulse_expires_at_utc"),
        )
        if any(value is None for value in values):
            missing += 1
            continue
        observed = _utc_timestamp(values[0], "decision observed_at_utc")
        available = _utc_timestamp(values[1], "decision available_at_utc")
        expires = _utc_timestamp(values[2], "entry pulse expiry")
        delay = (observed - available).total_seconds()
        pulse = (expires - available).total_seconds()
        if delay < 0.0 or pulse <= 0.0:
            raise ValueError("decision timing must have positive causal ordering")
        timings.append(
            (delay, pulse, payload.get("source_event") is True, row.get("sequence"))
        )
    delays = [item[0] for item in timings]
    pulse_values = {item[1] for item in timings}
    if len(pulse_values) > 1:
        raise ValueError("live run contains mixed entry-pulse durations")
    late = [item for item in timings if item[0] >= item[1]]
    return {
        "decision_rows": len(decisions),
        "measured_rows": len(timings),
        "rows_missing_timestamps": missing,
        "entry_pulse_seconds": next(iter(pulse_values), None),
        "minimum_seconds": round(min(delays), 6) if delays else None,
        "median_seconds": round(median(delays), 6) if delays else None,
        "maximum_seconds": round(max(delays), 6) if delays else None,
        "at_or_after_entry_pulse_rows": len(late),
        "source_events_at_or_after_entry_pulse_rows": sum(item[2] for item in late),
        "late_sequences": [item[3] for item in late],
    }


def _regime_diagnostics_summary(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    decisions = [row for row in rows if row.get("event_type") == "regime_decision"]
    diagnostics: list[tuple[str, str, bool, bool]] = []
    for row in decisions:
        payload = _payload(row)
        value = payload.get("regime_diagnostics")
        if value is None:
            continue
        detail = _diagnostic_fact(value, payload.get("primary_regime"))
        diagnostics.append(detail)
    return {
        "decision_rows": len(decisions),
        "rows_with_diagnostics": len(diagnostics),
        "rows_missing_diagnostics": len(decisions) - len(diagnostics),
        "raw_primary_distribution": _distribution(item[0] for item in diagnostics),
        "raw_confirmed_distribution": _distribution(
            f"{item[0]}->{item[1]}" for item in diagnostics
        ),
        "state_filtered_rows": sum(item[2] for item in diagnostics),
        "raw_range_rule_rows": sum(item[3] for item in diagnostics),
    }


def _diagnostic_fact(
    value: object,
    outer_primary: object,
) -> tuple[str, str, bool, bool]:
    if not isinstance(value, Mapping):
        raise ValueError("regime diagnostics must be an object")
    if value.get("authority") != "telemetry_only":
        raise ValueError("regime diagnostics must be telemetry-only")
    raw = _required_text(value.get("raw_primary"), "raw primary regime")
    confirmed = _required_text(
        value.get("confirmed_primary"), "confirmed primary regime"
    )
    if confirmed != _required_text(outer_primary, "decision primary regime"):
        raise ValueError("diagnostic confirmed regime differs from decision")
    filtered = value.get("state_filtered")
    if not isinstance(filtered, bool) or filtered != (raw != confirmed):
        raise ValueError("diagnostic state-filtered flag is inconsistent")
    rank = _optional_finite_number(value.get("adx_percentile_rank"), "ADX rank")
    threshold = _finite_number(
        value.get("adx_range_percentile_threshold"), "ADX range threshold"
    )
    return (
        raw,
        confirmed,
        filtered,
        raw == "RANGE" and rank is not None and rank < threshold,
    )


def _lifecycle_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    event_names = {
        "closes": "close",
        "faults": "fault",
        "fills": "fill",
        "funding": "funding",
        "order_acknowledgements": "order_acknowledgement",
        "order_intents": "order_intent",
        "target_orders": "target_order",
    }
    counts = Counter(str(row.get("event_type") or "") for row in rows)
    faults = [
        {
            "sequence": row.get("sequence"),
            "observed_at_utc": row.get("observed_at_utc"),
            "reason": _payload(row).get("reason"),
        }
        for row in rows
        if row.get("event_type") == "fault"
    ]
    return {
        "event_counts": {
            label: counts[event_type] for label, event_type in event_names.items()
        },
        "latest_state": _latest_payload(rows, "state_transition"),
        "latest_reconciliation": _latest_payload(rows, "reconciliation"),
        "latest_position": _latest_payload(rows, "position"),
        "faults": faults,
    }


def _latest_payload(
    rows: Sequence[Mapping[str, object]],
    event_type: str,
) -> dict[str, object] | None:
    for row in reversed(rows):
        if row.get("event_type") == event_type:
            return dict(_payload(row))
    return None


def _distribution(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _text_or(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _select_run(
    rows: Sequence[Mapping[str, object]],
    requested: str | None,
) -> tuple[str, tuple[Mapping[str, object], ...]]:
    identified = [value for row in rows if (value := row.get("run_id")) is not None]
    if not identified:
        raise ValueError("source-follow live ledger has no run identity")
    selected_id = requested or _required_text(identified[-1], "latest run_id")
    selected = tuple(row for row in rows if row.get("run_id") == selected_id)
    if not selected:
        raise ValueError(f"source-follow live run not found: {selected_id}")
    return selected_id, selected


def _configuration_identity(
    rows: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    identities = [
        row for row in rows if row.get("event_type") == "configuration_identity"
    ]
    if len(identities) != 1:
        raise ValueError("live run requires exactly one configuration_identity")
    return identities[0]


def _single_profile(rows: Sequence[Mapping[str, object]]) -> str:
    profiles = {_required_text(row.get("profile_id"), "profile_id") for row in rows}
    if len(profiles) != 1:
        raise ValueError("live run contains mixed profile identity")
    return next(iter(profiles))


def _candles(
    rows: Sequence[Mapping[str, object]],
) -> tuple[LedgerCandle, ...]:
    candles: list[LedgerCandle] = []
    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type in _CANDLE_EVENT_TYPES:
            candles.append(_ledger_candle(event_type, _payload(row)))
    timestamps = [candle.timestamp for candle in candles]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("live run contains duplicate backend candle timestamps")
    return tuple(candles)


def _ledger_candle(
    event_type: str,
    payload: Mapping[str, object],
) -> LedgerCandle:
    timestamp = _utc_timestamp(payload.get("feed_ts"), "candle feed_ts")
    if timestamp.minute % 5 or timestamp.second or timestamp.microsecond:
        raise ValueError("backend candle timestamp must be five-minute aligned")
    opening = _finite_number(payload.get("open"), "candle open")
    high = _finite_number(payload.get("high"), "candle high")
    low = _finite_number(payload.get("low"), "candle low")
    close = _finite_number(payload.get("close"), "candle close")
    volume = _finite_number(payload.get("volume"), "candle volume")
    if min(opening, high, low, close) <= 0.0 or volume < 0.0:
        raise ValueError(
            "backend candle prices must be positive and volume nonnegative"
        )
    if high < max(opening, low, close) or low > min(opening, high, close):
        raise ValueError("backend candle has inconsistent OHLC")
    return LedgerCandle(timestamp, opening, high, low, close, volume, event_type)


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("live event payload must be an object")
    return payload


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _optional_finite_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _finite_number(value, label)


def _utc_timestamp(value: object, label: str) -> datetime:
    text = _required_text(value, label)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")
    return result
