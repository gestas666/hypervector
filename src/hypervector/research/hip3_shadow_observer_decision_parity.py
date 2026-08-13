"""Report-only parity between HIP-3 archive and live-observer decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

_ARCHIVE_PRESSURE_SOURCE = "hyperliquid_ws_l2Book"
_LIVE_PRESSURE_SOURCE = "hyperliquid_mainnet_l2_rest"
_TIMEFRAME_MS = 15 * 60_000
_ObserverDecision = tuple[bool, str | None, float, int]
_PressureDecision = tuple[float, int]


def build_hip3_shadow_observer_decision_parity(
    *,
    signal_parity_report: Mapping[str, object],
    observer_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compare frozen archive-pressure entries with prospective live decisions."""
    scope = _validated_signal_scope(signal_parity_report)
    start_ms, end_ms = _decision_bounds(signal_parity_report)
    archive_entries = _archive_entries(signal_parity_report)
    archive_pressure = _archive_pressure(signal_parity_report)
    observed = _observer_decisions(observer_rows, scope)
    comparison = _comparison_bounds(start_ms, end_ms, observed)
    diagnostics = _diagnostics(archive_entries, archive_pressure, observed, comparison)
    archive_count = _entry_count(archive_entries, comparison)
    observer_count = _observer_entry_count(observed, comparison)
    decision_count = _decision_count(comparison)
    resolved = decision_count > 0 and not diagnostics
    return {
        "schema_version": "hip3_shadow_observer_decision_parity_v1",
        "contract": _contract(),
        "scope": scope,
        "source": {
            "archive_pressure_source": _ARCHIVE_PRESSURE_SOURCE,
            "observer_pressure_source": _LIVE_PRESSURE_SOURCE,
        },
        "coverage": {
            "archive_decision_start_ms": start_ms,
            "archive_decision_end_ms": end_ms,
            "comparison_start_ms": comparison[0],
            "comparison_end_ms": comparison[1],
        },
        "decision_diagnostics": diagnostics,
        "technical_assessment": {
            "archive_entry_events": archive_count,
            "comparison_decisions": decision_count,
            "non_vacuous_entry_comparison": archive_count + observer_count > 0,
            "observer_archive_pressure_decision_parity_resolved": resolved,
            "observer_entry_events": observer_count,
            "pressure_decision_mismatches": len(diagnostics),
        },
        "limitations": [
            "this compares entry decisions rather than fills or profitability",
            "different pressure transports remain distinct evidence sources",
            "this report grants no execution or promotion authority",
        ],
    }


def _validated_signal_scope(report: Mapping[str, object]) -> dict[str, str]:
    _require_contract(_mapping(report, "contract"))
    assessment = _mapping(report, "technical_assessment")
    if _boolean(assessment, "prospective_signal_source_parity_resolved") is not True:
        raise ValueError("signal-source parity must be resolved before observer parity")
    source = _mapping(report, "source")
    if _text(source, "pressure_source") != _ARCHIVE_PRESSURE_SOURCE:
        raise ValueError("archive pressure source identity is inconsistent")
    scope = _mapping(report, "scope")
    output = {
        "symbol": _text(scope, "symbol"),
        "provider_id": _text(scope, "provider_id"),
        "profile_id": _text(scope, "profile_id"),
        "timeframe": _text(scope, "timeframe"),
    }
    if output["timeframe"] != "15m":
        raise ValueError("observer decision parity requires 15m timeframe")
    return output


def _decision_bounds(report: Mapping[str, object]) -> tuple[int, int]:
    coverage = _mapping(report, "coverage")
    start_ms = _integer(coverage, "decision_start_ms")
    end_ms = _integer(coverage, "decision_end_ms")
    if start_ms <= 0 or end_ms < start_ms or (end_ms - start_ms) % _TIMEFRAME_MS:
        raise ValueError("archive decision window is invalid")
    return start_ms, end_ms


def _archive_entries(report: Mapping[str, object]) -> dict[int, str]:
    event_sources = _mapping(report, "reconstructed_entry_events")
    trade = _entry_map(_sequence(event_sources, "trade"))
    venue = _entry_map(_sequence(event_sources, "venue"))
    if trade != venue:
        raise ValueError("trade and venue reconstructed entries differ")
    return trade


def _entry_map(rows: Sequence[object]) -> dict[int, str]:
    output: dict[int, str] = {}
    for value in rows:
        row = _object_mapping(value, "reconstructed entry")
        decision_time = _integer(row, "decision_time_ms")
        side = _side(row.get("side"), required=True)
        if decision_time in output:
            raise ValueError("duplicate reconstructed entry decision")
        output[decision_time] = side
    return output


def _archive_pressure(report: Mapping[str, object]) -> dict[int, _PressureDecision]:
    rows = report.get("reconstructed_pressure_decisions")
    if not isinstance(rows, list):
        raise ValueError("reconstructed pressure decisions must be a list")
    output: dict[int, _PressureDecision] = {}
    for value in rows:
        row = _object_mapping(value, "reconstructed pressure decision")
        timestamp = _integer(row, "decision_time_ms")
        if not _boolean(row, "fresh"):
            raise ValueError("reconstructed pressure decision must be fresh")
        if timestamp in output:
            raise ValueError("duplicate reconstructed pressure decision")
        output[timestamp] = (
            _finite_number(row, "imbalance_10"),
            _integer(row, "last_exchange_ts_ms"),
        )
    return output


def _observer_decisions(
    rows: Sequence[Mapping[str, object]], scope: Mapping[str, str]
) -> dict[int, _ObserverDecision]:
    output: dict[int, _ObserverDecision] = {}
    for row in rows:
        _validate_observer_envelope(row)
        decision = _mapping(row, "decision")
        _validate_observer_identity(decision, scope)
        if not _boolean(decision, "pressure_state_history_complete"):
            continue
        _require_fresh_pressure(decision)
        timestamp = _integer(decision, "decision_time_ms")
        eligible = _boolean(decision, "eligible")
        side = _side(decision.get("side"), required=eligible)
        if not eligible and side is not None:
            raise ValueError("ineligible observer decision has side")
        if timestamp in output:
            raise ValueError("duplicate observer decision timestamp")
        output[timestamp] = (
            eligible,
            side,
            _finite_number(decision, "decision_imbalance_10"),
            _integer(decision, "pressure_exchange_ts_ms"),
        )
    return output


def _validate_observer_envelope(row: Mapping[str, object]) -> None:
    event_type = _text(row, "event_type")
    if not event_type.endswith("_hip3_breakout_shadow_decision"):
        raise ValueError("observer event type is inconsistent")
    if row.get("intents") != []:
        raise ValueError("observer decision must not contain intents")
    _require_contract(row)


def _validate_observer_identity(
    decision: Mapping[str, object], scope: Mapping[str, str]
) -> None:
    for name in ("symbol", "provider_id", "profile_id"):
        if _text(decision, name) != scope[name]:
            raise ValueError(f"observer {name} identity is inconsistent")
    if _text(decision, "pressure_source") != _LIVE_PRESSURE_SOURCE:
        raise ValueError("observer pressure source identity is inconsistent")
    if not _boolean(decision, "prospective"):
        raise ValueError("observer decision is not prospective")
    if _text(decision, "execution_authority") != "none":
        raise ValueError("observer decision has execution authority")


def _require_fresh_pressure(decision: Mapping[str, object]) -> None:
    if not _boolean(decision, "pressure_fresh") or not _boolean(
        decision, "pressure_scan_complete"
    ):
        raise ValueError("history-complete observer decision pressure is unresolved")


def _comparison_bounds(
    start_ms: int,
    end_ms: int,
    observed: Mapping[int, _ObserverDecision],
) -> tuple[int | None, int | None]:
    if not observed:
        return None, None
    start = max(start_ms, min(observed))
    end = min(end_ms, max(observed))
    return (None, None) if end < start else (start, end)


def _diagnostics(
    archive: Mapping[int, str],
    archive_pressure: Mapping[int, _PressureDecision],
    observed: Mapping[int, _ObserverDecision],
    bounds: tuple[int | None, int | None],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for timestamp in _decision_times(bounds):
        expected = archive.get(timestamp)
        actual = observed.get(timestamp)
        pressure = archive_pressure.get(timestamp)
        if pressure is None:
            raise ValueError("archive pressure decision coverage is incomplete")
        if actual is None:
            output.append({"decision_time_ms": timestamp, "reason": "missing_observer"})
        elif actual[:2] != (expected is not None, expected):
            output.append(
                {
                    "decision_time_ms": timestamp,
                    "reason": "entry_decision_mismatch",
                    "archive_eligible": expected is not None,
                    "archive_side": expected,
                    "archive_imbalance_10": pressure[0],
                    "archive_pressure_exchange_ts_ms": pressure[1],
                    "observer_eligible": actual[0],
                    "observer_side": actual[1],
                    "observer_imbalance_10": actual[2],
                    "observer_pressure_exchange_ts_ms": actual[3],
                }
            )
    return output


def _decision_times(bounds: tuple[int | None, int | None]) -> range:
    start, end = bounds
    if start is None or end is None:
        return range(0)
    return range(start, end + 1, _TIMEFRAME_MS)


def _decision_count(bounds: tuple[int | None, int | None]) -> int:
    return len(_decision_times(bounds))


def _entry_count(
    entries: Mapping[int, str], bounds: tuple[int | None, int | None]
) -> int:
    times = set(_decision_times(bounds))
    return sum(timestamp in times for timestamp in entries)


def _observer_entry_count(
    rows: Mapping[int, _ObserverDecision],
    bounds: tuple[int | None, int | None],
) -> int:
    times = set(_decision_times(bounds))
    return sum(timestamp in times and value[0] for timestamp, value in rows.items())


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }


def _require_contract(value: Mapping[str, object]) -> None:
    if value.get("report_only") is not True:
        raise ValueError("report-only contract is required")
    if value.get("execution_authority") != "none":
        raise ValueError("execution authority must be none")
    if value.get("runtime_strategy_changed") is not False:
        raise ValueError("runtime strategy change must be false")


def _mapping(parent: Mapping[str, object], name: str) -> Mapping[str, object]:
    return _object_mapping(parent.get(name), name)


def _object_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _sequence(parent: Mapping[str, object], name: str) -> Sequence[object]:
    value = parent.get(name)
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _text(parent: Mapping[str, object], name: str) -> str:
    value = parent.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be non-empty text")
    return value


def _integer(parent: Mapping[str, object], name: str) -> int:
    value = parent.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _boolean(parent: Mapping[str, object], name: str) -> bool:
    value = parent.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _finite_number(parent: Mapping[str, object], name: str) -> float:
    value = parent.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _side(value: object, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if value not in {"long", "short"}:
        raise ValueError("entry side must be long or short")
    return str(value)
