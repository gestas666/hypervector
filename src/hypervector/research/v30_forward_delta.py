"""Compare immutable v30 forward-readiness reports without execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math


Record = Mapping[str, object]
_SCHEMA = "v30_live_forward_readiness_v1"
_CONTRACT: dict[str, object] = {
    "automatic_promotion": False,
    "execution_authority": "none",
    "report_only": True,
    "runtime_strategy_changed": False,
}
_COUNTERS = (
    "forward_evaluations",
    "eligible_signals",
    "resolved_signal_horizons",
)
_PERFORMANCE_COUNTERS = ("closed_trades", "wins", "losses")
_PERFORMANCE_VALUES = ("fees_usd", "funding_usd", "net_pnl_usd")


def build_v30_forward_delta(before: Record, after: Record) -> dict[str, object]:
    """Build a strict report-only delta between comparable v30 evidence reports."""
    _validate_report_contract(before, "before")
    _validate_report_contract(after, "after")
    _require_identity(before, after)
    before_routes = _route_index(before, "before")
    after_routes = _route_index(after, "after")
    if before_routes.keys() != after_routes.keys():
        raise ValueError("v30 route identities must remain unchanged")
    route_deltas = [
        _route_delta(name, before_routes[name], after_routes[name])
        for name in sorted(before_routes)
    ]
    summary = _summary(before, after, route_deltas)
    return {
        "schema_version": "v30_live_forward_delta_v2",
        "contract": dict(_CONTRACT),
        "identity": _identity(before, after),
        "routes": route_deltas,
        "summary": summary,
        "assessment": _assessment(summary),
        "limitations": [
            "aggregate route reports cannot prove individual lifecycle immutability",
            "eligible signals and markouts are not authenticated venue fills",
            "routine evaluation growth is cadence evidence, not economic evidence",
            "this report cannot alter routes, orders, positions, sizing, or authority",
        ],
    }


def _validate_report_contract(report: Record, label: str) -> None:
    if report.get("schema_version") != _SCHEMA:
        raise ValueError(f"{label} report schema must be {_SCHEMA}")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise ValueError(f"{label} report has invalid {field}")


def _require_identity(before: Record, after: Record) -> None:
    for section_name in ("source_run", "candidate"):
        left = _mapping(before.get(section_name), f"before {section_name}")
        right = _mapping(after.get(section_name), f"after {section_name}")
        fields = (
            ("run_id", "profile_id", "profile_fingerprint")
            if section_name == "source_run"
            else (
                "profile_id",
                "profile_fingerprint",
                "executable_routes",
                "both_directions",
                "maximum_positions",
                "symbols",
            )
        )
        for field in fields:
            if left.get(field) != right.get(field):
                raise ValueError(f"{section_name} {field} changed between reports")
    before_time = _timestamp(before, "before")
    after_time = _timestamp(after, "after")
    if after_time < before_time:
        raise ValueError("after checkpoint timestamp cannot move backwards")


def _identity(before: Record, after: Record) -> dict[str, object]:
    return {
        "source_run": dict(_mapping(after.get("source_run"), "source run")),
        "candidate": dict(_mapping(after.get("candidate"), "candidate")),
        "before_checkpoint_generated_at_utc": str(
            before["source_checkpoint_generated_at_utc"]
        ),
        "after_checkpoint_generated_at_utc": str(
            after["source_checkpoint_generated_at_utc"]
        ),
    }


def _route_index(report: Record, label: str) -> dict[str, Record]:
    routes = report.get("routes")
    if not isinstance(routes, list):
        raise ValueError(f"{label} routes must be a list")
    result: dict[str, Record] = {}
    for raw in routes:
        route = _mapping(raw, f"{label} route")
        name = _text(route.get("route"), f"{label} route identity")
        if name in result:
            raise ValueError(f"{label} has duplicate route: {name}")
        result[name] = route
    return result


def _route_delta(name: str, before: Record, after: Record) -> dict[str, object]:
    result: dict[str, object] = {"route": name}
    for field in _COUNTERS:
        result[f"{_counter_label(field)}_delta"] = _monotonic_delta(
            before, after, field, name
        )
    before_performance = _optional_mapping(before.get("execution_performance"), name)
    after_performance = _optional_mapping(after.get("execution_performance"), name)
    _validate_performance_progress(before_performance, after_performance, name)
    for field in _PERFORMANCE_COUNTERS:
        result[f"{_counter_label(field)}_delta"] = _performance_delta(
            before_performance, after_performance, field, name
        )
    for field in _PERFORMANCE_VALUES:
        result[f"{field}_delta"] = _performance_value_delta(
            before_performance, after_performance, field, name
        )
    before_sides = _mapping(
        before.get("execution_performance_by_side"), f"{name} before sides"
    )
    after_sides = _mapping(
        after.get("execution_performance_by_side"), f"{name} after sides"
    )
    result["new_sides"] = sorted(after_sides.keys() - before_sides.keys())
    if result["closed_trade_delta"] == 0 and before_sides != after_sides:
        raise ValueError(f"{name} side economics changed without a new close")
    result["repeatability_net_before_usd"] = before.get(
        "net_pnl_excluding_largest_winner_usd"
    )
    result["repeatability_net_after_usd"] = after.get(
        "net_pnl_excluding_largest_winner_usd"
    )
    return result


def _validate_performance_progress(
    before: Record | None,
    after: Record | None,
    route: str,
) -> None:
    if before is not None and after is None:
        raise ValueError(f"{route} execution performance cannot disappear")
    if before is None or after is None:
        return
    closed_delta = _monotonic_delta(before, after, "closed_trades", route)
    if closed_delta == 0 and before != after:
        raise ValueError(f"{route} economics changed without a new close")


def _performance_delta(
    before: Record | None,
    after: Record | None,
    field: str,
    route: str,
) -> int:
    if before is None:
        return 0 if after is None else _nonnegative_int(after.get(field), field)
    if after is None:
        raise ValueError(f"{route} execution performance cannot disappear")
    return _monotonic_delta(before, after, field, route)


def _performance_value_delta(
    before: Record | None,
    after: Record | None,
    field: str,
    route: str,
) -> float:
    if before is None:
        return 0.0 if after is None else _number(after.get(field), field)
    if after is None:
        raise ValueError(f"{route} execution performance cannot disappear")
    return _number(after.get(field), field) - _number(before.get(field), field)


def _summary(
    before: Record,
    after: Record,
    routes: list[dict[str, object]],
) -> dict[str, object]:
    before_live = _mapping(before.get("live_state"), "before live state")
    after_live = _mapping(after.get("live_state"), "after live state")
    new_sides = [
        f"{route['route']}|{side}"
        for route in routes
        for side in _string_list(route.get("new_sides"), "new sides")
    ]
    before_faults = _nonnegative_int(before_live.get("faults"), "before faults")
    after_faults = _nonnegative_int(after_live.get("faults"), "after faults")
    if after_faults < before_faults:
        raise ValueError("live fault count cannot move backwards")
    before_open = _open_count(before_live, "before")
    after_open = _open_count(after_live, "after")
    before_transition = _transition_status(before_live, "before")
    after_transition = _transition_status(after_live, "after")
    return {
        "evaluation_delta": _sum(routes, "evaluation_delta"),
        "eligible_signal_delta": _sum(routes, "eligible_signal_delta"),
        "resolved_signal_horizon_delta": _sum(routes, "resolved_signal_horizon_delta"),
        "closed_trade_delta": _sum(routes, "closed_trade_delta"),
        "new_side_evidence": new_sides,
        "fault_delta": after_faults - before_faults,
        "protection_degraded": (
            before_live.get("all_open_positions_protected") is True
            and after_live.get("all_open_positions_protected") is not True
        ),
        "recommendation_changed": _recommendation(before) != _recommendation(after),
        "open_position_count_before": before_open,
        "open_position_count_after": after_open,
        "flat_boundary_reached": before_open > 0 and after_open == 0,
        "transition_state_changed": before_transition != after_transition,
        "transition_status_before": before_transition,
        "transition_status_after": after_transition,
    }


def _assessment(summary: Record) -> dict[str, object]:
    material = (
        any(
            _nonnegative_int(summary[field], field) > 0
            for field in (
                "eligible_signal_delta",
                "resolved_signal_horizon_delta",
                "closed_trade_delta",
                "fault_delta",
            )
        )
        or bool(summary["new_side_evidence"])
        or bool(summary["protection_degraded"])
        or bool(summary["flat_boundary_reached"])
        or bool(summary["transition_state_changed"])
    )
    journal = (
        _nonnegative_int(summary["closed_trade_delta"], "closed trade delta") > 0
        or bool(summary["new_side_evidence"])
        or int(summary["fault_delta"]) > 0
        or bool(summary["protection_degraded"])
        or bool(summary["recommendation_changed"])
        or bool(summary["flat_boundary_reached"])
        or bool(summary["transition_state_changed"])
    )
    return {
        "material_evidence_change": material,
        "journal_revision_recommended": journal,
        "automatic_transition_authorized": False,
    }


def _recommendation(report: Record) -> object:
    return _mapping(report.get("assessment"), "assessment").get("recommendation")


def _open_count(live: Record, label: str) -> int:
    positions = live.get("open_positions")
    if not isinstance(positions, list):
        raise ValueError(f"{label} open_positions must be a list")
    return len(positions)


def _transition_status(live: Record, label: str) -> str:
    transition = _mapping(live.get("transition_drain"), f"{label} transition")
    return _text(transition.get("status"), f"{label} transition status")


def _monotonic_delta(before: Record, after: Record, field: str, label: str) -> int:
    left = _nonnegative_int(before.get(field), f"{label} before {field}")
    right = _nonnegative_int(after.get(field), f"{label} after {field}")
    if right < left:
        raise ValueError(f"{label} {field} cannot move backwards")
    return right - left


def _counter_label(field: str) -> str:
    return {
        "forward_evaluations": "evaluation",
        "eligible_signals": "eligible_signal",
        "resolved_signal_horizons": "resolved_signal_horizon",
        "closed_trades": "closed_trade",
    }.get(field, field.removesuffix("s"))


def _sum(routes: list[dict[str, object]], field: str) -> int:
    return sum(_nonnegative_int(route.get(field), field) for route in routes)


def _timestamp(report: Record, label: str) -> datetime:
    raw = _text(report.get("source_checkpoint_generated_at_utc"), f"{label} timestamp")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} checkpoint timestamp is invalid: {raw}") from exc


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a string-keyed mapping")
    return value


def _optional_mapping(value: object, label: str) -> Record | None:
    return None if value is None else _mapping(value, label)


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text list")
    return value
