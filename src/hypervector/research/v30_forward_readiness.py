"""Read-only live-prefix readiness assessment for the fixed v30 routes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


_ROUTES: tuple[str, ...] = (
    "range_onset_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|SOL",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
)


def build_v30_forward_readiness(
    checkpoint: Mapping[str, object], candidate_path: Path
) -> dict[str, object]:
    """Extract exact v30 forward evidence without claiming counterfactual fills."""
    candidate = load_multi_asset_live_config(candidate_path, mode="observe")
    _validate_candidate_routes(candidate.executable_provider_symbols)
    audit = _mapping(checkpoint, "audit", "checkpoint")
    run = _mapping(audit, "run", "audit")
    scorecard = _mapping(audit, "strategy_scorecard", "audit")
    scores = _mapping(scorecard, "by_provider_symbol", "strategy scorecard")
    missing = sorted(set(_ROUTES).difference(scores))
    if missing:
        raise ValueError(f"missing exact v30 route scorecards: {missing}")
    routes = [_route_report(route, _route_score(scores, route)) for route in _ROUTES]
    live_state = _live_state(checkpoint, audit)
    return {
        "schema_version": "v30_live_forward_readiness_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "source_checkpoint_generated_at_utc": _text(
            checkpoint, "generated_at_utc", "checkpoint"
        ),
        "source_run": _run_identity(run),
        "candidate": _candidate_identity(candidate),
        "routes": routes,
        "live_state": live_state,
        "assessment": _assessment(routes, live_state),
    }


def _route_report(route: str, score: Mapping[str, object]) -> dict[str, object]:
    performance = _optional_mapping(score.get("execution_performance"), route)
    repeatability = _optional_mapping(score.get("repeatability_evidence"), route)
    side_performance = _optional_mapping(
        score.get("execution_performance_by_side"), route
    )
    _validate_optional_execution_fields(
        performance, repeatability, side_performance, route
    )
    return {
        "route": route,
        "forward_evaluations": _integer(score, "forward_evaluations", route),
        "eligible_signals": _integer(score, "eligible_signals", route),
        "resolved_signal_horizons": _integer(score, "resolved_signal_horizons", route),
        "forward_assessment": _text(score, "forward_assessment", route),
        "eligible_signal_horizons": dict(
            _mapping(score, "eligible_signal_horizons", route)
        ),
        "execution_performance": _execution_performance(performance, route),
        "execution_performance_by_side": dict(side_performance or {}),
        "net_pnl_excluding_largest_winner_usd": _repeatability_net(
            repeatability, route
        ),
        "repeatability_evidence_state": (
            "observed" if repeatability is not None else "no_closed_execution"
        ),
    }


def _validate_optional_execution_fields(
    performance: Mapping[str, object] | None,
    repeatability: Mapping[str, object] | None,
    side_performance: Mapping[str, object] | None,
    route: str,
) -> None:
    if performance is None and (
        repeatability is not None or side_performance is not None
    ):
        raise ValueError(f"{route} has execution detail without execution performance")
    if performance is not None and (repeatability is None or side_performance is None):
        raise ValueError(
            f"{route} closed execution is missing repeatability or side detail"
        )


def _repeatability_net(
    repeatability: Mapping[str, object] | None, route: str
) -> float | None:
    if repeatability is None:
        return None
    return _optional_number(
        repeatability.get("net_pnl_excluding_largest_winner_usd"),
        f"{route} net excluding largest winner",
    )


def _execution_performance(
    performance: Mapping[str, object] | None, route: str
) -> dict[str, object] | None:
    if performance is None:
        return None
    fields = (
        "closed_trades",
        "wins",
        "losses",
        "fees_usd",
        "funding_usd",
        "net_pnl_usd",
        "profit_factor",
    )
    missing = sorted(set(fields).difference(performance))
    if missing:
        raise ValueError(f"{route} execution performance missing fields: {missing}")
    return {field: performance[field] for field in fields}


def _live_state(
    checkpoint: Mapping[str, object], audit: Mapping[str, object]
) -> dict[str, object]:
    health = _mapping(audit, "health", "audit")
    assets = _mapping(health, "assets", "health")
    open_positions = [
        _open_position(symbol, _route_score(assets, symbol))
        for symbol in sorted(assets)
        if _text(_route_score(assets, symbol), "final_state", symbol) == "OPEN"
    ]
    return {
        "mode": _text(checkpoint, "mode", "checkpoint"),
        "transition_drain": dict(
            _mapping(checkpoint, "transition_drain", "checkpoint")
        ),
        "execution": dict(_mapping(audit, "execution", "audit")),
        "portfolio": dict(_mapping(audit, "portfolio", "audit")),
        "faults": _integer(health, "faults", "health"),
        "open_positions": open_positions,
        "all_open_positions_protected": all(
            bool(row["protected_if_open"]) for row in open_positions
        ),
    }


def _open_position(symbol: str, asset: Mapping[str, object]) -> dict[str, object]:
    return {
        "symbol": symbol,
        "position_size_signed": _number(asset, "position_size_signed", symbol),
        "protected_if_open": _boolean(asset, "protected_if_open", symbol),
        "stop_oid": asset.get("stop_oid"),
        "open_order_ids": asset.get("open_order_ids"),
    }


def _assessment(
    routes: list[dict[str, object]], live_state: Mapping[str, object]
) -> dict[str, object]:
    zero_eligible = sum(int(row["eligible_signals"]) == 0 for row in routes)
    zero_closed = sum(_closed_trades(row) == 0 for row in routes)
    negative_without_largest = sum(
        _is_negative(row.get("net_pnl_excluding_largest_winner_usd")) for row in routes
    )
    return {
        "confidence": "low",
        "routes_with_zero_eligible_signals": zero_eligible,
        "routes_with_zero_closed_trades": zero_closed,
        "routes_negative_excluding_largest_winner": negative_without_largest,
        "current_open_positions": len(list(live_state["open_positions"])),
        "candidate_active": False,
        "transition_authorized": False,
        "recommendation": "retain_v30_inactive_collect_exact_forward_evidence",
        "reason": (
            "selected route coverage is incomplete and positive exact execution "
            "depends on one SPCX winner while v25 owns protected positions"
        ),
    }


def _closed_trades(route: Mapping[str, object]) -> int:
    performance = route.get("execution_performance")
    if performance is None:
        return 0
    if not isinstance(performance, Mapping):
        raise ValueError("route execution performance must be a mapping")
    value = performance.get("closed_trades")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("closed trades must be an integer")
    return value


def _candidate_identity(candidate: object) -> dict[str, object]:
    config = candidate
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "symbols": list(config.symbols),
        "maximum_positions": config.maximum_positions,
        "executable_routes": sorted(
            f"{provider}|{symbol}"
            for provider, symbol in config.executable_provider_symbols
        ),
        "both_directions": all(
            {
                side
                for route_provider, route_symbol, side in config.executable_provider_directions
                if route_provider == provider and route_symbol == symbol
            }
            == {"long", "short"}
            for provider, symbol in config.executable_provider_symbols
        ),
    }


def _run_identity(run: Mapping[str, object]) -> dict[str, str]:
    return {
        name: _text(run, name, "run")
        for name in ("run_id", "profile_id", "profile_fingerprint")
    }


def _validate_candidate_routes(routes: frozenset[tuple[str, str]]) -> None:
    observed = {f"{provider}|{symbol}" for provider, symbol in routes}
    if observed != set(_ROUTES):
        raise ValueError(f"candidate executable routes do not match v30: {observed}")


def _mapping(
    source: Mapping[str, object], key: str, context: str
) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{context} {key} must be a string-keyed mapping")
    return value


def _route_score(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _mapping(source, key, "route collection")


def _optional_mapping(value: object, context: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} optional value must be a string-keyed mapping")
    return value


def _text(source: Mapping[str, object], key: str, context: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} {key} must be non-empty text")
    return value


def _integer(source: Mapping[str, object], key: str, context: str) -> int:
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} {key} must be an integer")
    return value


def _number(source: Mapping[str, object], key: str, context: str) -> float:
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} {key} must be numeric")
    return float(value)


def _boolean(source: Mapping[str, object], key: str, context: str) -> bool:
    value = source.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{context} {key} must be boolean")
    return value


def _optional_number(value: object, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric or null")
    return float(value)


def _is_negative(value: object) -> bool:
    return value is not None and _optional_number(value, "route sensitivity") < 0.0
