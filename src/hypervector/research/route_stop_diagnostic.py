"""All-executable-route stop and exit evidence diagnostic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_stop_recovery_sensitivity import (
    build_stop_recovery_sensitivity,
)

Record = Mapping[str, object]
_WIDTHS_BPS = (20.0, 40.0, 60.0, 80.0, 100.0, 120.0)


def build_route_stop_diagnostic(
    config: Record,
    checkpoint: Record,
    *,
    assessment_horizon_minutes: int = 15,
) -> dict[str, object]:
    """Account for every executable route using exact all-time identities."""
    _require_runtime_match(checkpoint)
    audit = _mapping(checkpoint, "audit")
    run = _mapping(audit, "run")
    route_ids = _strings(
        run.get("executable_provider_symbols"), "executable provider symbols"
    )
    provider_contracts = _provider_contracts(config)
    history = _mapping(_mapping(audit, "trade_reflections"), "all_time_live")
    closed = _records(history.get("trades"), "all-time closed trades")
    open_rows = _records(
        _mapping(audit, "open_trade_reflections").get("trades"), "open trades"
    )
    routes = {
        route_id: _route_diagnostic(
            route_id,
            provider_contracts,
            closed,
            open_rows,
            assessment_horizon_minutes,
        )
        for route_id in route_ids
    }
    return {
        "schema_version": 1,
        "mode": "v62_all_executable_route_stop_diagnostic",
        "profile": config.get("profile"),
        "profile_fingerprint": _mapping(checkpoint, "configuration_generation").get(
            "current_profile_fingerprint"
        ),
        "checkpoint_generated_at_utc": checkpoint.get("generated_at_utc"),
        "summary": _summary(routes),
        "routes": routes,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_strategy_changes": False,
            "runtime_strategy_changed": False,
        },
        "limitations": [
            "exact current route identities can have sparse all-time samples",
            "completed one-minute paths do not reproduce mark-price stop ordering",
            "possible whipsaw means post-stop entry recovery, not proven wider-stop PnL",
            "routes without protective stops remain insufficient rather than favorable",
        ],
    }


def _route_diagnostic(
    route_id: str,
    provider_contracts: Mapping[str, Record],
    closed_rows: Sequence[Record],
    open_rows: Sequence[Record],
    horizon: int,
) -> dict[str, object]:
    strategy_id, symbol = _route_parts(route_id)
    if strategy_id not in provider_contracts:
        raise ValueError(f"route provider is missing from config: {strategy_id}")
    closed = [
        row
        for row in closed_rows
        if row.get("strategy_id") == strategy_id and row.get("symbol") == symbol
    ]
    stops = [row for row in closed if row.get("exit_reason") == "protective_stop"]
    assessment = _stop_assessment(stops, horizon)
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "closed_trades": len(closed),
        "open_trades": _open_count(open_rows, strategy_id, symbol),
        "protective_stop_trades": len(stops),
        "exit_reason_counts": _exit_reason_counts(closed),
        "possible_control_whipsaws_15m": assessment["possible_whipsaws"],
        "resolved_post_stop_paths_15m": assessment["resolved_post_stop_paths"],
        "evidence_status": _evidence_status(closed, stops, assessment),
        "configured_exit_contract": dict(provider_contracts[strategy_id]),
        "stop_recovery_assessment": assessment["report"],
    }


def _stop_assessment(stops: Sequence[Record], horizon: int) -> dict[str, object]:
    if not stops:
        return {
            "possible_whipsaws": 0,
            "resolved_post_stop_paths": 0,
            "report": None,
        }
    report = build_stop_recovery_sensitivity(
        stops,
        stop_widths_bps=_WIDTHS_BPS,
        assessment_horizon_minutes=horizon,
    )
    summary = _mapping(report, "summary")
    assessment = _mapping(summary, "assessment")
    return {
        "possible_whipsaws": assessment.get("possible_control_whipsaws", 0),
        "resolved_post_stop_paths": assessment.get("post_stop_resolved_trades", 0),
        "report": report,
    }


def _evidence_status(
    closed: Sequence[Record],
    stops: Sequence[Record],
    assessment: Mapping[str, object],
) -> str:
    if not closed:
        return "insufficient_no_closed_trades"
    if not stops:
        return "insufficient_no_protective_stops"
    if assessment["resolved_post_stop_paths"] == 0:
        return "insufficient_no_resolved_post_stop_paths"
    return "protective_stop_recovery_evidence_available"


def _provider_contracts(config: Record) -> dict[str, Record]:
    output: dict[str, Record] = {}
    for provider in _records(config.get("providers"), "config providers"):
        strategy_id = _text(provider.get("strategy_id"), "provider strategy id")
        if strategy_id in output:
            raise ValueError(f"duplicate provider strategy id: {strategy_id}")
        execution = _mapping(provider, "execution")
        output[strategy_id] = execution
    return output


def _open_count(rows: Sequence[Record], strategy_id: str, symbol: str) -> int:
    count = 0
    for row in rows:
        context = row.get("current_context")
        if not isinstance(context, Mapping):
            continue
        provider = context.get("signal_provider")
        if not isinstance(provider, Mapping):
            continue
        count += (
            row.get("symbol") == symbol and provider.get("strategy_id") == strategy_id
        )
    return count


def _exit_reason_counts(rows: Sequence[Record]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = _text(row.get("exit_reason"), "exit reason")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _summary(routes: Mapping[str, Record]) -> dict[str, int]:
    values = list(routes.values())
    return {
        "executable_routes": len(values),
        "routes_with_closed_trades": sum(
            int(row["closed_trades"]) > 0 for row in values
        ),
        "routes_with_protective_stops": sum(
            int(row["protective_stop_trades"]) > 0 for row in values
        ),
        "routes_with_resolved_stop_recovery": sum(
            row["evidence_status"] == "protective_stop_recovery_evidence_available"
            for row in values
        ),
    }


def _require_runtime_match(checkpoint: Record) -> None:
    generation = _mapping(checkpoint, "configuration_generation")
    if generation.get("matches_runtime") is not True:
        raise ValueError("route diagnostic checkpoint does not match runtime config")


def _route_parts(route_id: str) -> tuple[str, str]:
    parts = route_id.rsplit("|", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"invalid executable route identity: {route_id}")
    return parts[0], parts[1]


def _mapping(source: Record, key: str) -> Record:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"route diagnostic mapping is missing: {key}")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"route diagnostic {label} must be a list of objects")
    return list(value)


def _strings(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"route diagnostic {label} must be non-empty strings")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"route diagnostic {label} must be non-empty")
    return value
