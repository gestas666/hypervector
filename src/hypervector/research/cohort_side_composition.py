"""Report-only composition of separate long and short portfolio mechanisms."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from hypervector.research.cohort_successor_triage import (
    _mapping,
    _nonnegative_integer,
    _number,
    _optional_mapping,
    _optional_number,
    _side_assessment,
    _text,
    _validate_report_only,
)

_SIDES = ("long", "short")
_MIN_REPEATED_TRADES = 5
_FRONTIER_MIN_PRIORITY = 2
_TIER_PRIORITY = {
    "nonpositive_mixed_profile": 0,
    "unobserved_live": 1,
    "historical_supportive_no_live": 2,
    "positive_sparse_mixed_profile": 3,
    "repeated_positive_mixed_profile": 4,
}


def build_side_composition(audit: Mapping[str, object]) -> dict[str, object]:
    """Rank provider-symbol-side mechanisms without granting runtime authority."""
    source = _mapping(audit, "cohort audit")
    experiment = _mapping(source.get("experiment_contract"), "experiment contract")
    scorecard = _mapping(source.get("strategy_scorecard"), "strategy scorecard")
    alignment = _mapping(
        source.get("entry_alignment_mechanism"), "entry alignment mechanism"
    )
    _validate_report_only(experiment, "experiment contract")
    _validate_report_only(
        _mapping(scorecard.get("contract"), "scorecard contract"),
        "scorecard contract",
    )
    _validate_alignment_contract(alignment)
    scope = _text(alignment.get("scope"), "alignment scope")
    if scope != "all_live_history_mixed_profiles":
        raise ValueError(
            "entry alignment scope must be all_live_history_mixed_profiles"
        )
    records = _mapping(scorecard.get("by_provider_symbol"), "scorecard routes")
    histories = _mapping(
        alignment.get("by_provider_symbol_side"), "side alignment records"
    )
    retired = _retired_history_components(records, histories, scope)
    components = _build_components(records, histories, scope)
    frontier = {side: _frontier(components, side) for side in _SIDES}
    return {
        "schema_version": 2,
        "mode": "cohort_separate_side_composition",
        "contract": _contract(),
        "source": _source_identity(_mapping(source.get("run"), "audit run"), scope),
        "summary": _summary(components, frontier, len(retired)),
        "frontier": frontier,
        "components": components,
        "retired_history_components": retired,
    }


def _build_components(
    records: Mapping[str, object],
    histories: Mapping[str, object],
    scope: str,
) -> dict[str, object]:
    identities = _component_identities(records, histories)
    output: dict[str, object] = {}
    for component, (route_key, side) in sorted(identities.items()):
        route = _mapping(records.get(route_key), f"route {route_key}")
        strategy, symbol = _route_identity(route_key, route)
        historical = _historical_side(route, side)
        route_state = _text(route.get("research_state"), "route research state")
        live = _live_history(histories.get(component), component, side, scope)
        current = _current_profile_execution(route, side)
        tier = _evidence_tier(historical, live)
        output[component] = {
            "strategy_id": strategy,
            "symbol": symbol,
            "side": side,
            "historical_side_assessment": historical,
            "route_research_state": route_state,
            "live_history": live,
            "current_profile_execution": current,
            "evidence_tier": tier,
            "priority": _TIER_PRIORITY[tier],
            "evidence_tension": _evidence_tension(historical, route_state, live),
            "execution_effect": "report_only",
        }
    return output


def _component_identities(
    records: Mapping[str, object], histories: Mapping[str, object]
) -> dict[str, tuple[str, str]]:
    identities: dict[str, tuple[str, str]] = {}
    for route_key, raw in records.items():
        route = _mapping(raw, f"route {route_key}")
        _route_identity(route_key, route)
        directional = _optional_mapping(route.get("directional_research"))
        current = _optional_mapping(route.get("execution_performance_by_side"))
        for side in set(directional).union(current):
            _validate_side(side)
            identities[f"{route_key}|{side}"] = (route_key, side)
    for component in histories:
        route_key, side = _split_component(component)
        if route_key in records:
            identities[component] = (route_key, side)
    return identities


def _retired_history_components(
    records: Mapping[str, object], histories: Mapping[str, object], scope: str
) -> list[str]:
    """Validate and disclose mixed-profile histories absent from the current roster."""
    retired: list[str] = []
    for component, raw in histories.items():
        route_key, side = _split_component(component)
        if route_key in records:
            continue
        _live_history(raw, component, side, scope)
        retired.append(component)
    return sorted(retired)


def _route_identity(key: str, route: Mapping[str, object]) -> tuple[str, str]:
    strategy = _text(route.get("strategy_id"), "strategy_id")
    symbol = _text(route.get("symbol"), "symbol")
    if key != f"{strategy}|{symbol}":
        raise ValueError(f"route identity mismatch: {key}")
    return strategy, symbol


def _split_component(value: str) -> tuple[str, str]:
    try:
        route_key, side = value.rsplit("|", 1)
    except ValueError as exc:
        raise ValueError(f"invalid side component identity: {value}") from exc
    _validate_side(side)
    return route_key, side


def _validate_side(side: str) -> None:
    if side not in _SIDES:
        raise ValueError("side must be long or short")


def _historical_side(route: Mapping[str, object], side: str) -> str:
    directional = _optional_mapping(route.get("directional_research"))
    raw = directional.get(side)
    if raw is None:
        return "unavailable"
    state = _text(_mapping(raw, f"{side} research").get("research_state"), "side state")
    return _side_assessment(state)


def _live_history(
    raw: object, component: str, side: str, scope: str
) -> dict[str, object]:
    if raw is None:
        return _empty_economics(scope)
    record = _mapping(raw, f"side history {component}")
    if _text(record.get("side"), "history side") != side:
        raise ValueError(f"side history identity mismatch: {component}")
    outcome = _mapping(record.get("outcome"), "side history outcome")
    economics = _outcome_economics(outcome, scope)
    closed = _nonnegative_integer(record.get("closed_trades"), "history closed trades")
    if economics["trades"] != closed:
        raise ValueError(f"side history trade count mismatch: {component}")
    return economics


def _outcome_economics(outcome: Mapping[str, object], scope: str) -> dict[str, object]:
    trades = _nonnegative_integer(outcome.get("trades"), "outcome trades")
    wins = _nonnegative_integer(outcome.get("wins"), "outcome wins")
    losses = _nonnegative_integer(outcome.get("losses"), "outcome losses")
    breakeven = _nonnegative_integer(outcome.get("breakeven"), "outcome breakeven")
    if wins + losses + breakeven != trades:
        raise ValueError("side outcome counts do not reconcile")
    return {
        "available": True,
        "scope": scope,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "net_pnl_usd": _number(outcome.get("net_pnl_usd"), "outcome net PnL"),
        "usd_profit_factor": _optional_number(outcome.get("usd_profit_factor")),
        "normalized_profit_factor": _optional_number(
            outcome.get("normalized_profit_factor")
        ),
        "mean_return_on_margin_pct": _optional_number(
            outcome.get("mean_net_return_on_margin_pct")
        ),
        "median_return_on_margin_pct": _optional_number(
            outcome.get("median_net_return_on_margin_pct")
        ),
    }


def _current_profile_execution(
    route: Mapping[str, object], side: str
) -> dict[str, object]:
    if route.get("execution_outcomes_identifiable") is not True:
        return _empty_economics("current_profile_provider_execution_contract_history")
    raw = _optional_mapping(route.get("execution_performance_by_side")).get(side)
    if raw is None:
        return _empty_economics("current_profile_provider_execution_contract_history")
    value = _mapping(raw, f"current {side} execution")
    trades = _nonnegative_integer(value.get("closed_trades"), "current trades")
    wins = _nonnegative_integer(value.get("wins"), "current wins")
    losses = _nonnegative_integer(value.get("losses"), "current losses")
    breakeven = _nonnegative_integer(value.get("breakeven"), "current breakeven")
    if wins + losses + breakeven != trades:
        raise ValueError("current side execution counts do not reconcile")
    return {
        "available": True,
        "scope": "current_profile_provider_execution_contract_history",
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "net_pnl_usd": _number(value.get("net_pnl_usd"), "current net PnL"),
        "usd_profit_factor": _optional_number(value.get("profit_factor")),
        "normalized_profit_factor": None,
        "fees_usd": _number(value.get("fees_usd"), "current fees"),
        "funding_usd": _number(value.get("funding_usd"), "current funding"),
    }


def _empty_economics(scope: str) -> dict[str, object]:
    return {
        "available": False,
        "scope": scope,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "net_pnl_usd": 0.0,
        "usd_profit_factor": None,
        "normalized_profit_factor": None,
    }


def _evidence_tier(historical: str, live: Mapping[str, object]) -> str:
    trades = _nonnegative_integer(live.get("trades"), "live history trades")
    if trades == 0:
        return (
            "historical_supportive_no_live"
            if historical == "supportive"
            else "unobserved_live"
        )
    net = _number(live.get("net_pnl_usd"), "live history net PnL")
    if net <= 0.0:
        return "nonpositive_mixed_profile"
    profit_factor = _optional_number(live.get("normalized_profit_factor"))
    median = _optional_number(live.get("median_return_on_margin_pct"))
    if (
        trades >= _MIN_REPEATED_TRADES
        and profit_factor is not None
        and profit_factor > 1.0
        and median is not None
        and median > 0.0
    ):
        return "repeated_positive_mixed_profile"
    return "positive_sparse_mixed_profile"


def _evidence_tension(
    historical: str, route_state: str, live: Mapping[str, object]
) -> bool:
    positive = _number(live.get("net_pnl_usd"), "live history net PnL") > 0.0
    historical_conflict = historical in {"adverse", "contradictory"}
    route_conflict = any(
        marker in route_state.lower()
        for marker in ("negative", "rejected", "falsified", "contradictory")
    )
    return positive and (historical_conflict or route_conflict)


def _frontier(components: Mapping[str, object], side: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, raw in components.items():
        value = _mapping(raw, f"component {key}")
        if value.get("side") != side:
            continue
        priority = _nonnegative_integer(value.get("priority"), "component priority")
        if priority < _FRONTIER_MIN_PRIORITY:
            continue
        live = _mapping(value.get("live_history"), "live history")
        rows.append(
            {
                "component": key,
                "priority": priority,
                "evidence_tier": value.get("evidence_tier"),
                "evidence_tension": value.get("evidence_tension"),
                "trades": live.get("trades"),
                "net_pnl_usd": live.get("net_pnl_usd"),
                "usd_profit_factor": live.get("usd_profit_factor"),
                "normalized_profit_factor": live.get("normalized_profit_factor"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -int(row["priority"]),
            -int(row["trades"]),
            -float(row["net_pnl_usd"]),
            str(row["component"]),
        ),
    )


def _summary(
    components: Mapping[str, object],
    frontier: Mapping[str, list[dict[str, object]]],
    retired_history_components: int,
) -> dict[str, object]:
    tiers = Counter(
        _text(_mapping(value, "component").get("evidence_tier"), "evidence tier")
        for value in components.values()
    )
    return {
        "components": len(components),
        "long_frontier_components": len(frontier["long"]),
        "short_frontier_components": len(frontier["short"]),
        "both_side_frontier_available": bool(frontier["long"] and frontier["short"]),
        "retired_history_components": retired_history_components,
        "evidence_tiers": dict(sorted(tiers.items())),
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _source_identity(run: Mapping[str, object], scope: str) -> dict[str, object]:
    return {
        "run_id": _text(run.get("run_id"), "run_id"),
        "profile_id": _text(run.get("profile_id"), "profile_id"),
        "profile_fingerprint": _text(
            run.get("profile_fingerprint"), "profile fingerprint"
        ),
        "as_of_utc": _text(run.get("last_observed_at_utc"), "last observed time"),
        "live_history_scope": scope,
    }


def _validate_alignment_contract(alignment: Mapping[str, object]) -> None:
    contract = _mapping(alignment.get("contract"), "entry alignment contract")
    _validate_report_only(contract, "entry alignment contract")
    if contract.get("execution_gate") is True:
        raise ValueError("entry alignment contract cannot contain an execution gate")
    if contract.get("automatic_strategy_changes") is True:
        raise ValueError("entry alignment contract cannot change a strategy")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "ranking_only": True,
        "descriptive_tier_profit_factor_basis": "normalized_profit_factor",
        "minimum_repeated_trades_for_descriptive_tier": _MIN_REPEATED_TRADES,
        "mixed_profile_history_is_not_current_profile_edge": True,
    }
