"""Route-level current, historical, and research evidence for exact live v39."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.research.v39_causal_challenger_program import (
    build_v39_causal_challenger_program,
)
from hypervector.research.v39_forward_evidence_contract import (
    PROFILE_FINGERPRINT,
    PROFILE_ID,
    ROUTES,
)

Record = Mapping[str, object]

_PERFORMANCE_FIELDS = (
    "closed_trades",
    "wins",
    "losses",
    "breakeven",
    "net_pnl_usd",
    "profit_factor",
    "net_pnl_excluding_largest_winner_usd",
    "fees_usd",
    "funding_usd",
)


def build_v39_route_portfolio_review(
    forward: Record,
    checkpoint: Record,
) -> dict[str, object]:
    """Join exact-run evidence to clearly labeled mixed-history diagnostics."""
    _require_forward_contract(forward)
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    source = _mapping(forward.get("source"), "forward source")
    _require_identity(source, _mapping(audit.get("run"), "checkpoint run"))
    current_routes = _exact_routes(forward)
    research = _research_routes(audit)
    history = _historical_routes(audit)
    closed_rows = _current_closed_rows(audit, _text(source.get("run_id"), "run id"))
    open_rows = _current_open_rows(audit, _text(source.get("run_id"), "run id"))
    routes = {
        route: _route_review(
            route,
            _mapping(current_routes[route], f"current route {route}"),
            history.get(route),
            _mapping(research[route], f"research route {route}"),
            closed_rows,
            open_rows,
        )
        for route in ROUTES
    }
    return {
        "schema_version": "v39_route_portfolio_review_v1",
        "mode": "exact_v39_route_evidence_review",
        "contract": _contract(),
        "source": dict(source),
        "summary": _summary(forward, routes),
        "regime_telemetry": _regime_summary(audit),
        "routes": routes,
        "causal_challenger_program": build_v39_causal_challenger_program(
            forward, checkpoint
        ),
        "portfolio_assessment": _portfolio_assessment(),
        "limitations": _limitations(),
    }


def _route_review(
    route: str,
    current: Record,
    historical: Record | None,
    research: Record,
    closed_rows: Sequence[Record],
    open_rows: Sequence[Record],
) -> dict[str, object]:
    strategy, symbol = route.split("|", 1)
    evaluations = _integer(current.get("evaluations"), "evaluations")
    eligible = _integer(current.get("eligible_evaluations"), "eligible evaluations")
    sides = _mapping(current.get("sides"), "current sides")
    opens = sum(
        _integer(_mapping(row, "side").get("open_positions"), "opens")
        for row in sides.values()
    )
    closed = _mapping(current.get("closed"), "current closed")
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "current_run": {
            "evaluations": evaluations,
            "eligible_evaluations": eligible,
            "eligible_rate_pct": _rate(eligible, evaluations),
            "closed": dict(closed),
            "sides": {
                key: dict(_mapping(value, "side")) for key, value in sides.items()
            },
            "friction": _friction(route, closed, closed_rows, open_rows),
        },
        "all_time_descriptive": _historical_record(historical),
        "research_context": _research_record(research),
        "evidence_state": _evidence_state(closed, opens, eligible),
        "scaling_interpretation": "descriptive_not_a_performance_gate",
    }


def _friction(
    route: str,
    closed: Record,
    closed_rows: Sequence[Record],
    open_rows: Sequence[Record],
) -> dict[str, object]:
    route_closed = [row for row in closed_rows if _route_identity(row) == route]
    route_open = [row for row in open_rows if _route_identity(row) == route]
    entries = [
        *_slippage_values(route_closed, "entry"),
        *_slippage_values(route_open, "entry"),
    ]
    exits = _slippage_values(route_closed, "exit")
    open_fees = sum(
        _number(
            _mapping(row.get("marked_economics"), "marked economics").get("fees_usd"),
            "open fees",
        )
        for row in route_open
    )
    return {
        "entry_slippage_bps": _distribution(entries),
        "exit_slippage_bps": _distribution(exits),
        "closed_fees_usd": _number(closed.get("fees_usd"), "closed fees"),
        "closed_funding_usd": _number(closed.get("funding_usd"), "closed funding"),
        "provisional_open_entry_fees_usd": open_fees,
        "scope": "exact_current_v39_fills_only",
    }


def _slippage_values(rows: Sequence[Record], boundary: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        raw = row.get(boundary)
        if raw is None:
            continue
        value = _mapping(raw, f"{boundary} fill").get("slippage_bps")
        if value is not None:
            values.append(_number(value, f"{boundary} slippage"))
    return values


def _distribution(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {
            "observations": 0,
            "mean": None,
            "maximum": None,
            "status": "unavailable",
        }
    return {
        "observations": len(values),
        "mean": sum(values) / len(values),
        "maximum": max(values),
        "status": "observed",
    }


def _historical_record(value: Record | None) -> dict[str, object]:
    if value is None:
        return {
            **{field: 0 for field in _PERFORMANCE_FIELDS[:4]},
            **{field: None for field in _PERFORMANCE_FIELDS[4:]},
            "scope": "no_mixed_history_route_close",
        }
    row = {field: value.get(field) for field in _PERFORMANCE_FIELDS}
    for field in _PERFORMANCE_FIELDS[:4]:
        _integer(row[field], f"historical {field}")
    for field in ("net_pnl_usd", "fees_usd", "funding_usd"):
        _number(row[field], f"historical {field}")
    row["scope"] = "all_time_mixed_contract_descriptive_only"
    return row


def _research_record(value: Record) -> dict[str, object]:
    return {
        "research_state": _text(value.get("research_state"), "research state"),
        "forward_assessment": _text(
            value.get("forward_assessment"), "forward assessment"
        ),
        "historical_summary": _text(
            value.get("historical_summary"), "historical summary"
        ),
        "confidence": _text(value.get("confidence"), "research confidence"),
        "eligible_signal_horizons": dict(
            _mapping(value.get("eligible_signal_horizons"), "signal horizons")
        ),
        "scope": "preexisting_report_only_route_context",
    }


def _summary(forward: Record, routes: Mapping[str, Record]) -> dict[str, object]:
    current = _mapping(forward.get("summary"), "forward summary")
    history = [
        _mapping(row.get("all_time_descriptive"), "route history")
        for row in routes.values()
    ]
    return {
        "provider_symbol_routes": len(routes),
        "configured_directional_scopes": _integer(
            current.get("configured_directional_scopes"), "scopes"
        ),
        "current_run_closed_trades": _integer(
            current.get("closed_trades"), "current closes"
        ),
        "current_run_net_pnl_usd": _number(current.get("net_pnl_usd"), "current net"),
        "current_run_eligible_evaluations": _integer(
            current.get("eligible_evaluations"), "eligible"
        ),
        "routes_with_current_closes": sum(
            _route_closed(row) > 0 for row in routes.values()
        ),
        "routes_with_open_positions": sum(
            _route_opens(row) > 0 for row in routes.values()
        ),
        "all_time_descriptive_closed_trades": sum(
            _integer(row.get("closed_trades"), "historical closes") for row in history
        ),
    }


def _regime_summary(audit: Record) -> dict[str, object]:
    telemetry = _mapping(audit.get("canonical_regime_telemetry"), "canonical regime")
    contract = _mapping(telemetry.get("contract"), "canonical regime contract")
    if (
        contract.get("execution_authority") != "none"
        or contract.get("intents_emitted") is not False
    ):
        raise ValueError("canonical regime telemetry is not authority-none")
    by_symbol = _mapping(telemetry.get("by_symbol"), "canonical regime symbols")
    return {
        "symbols": {
            symbol: _latest_regime(value) for symbol, value in by_symbol.items()
        },
        "authority": "report_only_no_route_gate",
    }


def _latest_regime(value: object) -> dict[str, object]:
    row = _mapping(value, "canonical symbol")
    latest_raw = row.get("latest")
    if latest_raw is None:
        return {
            "status": "unavailable",
            "evaluations": _integer(row.get("evaluations"), "regime evaluations"),
        }
    latest = _mapping(latest_raw, "latest canonical regime")
    return {
        "status": latest.get("status"),
        "evaluations": _integer(row.get("evaluations"), "regime evaluations"),
        "state_1m": latest.get("state_1m"),
        "state_5m": latest.get("state_5m"),
        "context_15m": latest.get("context_15m"),
        "primary_regime": latest.get("primary_regime"),
        "decision_time_ms": latest.get("decision_time_ms"),
    }


def _exact_routes(forward: Record) -> Record:
    routes = _mapping(forward.get("routes"), "forward routes")
    if set(routes) != set(ROUTES):
        raise ValueError("current v39 route coverage is incomplete")
    return routes


def _research_routes(audit: Record) -> Record:
    scorecard = _mapping(audit.get("strategy_scorecard"), "strategy scorecard")
    routes = _mapping(scorecard.get("by_provider_symbol"), "research routes")
    if set(routes) != set(ROUTES):
        raise ValueError("research route coverage is incomplete")
    return routes


def _historical_routes(audit: Record) -> dict[str, Record]:
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    coverage = _mapping(archive.get("coverage"), "archive coverage")
    if coverage.get("complete") is not True:
        raise ValueError("portfolio archive coverage is incomplete")
    performance = _mapping(archive.get("performance"), "archive performance")
    raw = _mapping(performance.get("by_provider_symbol"), "archive routes")
    return {
        key: _mapping(value, f"archive route {key}")
        for key, value in raw.items()
        if key in ROUTES
    }


def _current_closed_rows(audit: Record, run_id: str) -> list[Record]:
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    return [
        row
        for row in _records(reflections.get("trades"), "closed trades")
        if row.get("source_run_id") == run_id
    ]


def _current_open_rows(audit: Record, run_id: str) -> list[Record]:
    reflections = _mapping(audit.get("open_trade_reflections"), "open reflections")
    return [
        row
        for row in _records(reflections.get("trades"), "open trades")
        if row.get("source_run_id") == run_id
    ]


def _require_forward_contract(forward: Record) -> None:
    contract = _mapping(forward.get("contract"), "forward contract")
    exact = (
        contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("performance_gate") is False
    )
    if not exact:
        raise ValueError("forward evidence is not authority-none and ungated")


def _require_identity(source: Record, run: Record) -> None:
    exact = (
        source.get("profile_id") == PROFILE_ID
        and source.get("profile_fingerprint") == PROFILE_FINGERPRINT
        and source.get("run_id") == run.get("run_id")
        and run.get("profile_id") == PROFILE_ID
        and run.get("profile_fingerprint") == PROFILE_FINGERPRINT
    )
    if not exact:
        raise ValueError("v39 review runtime identity mismatch")


def _portfolio_assessment() -> dict[str, object]:
    return {
        "current_trial_state": "prospective_live_evidence_collection",
        "growth_scaling_state": "sizing_only_route_edge_not_established",
        "automatic_route_changes": False,
        "interpretation": "results inform a separately identified successor and do not mutate v39",
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "trade_count_gate": False,
        "automatic_strategy_changes": False,
        "automatic_retuning": False,
        "automatic_promotion": False,
    }


def _limitations() -> list[str]:
    return [
        "current-run evidence is exact v39 while all-time evidence mixes prior contracts",
        "eligible horizon paths are counterfactual annotations rather than executable fills",
        "open marked economics are provisional and excluded from closed results",
        "historical research context is not an automatic execution or scaling gate",
        "a five-thousand-dollar successor requires a new identity and fresh preflight",
    ]


def _evidence_state(closed: Record, opens: int, eligible: int) -> str:
    if _integer(closed.get("closed_trades"), "closed trades") > 0:
        return "resolved_current_run_close"
    if opens > 0:
        return "provisional_open_no_resolved_close"
    if eligible > 0:
        return "eligible_without_open_or_resolved_close"
    return "no_eligible_or_resolved_current_run_evidence"


def _route_identity(row: Record) -> str:
    return f"{_text(row.get('strategy_id'), 'strategy id')}|{_text(row.get('symbol'), 'symbol')}"


def _route_closed(row: Record) -> int:
    current = _mapping(row.get("current_run"), "route current")
    return _integer(
        _mapping(current.get("closed"), "route closed").get("closed_trades"), "closes"
    )


def _route_opens(row: Record) -> int:
    current = _mapping(row.get("current_run"), "route current")
    sides = _mapping(current.get("sides"), "route sides")
    return sum(
        _integer(_mapping(side, "side").get("open_positions"), "opens")
        for side in sides.values()
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator * 100.0


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
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
