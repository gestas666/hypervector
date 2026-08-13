"""Exact-profile, execution-incapable forward evidence for live v39."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.v39_effective_episodes import (
    build_effective_episode_evidence,
)
from hypervector.research.v39_forward_evidence_contract import (
    require_exact_config,
    require_run_identity,
    validated_source,
)
from hypervector.research.v39_forward_evidence_lifecycles import (
    require_current_trade_evidence,
    validated_open_rows,
)

Record = Mapping[str, object]

_SIDES = ("long", "short")
_TOLERANCE = 1e-9


def build_v39_forward_evidence(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    *,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    """Build one exact-current-run v39 snapshot without execution authority."""
    expected = require_exact_config(config)
    _require_checkpoint_contract(
        _mapping(checkpoint.get("checkpoint_contract"), "checkpoint")
    )
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    run = _mapping(audit.get("run"), "checkpoint run")
    require_run_identity(run, config, expected)
    source = validated_source(run, checkpoint, observed_at or datetime.now(UTC))
    outcomes = _validated_outcomes(audit, expected)
    run_id = _text(run.get("run_id"), "run id")
    current = _current_run(audit, run_id, expected, config.profile_fingerprint)
    open_rows = _open_rows(audit, expected, run_id)
    episodes = build_effective_episode_evidence(
        _records(
            _mapping(audit.get("trade_reflections"), "trade reflections").get("trades"),
            "closed reflection trades",
        ),
        _records(
            _mapping(audit.get("open_trade_reflections"), "open reflections").get(
                "trades"
            ),
            "open reflection trades",
        ),
        run_id,
    )
    routes = {
        route: _route_report(route, outcomes[route], current, open_rows)
        for route in expected
    }
    _reconcile_current_total(current, routes)
    return {
        "schema_version": "v39_forward_evidence_v2",
        "mode": "exact_profile_current_run_forward_evidence",
        "contract": _contract(),
        "source": source,
        "summary": _summary(routes),
        "routes": routes,
        "effective_episode_evidence": episodes,
        "limitations": _limitations(),
    }


def _validated_outcomes(
    audit: Record,
    expected: tuple[str, ...],
) -> dict[str, Record]:
    routing = _mapping(audit.get("routing"), "audit routing")
    routed = _text_set(routing.get("executable_provider_symbols"), "routing routes")
    signal = _mapping(audit.get("signal_outcomes"), "signal outcomes")
    raw = _mapping(signal.get("by_provider_symbol"), "signal outcome routes")
    if routed != set(expected) or set(raw) != set(expected):
        raise ValueError("v39 forward evidence route coverage is incomplete")
    return {route: _mapping(raw[route], f"outcome {route}") for route in expected}


def _current_run(
    audit: Record,
    run_id: str,
    expected: tuple[str, ...],
    profile_fingerprint: str,
) -> Record:
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    _require_reflection_contract(
        _mapping(reflections.get("contract"), "trade reflections")
    )
    performance = _mapping(reflections.get("performance"), "trade performance")
    current = _mapping(performance.get("current_run"), "current run performance")
    if _text(current.get("run_id"), "performance run id") != run_id:
        raise ValueError("current-run performance identity does not match runtime")
    routes = _mapping(current.get("by_provider_symbol"), "current-run routes")
    if not set(routes).issubset(expected):
        raise ValueError("current-run performance contains a non-v39 route")
    require_current_trade_evidence(
        reflections, current, expected, run_id, profile_fingerprint
    )
    return current


def _open_rows(
    audit: Record,
    expected: tuple[str, ...],
    run_id: str,
) -> dict[tuple[str, str], tuple[Record, ...]]:
    section = _mapping(audit.get("open_trade_reflections"), "open reflections")
    _require_reflection_contract(_mapping(section.get("contract"), "open reflections"))
    return validated_open_rows(section, expected, run_id)


def _route_report(
    route: str,
    outcome: Record,
    current: Record,
    opens: Mapping[tuple[str, str], tuple[Record, ...]],
) -> dict[str, object]:
    current_routes = _mapping(current.get("by_provider_symbol"), "current-run routes")
    closed = _missing_mapping(current_routes.get(route), f"current-run route {route}")
    by_side = _missing_mapping(closed.get("by_side"), "by-side performance")
    if not set(by_side).issubset(_SIDES):
        raise ValueError(f"current-run route contains an invalid side: {route}")
    evaluations, eligible, signal_sides = _signal_counts(outcome)
    sides = {
        side: _side_report(
            _missing_mapping(by_side.get(side), f"{route} {side} performance"),
            opens.get((route, side), ()),
            signal_sides[side],
        )
        for side in _SIDES
    }
    closed_record = _performance_record(closed)
    _reconcile_route_sides(route, closed_record, sides)
    return {
        "strategy_id": route.split("|", 1)[0],
        "symbol": route.split("|", 1)[1],
        "evaluations": evaluations,
        "eligible_evaluations": eligible,
        "closed": closed_record,
        "sides": sides,
        "evidence_scope": "exact_profile_current_process_run",
    }


def _signal_counts(
    outcome: Record,
) -> tuple[int, int, dict[str, Record]]:
    evaluations = _nonnegative_integer(outcome.get("evaluations"), "evaluations")
    eligible = _nonnegative_integer(
        outcome.get("eligible_evaluations"), "eligible evaluations"
    )
    no_direction = _nonnegative_integer(outcome.get("no_direction"), "no direction")
    raw = _mapping(outcome.get("by_side"), "directional signal outcomes")
    if set(raw) != set(_SIDES):
        raise ValueError("directional signal outcomes require long and short")
    sides = {side: _signal_side(raw[side], side) for side in _SIDES}
    side_evaluations = sum(
        _integer(row["evaluations"], "evaluations") for row in sides.values()
    )
    side_eligible = sum(
        _integer(row["eligible_evaluations"], "eligible") for row in sides.values()
    )
    if eligible > evaluations or side_eligible != eligible:
        raise ValueError("eligible evaluations exceed evaluations or do not reconcile")
    if side_evaluations + no_direction != evaluations:
        raise ValueError("directional evaluations do not reconcile")
    return evaluations, eligible, sides


def _signal_side(value: object, side: str) -> Record:
    row = _mapping(value, f"{side} signal outcomes")
    evaluations = _nonnegative_integer(row.get("evaluations"), "side evaluations")
    eligible = _nonnegative_integer(
        row.get("eligible_evaluations"), "side eligible evaluations"
    )
    if eligible > evaluations:
        raise ValueError("side eligible evaluations exceed evaluations")
    return {"evaluations": evaluations, "eligible_evaluations": eligible}


def _side_report(
    performance: Record,
    opens: tuple[Record, ...],
    signals: Record,
) -> dict[str, object]:
    marked = sum(
        _number(
            _mapping(row.get("marked_economics"), "open marked economics").get(
                "active_lifecycle_marked_net_pnl_usd"
            ),
            "open marked PnL",
        )
        for row in opens
    )
    return {
        **_performance_record(performance),
        "signal_evaluations": _integer(signals.get("evaluations"), "side evaluations"),
        "eligible_signal_evaluations": _integer(
            signals.get("eligible_evaluations"), "side eligible evaluations"
        ),
        "open_positions": len(opens),
        "open_marked_pnl_usd": marked,
        "open_pnl_status": "provisional",
    }


def _performance_record(value: Record) -> dict[str, object]:
    if not value:
        return _empty_performance()
    record = {
        "closed_trades": _nonnegative_integer(value.get("closed_trades"), "closes"),
        "wins": _nonnegative_integer(value.get("wins"), "wins"),
        "losses": _nonnegative_integer(value.get("losses"), "losses"),
        "breakeven": _nonnegative_integer(value.get("breakeven"), "breakeven"),
        "net_pnl_usd": _number(value.get("net_pnl_usd"), "net PnL"),
        "fees_usd": _nonnegative_number(value.get("fees_usd"), "fees_usd"),
        "funding_usd": _number(value.get("funding_usd"), "funding"),
        "entry_margin_used_usd": _nonnegative_number(
            value.get("entry_margin_used_usd"), "entry_margin_used_usd"
        ),
        "net_return_on_margin_pct": _optional_number(
            value.get("net_return_on_margin_pct")
        ),
        "profit_factor": _optional_number(value.get("profit_factor")),
        "net_pnl_excluding_largest_winner_usd": _optional_number(
            value.get("net_pnl_excluding_largest_winner_usd")
        ),
        "maximum_closed_sequence_drawdown_usd": _nonnegative_number(
            value.get("maximum_closed_sequence_drawdown_usd"),
            "maximum_closed_sequence_drawdown_usd",
        ),
    }
    _require_trade_count_identity(record)
    if record["closed_trades"] and record["net_return_on_margin_pct"] is None:
        raise ValueError("return on margin is required for completed trades")
    return record


def _require_trade_count_identity(record: Record) -> None:
    closed = _integer(record.get("closed_trades"), "closes")
    outcomes = sum(
        _integer(record.get(field), field) for field in ("wins", "losses", "breakeven")
    )
    if outcomes != closed:
        raise ValueError("trade counts do not reconcile")


def _reconcile_route_sides(
    route: str,
    closed: Record,
    sides: Mapping[str, Record],
) -> None:
    side_rows = [_mapping(value, f"{route} side") for value in sides.values()]
    for field in ("closed_trades", "wins", "losses", "breakeven"):
        if _integer(closed.get(field), field) != sum(
            _integer(row.get(field), field) for row in side_rows
        ):
            raise ValueError(f"route sides do not reconcile: {route} {field}")
    for field in ("net_pnl_usd", "fees_usd", "funding_usd", "entry_margin_used_usd"):
        observed = sum(_number(row.get(field), field) for row in side_rows)
        if not math.isclose(
            _number(closed.get(field), field), observed, abs_tol=_TOLERANCE
        ):
            raise ValueError(f"route sides do not reconcile: {route} {field}")


def _empty_performance() -> dict[str, object]:
    return {
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "net_pnl_usd": 0.0,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "entry_margin_used_usd": 0.0,
        "net_return_on_margin_pct": None,
        "profit_factor": None,
        "net_pnl_excluding_largest_winner_usd": None,
        "maximum_closed_sequence_drawdown_usd": 0.0,
    }


def _reconcile_current_total(
    current: Record,
    routes: Mapping[str, Record],
) -> None:
    total = _performance_record(_mapping(current.get("total"), "current-run total"))
    route_closed = [
        _mapping(route.get("closed"), "route closed") for route in routes.values()
    ]
    for field in ("closed_trades", "wins", "losses", "breakeven"):
        if total[field] != sum(_integer(row[field], field) for row in route_closed):
            raise ValueError(f"current-run total does not reconcile: {field}")
    for field in ("net_pnl_usd", "fees_usd", "funding_usd", "entry_margin_used_usd"):
        observed = sum(_number(row[field], field) for row in route_closed)
        if not math.isclose(_number(total[field], field), observed, abs_tol=_TOLERANCE):
            raise ValueError(f"current-run total does not reconcile: {field}")


def _summary(routes: Mapping[str, Record]) -> dict[str, object]:
    closed = [
        _mapping(route.get("closed"), "route closed") for route in routes.values()
    ]
    return {
        "provider_symbol_routes": len(routes),
        "configured_directional_scopes": len(routes) * len(_SIDES),
        "directional_scopes_with_evaluations": sum(
            _integer(side.get("signal_evaluations"), "side evaluations") > 0
            for route in routes.values()
            for side in _mapping(route.get("sides"), "route sides").values()
        ),
        "evaluated_routes": sum(
            _integer(route.get("evaluations"), "evaluations") > 0
            for route in routes.values()
        ),
        "eligible_evaluations": sum(
            _integer(route.get("eligible_evaluations"), "eligible")
            for route in routes.values()
        ),
        "closed_trades": sum(
            _integer(row.get("closed_trades"), "closes") for row in closed
        ),
        "wins": sum(_integer(row.get("wins"), "wins") for row in closed),
        "losses": sum(_integer(row.get("losses"), "losses") for row in closed),
        "breakeven": sum(_integer(row.get("breakeven"), "breakeven") for row in closed),
        "net_pnl_usd": sum(
            _number(row.get("net_pnl_usd"), "net PnL") for row in closed
        ),
        "fees_usd": sum(_number(row.get("fees_usd"), "fees") for row in closed),
        "funding_usd": sum(
            _number(row.get("funding_usd"), "funding") for row in closed
        ),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "automatic_retuning": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "trade_count_gate": False,
        "open_marks_are_provisional": True,
    }


def _limitations() -> list[str]:
    return [
        "this report contains only the exact current backend process run",
        "zero trades is explicit absence of evidence rather than neutral edge",
        "open marked PnL is provisional and excluded from closed economics",
        "a backend restart is a process boundary, not statistical independence",
        "no result can route, resize, pause, retune, promote, or submit an order",
    ]


def _require_checkpoint_contract(contract: Record) -> None:
    _require_authority_none_contract(contract)
    required_false = (
        "performance_gate",
        "automatic_retuning",
        "automatic_pause",
        "balance_gate",
        "final",
    )
    if any(contract.get(field) is not False for field in required_false):
        raise ValueError("checkpoint source contract is not explicitly non-mutating")


def _require_reflection_contract(contract: Record) -> None:
    _require_authority_none_contract(contract)
    if contract.get("automatic_strategy_changes") is not False:
        raise ValueError("reflection source contract is not explicitly non-mutating")


def _require_authority_none_contract(contract: Record) -> None:
    exact = (
        contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("runtime_strategy_changed") is False
    )
    if not exact:
        raise ValueError("evidence source contract is not authority-none")


def _route_identity(row: Record) -> str:
    return f"{_text(row.get('strategy_id'), 'strategy id')}|{_text(row.get('symbol'), 'symbol')}"


def _side(value: object) -> str:
    side = _text(value, "side")
    if side not in _SIDES:
        raise ValueError("side must be long or short")
    return side


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return tuple(value)


def _missing_mapping(value: object, label: str) -> Record:
    return {} if value is None else _mapping(value, label)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_set(value: object, label: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text array")
    unique = set(value)
    if len(unique) != len(value):
        raise ValueError(f"{label} contains duplicate route identity")
    return unique


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    result = _integer(value, label)
    if result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _optional_number(value: object) -> float | None:
    return None if value is None else _number(value, "optional numeric value")
