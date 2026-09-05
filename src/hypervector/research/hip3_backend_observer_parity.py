"""Report-only parity between armed HIP-3 evaluations and shadow decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

Record = Mapping[str, object]
_BAR_MS = 15 * 60_000
_PRESSURE_SOURCE = "hyperliquid_mainnet_l2_rest"


@dataclass(frozen=True)
class _Decision:
    eligible: bool
    side: str | None
    decision_delay_ms: int
    imbalance_10: float
    pressure_boundary_age_ms: int
    pressure_snapshot_count: int
    pressure_history_complete: bool
    pressure_scan_complete: bool
    pressure_source: str


@dataclass(frozen=True)
class _BackendEvidence:
    decisions: dict[tuple[str, int], _Decision]
    unavailable_by_symbol: dict[str, int]
    unavailable_by_reason: dict[str, int]


def build_hip3_backend_observer_parity(
    *,
    cohort_rows: Sequence[Record],
    observer_rows_by_symbol: Mapping[str, Sequence[Record]],
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
    provider_id: str,
    symbols: tuple[str, ...],
    run_started_at_ms: int,
) -> dict[str, object]:
    """Reconcile exact current-run decisions over one common completed window."""
    _validate_scope(
        run_id, profile_id, profile_fingerprint, provider_id, symbols, run_started_at_ms
    )
    backend = _backend_decisions(
        cohort_rows, run_id, profile_id, profile_fingerprint, provider_id, symbols
    )
    observer = _observer_decisions(observer_rows_by_symbol, provider_id, symbols)
    start_ms, end_ms = _common_bounds(
        backend.decisions, observer, symbols, run_started_at_ms
    )
    diagnostics = _diagnostics(backend.decisions, observer, symbols, start_ms, end_ms)
    decisions_per_symbol = ((end_ms - start_ms) // _BAR_MS) + 1
    expected_decisions = decisions_per_symbol * len(symbols)
    return {
        "schema_version": "hip3_backend_observer_parity_v1",
        "contract": _contract(),
        "scope": _scope(run_id, profile_id, profile_fingerprint, provider_id, symbols),
        "coverage": _coverage(
            backend, observer, start_ms, end_ms, decisions_per_symbol
        ),
        "decision_diagnostics": diagnostics,
        "technical_assessment": {
            "backend_observer_decision_parity_resolved": not diagnostics,
            "expected_decisions": expected_decisions,
            "compared_decisions": _compared_count(
                backend.decisions, observer, symbols, start_ms, end_ms
            ),
            "mismatches": len(diagnostics),
        },
        "limitations": [
            "decision parity does not establish fills or profitability",
            "the compared processes may still share upstream public data defects",
            "this report grants no strategy, execution, or promotion authority",
        ],
    }


def _validate_scope(
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
    provider_id: str,
    symbols: tuple[str, ...],
    run_started_at_ms: int,
) -> None:
    if any(
        not value.strip()
        for value in (run_id, profile_id, profile_fingerprint, provider_id)
    ):
        raise ValueError("backend-observer parity requires exact text identity")
    if len(symbols) < 1 or len(set(symbols)) != len(symbols):
        raise ValueError("backend-observer parity symbols must be unique")
    if isinstance(run_started_at_ms, bool) or run_started_at_ms <= 0:
        raise ValueError("backend-observer parity run start must be positive")


def _backend_decisions(
    rows: Sequence[Record],
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
    provider_id: str,
    symbols: tuple[str, ...],
) -> _BackendEvidence:
    output: dict[tuple[str, int], _Decision] = {}
    unavailable_by_symbol: dict[str, int] = {}
    unavailable_by_reason: dict[str, int] = {}
    for row in rows:
        if row.get("event_type") != "intent_routing" or row.get("run_id") != run_id:
            continue
        _require_backend_envelope(row, profile_id, profile_fingerprint)
        for evaluation in _sequence(_mapping(row, "payload"), "evaluations"):
            value = _object(evaluation, "backend evaluation")
            if (
                value.get("strategy_id") != provider_id
                or value.get("symbol") not in symbols
            ):
                continue
            symbol = _text(value, "symbol")
            _integer(value, "decision_time_ms")
            reason = _technical_unavailability(value)
            if reason is not None:
                _increment(unavailable_by_symbol, symbol)
                _increment(unavailable_by_reason, reason)
                continue
            key = (symbol, _integer(value, "decision_time_ms"))
            _insert(output, key, _backend_decision(value))
    return _BackendEvidence(output, unavailable_by_symbol, unavailable_by_reason)


def _technical_unavailability(row: Record) -> str | None:
    if row.get("decision_action") != "technical_unavailable":
        return None
    reason = _text(row, "reason")
    readiness = _mapping(row, "readiness")
    metrics = _mapping(readiness, "metrics")
    valid = (
        row.get("eligible") is False
        and row.get("side") is None
        and row.get("backend_non_action_reason") == reason
        and readiness.get("conditions_met") == 0
        and readiness.get("conditions_required") == 1
        and readiness.get("blockers") == [reason]
        and metrics == {"technical_availability": "unavailable"}
    )
    if not valid:
        raise ValueError("backend-observer technical unavailability is malformed")
    return reason


def _observer_decisions(
    rows_by_symbol: Mapping[str, Sequence[Record]],
    provider_id: str,
    symbols: tuple[str, ...],
) -> dict[tuple[str, int], _Decision]:
    if set(rows_by_symbol) != set(symbols):
        raise ValueError("observer journals must exactly cover parity symbols")
    output: dict[tuple[str, int], _Decision] = {}
    for symbol in symbols:
        for row in rows_by_symbol[symbol]:
            _require_observer_envelope(row)
            decision = _mapping(row, "decision")
            if (
                decision.get("provider_id") != provider_id
                or decision.get("symbol") != symbol
            ):
                raise ValueError("observer decision identity is inconsistent")
            key = (symbol, _integer(decision, "decision_time_ms"))
            _insert(output, key, _observer_decision(decision))
    return output


def _common_bounds(
    backend: Mapping[tuple[str, int], _Decision],
    observer: Mapping[tuple[str, int], _Decision],
    symbols: tuple[str, ...],
    run_started_at_ms: int,
) -> tuple[int, int]:
    starts: list[int] = []
    ends: list[int] = []
    for source in (backend, observer):
        for symbol in symbols:
            times = sorted(
                time
                for coin, time in source
                if coin == symbol and time >= run_started_at_ms
            )
            if not times:
                raise ValueError(
                    f"parity source has no current-run decisions for {symbol}"
                )
            starts.append(times[0])
            ends.append(times[-1])
    start_ms, end_ms = max(starts), min(ends)
    if end_ms < start_ms or start_ms % _BAR_MS or end_ms % _BAR_MS:
        raise ValueError("backend-observer common decision window is invalid")
    return start_ms, end_ms


def _diagnostics(
    backend: Mapping[tuple[str, int], _Decision],
    observer: Mapping[tuple[str, int], _Decision],
    symbols: tuple[str, ...],
    start_ms: int,
    end_ms: int,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for symbol in symbols:
        for decision_time_ms in range(start_ms, end_ms + 1, _BAR_MS):
            key = (symbol, decision_time_ms)
            expected, actual = backend.get(key), observer.get(key)
            if expected is None and actual is None:
                output.append(_mismatch(symbol, decision_time_ms, expected, actual))
            elif expected != actual:
                output.append(_mismatch(symbol, decision_time_ms, expected, actual))
    return output


def _compared_count(
    backend: Mapping[tuple[str, int], _Decision],
    observer: Mapping[tuple[str, int], _Decision],
    symbols: tuple[str, ...],
    start_ms: int,
    end_ms: int,
) -> int:
    return sum(
        (symbol, decision_time_ms) in backend and (symbol, decision_time_ms) in observer
        for symbol in symbols
        for decision_time_ms in range(start_ms, end_ms + 1, _BAR_MS)
    )


def _mismatch(
    symbol: str,
    decision_time_ms: int,
    backend: _Decision | None,
    observer: _Decision | None,
) -> dict[str, object]:
    if backend is None and observer is None:
        return {
            "symbol": symbol,
            "decision_time_ms": decision_time_ms,
            "reason": "missing_both",
            "backend": None,
            "observer": None,
        }
    if backend is None or observer is None:
        return {
            "symbol": symbol,
            "decision_time_ms": decision_time_ms,
            "reason": "missing_backend" if backend is None else "missing_observer",
            "backend": None if backend is None else asdict(backend),
            "observer": None if observer is None else asdict(observer),
        }
    backend_values, observer_values = asdict(backend), asdict(observer)
    names = [
        name for name in backend_values if backend_values[name] != observer_values[name]
    ]
    return {
        "symbol": symbol,
        "decision_time_ms": decision_time_ms,
        "reason": "field_mismatch",
        "differing_fields": names,
        "backend": {name: backend_values[name] for name in names},
        "observer": {name: observer_values[name] for name in names},
    }


def _backend_decision(row: Record) -> _Decision:
    metrics = _mapping(_mapping(row, "readiness"), "metrics")
    return _decision(
        row,
        metrics,
        imbalance_key="imbalance_10",
        boundary_key="pressure_boundary_age_ms",
        history_key="pressure_history_complete",
    )


def _observer_decision(row: Record) -> _Decision:
    return _decision(
        row,
        row,
        imbalance_key="decision_imbalance_10",
        boundary_key="pressure_end_boundary_age_ms",
        history_key="pressure_state_history_complete",
    )


def _decision(
    identity: Record,
    metrics: Record,
    *,
    imbalance_key: str,
    boundary_key: str,
    history_key: str,
) -> _Decision:
    eligible = _boolean(identity, "eligible")
    side = _side(identity.get("side"), eligible)
    source = _text(metrics, "pressure_source")
    if source != _PRESSURE_SOURCE:
        raise ValueError("backend-observer pressure source is inconsistent")
    return _Decision(
        eligible,
        side,
        _nonnegative_integer(metrics, "decision_delay_ms"),
        _finite_number(metrics, imbalance_key),
        _nonnegative_integer(metrics, boundary_key),
        _positive_integer(metrics, "pressure_snapshot_count"),
        _boolean(metrics, history_key),
        _boolean(metrics, "pressure_scan_complete"),
        source,
    )


def _coverage(
    backend: _BackendEvidence,
    observer: Mapping[tuple[str, int], _Decision],
    start_ms: int,
    end_ms: int,
    decisions_per_symbol: int,
) -> dict[str, object]:
    return {
        "comparison_start_ms": start_ms,
        "comparison_end_ms": end_ms,
        "decisions_per_symbol": decisions_per_symbol,
        "backend_decisions": _bounded_count(backend.decisions, start_ms, end_ms),
        "observer_decisions": _bounded_count(observer, start_ms, end_ms),
        "excluded_later_backend_decisions": sum(
            key[1] > end_ms for key in backend.decisions
        ),
        "excluded_later_observer_decisions": sum(key[1] > end_ms for key in observer),
        "backend_technical_unavailable_evaluations": sum(
            backend.unavailable_by_reason.values()
        ),
        "backend_technical_unavailable_by_symbol": backend.unavailable_by_symbol,
        "backend_technical_unavailable_by_reason": backend.unavailable_by_reason,
    }


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _bounded_count(
    values: Mapping[tuple[str, int], _Decision], start_ms: int, end_ms: int
) -> int:
    return sum(start_ms <= key[1] <= end_ms for key in values)


def _scope(
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
    provider_id: str,
    symbols: tuple[str, ...],
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "profile_id": profile_id,
        "profile_fingerprint": profile_fingerprint,
        "provider_id": provider_id,
        "symbols": list(symbols),
        "timeframe": "15m",
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _require_backend_envelope(
    row: Record, profile_id: str, profile_fingerprint: str
) -> None:
    if (
        row.get("live_armed") is not True
        or row.get("profile_id") != profile_id
        or row.get("profile_fingerprint") != profile_fingerprint
    ):
        raise ValueError("backend decision envelope identity is inconsistent")


def _require_observer_envelope(row: Record) -> None:
    if (
        row.get("report_only") is not True
        or row.get("execution_authority") != "none"
        or row.get("runtime_strategy_changed") is not False
        or row.get("intents") != []
    ):
        raise ValueError("observer decision envelope authority is invalid")
    decision = _mapping(row, "decision")
    if (
        decision.get("prospective") is not True
        or decision.get("execution_authority") != "none"
    ):
        raise ValueError("observer decision is not prospective report-only evidence")


def _insert(
    output: dict[tuple[str, int], _Decision],
    key: tuple[str, int],
    value: _Decision,
) -> None:
    if key in output:
        raise ValueError(f"duplicate backend-observer decision identity: {key}")
    output[key] = value


def _side(value: object, eligible: bool) -> str | None:
    if value is None and not eligible:
        return None
    if value not in {"long", "short"} or not eligible:
        raise ValueError("backend-observer decision side is inconsistent")
    return str(value)


def _mapping(row: Record, key: str) -> Record:
    return _object(row.get(key), key)


def _object(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"backend-observer {label} must be an object")
    return value


def _sequence(row: Record, key: str) -> Sequence[object]:
    value = row.get(key)
    if not isinstance(value, list):
        raise ValueError(f"backend-observer {key} must be a list")
    return value


def _text(row: Record, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"backend-observer {key} must be text")
    return value


def _integer(row: Record, key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"backend-observer {key} must be an integer")
    return value


def _nonnegative_integer(row: Record, key: str) -> int:
    value = _integer(row, key)
    if value < 0:
        raise ValueError(f"backend-observer {key} must be nonnegative")
    return value


def _positive_integer(row: Record, key: str) -> int:
    value = _integer(row, key)
    if value <= 0:
        raise ValueError(f"backend-observer {key} must be positive")
    return value


def _boolean(row: Record, key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"backend-observer {key} must be boolean")
    return value


def _finite_number(row: Record, key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"backend-observer {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"backend-observer {key} must be finite")
    return number
