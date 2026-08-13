"""Report-only, side-aware triage for cohort successor research."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

_ADVERSE_MARKERS = ("negative", "rejected", "falsified")
_CONTRADICTORY_MARKERS = ("contradictory", "unstable", "unresolved", "observer")
_SUPPORTIVE_MARKERS = ("candidate", "positive")
_SIDES = frozenset({"long", "short"})


def build_successor_triage(audit: Mapping[str, object]) -> dict[str, object]:
    """Build a non-executable successor triage from one immutable audit."""
    source = _mapping(audit, "cohort audit")
    experiment = _mapping(source.get("experiment_contract"), "experiment contract")
    scorecard = _mapping(source.get("strategy_scorecard"), "strategy scorecard")
    _validate_report_only(experiment, "experiment contract")
    _validate_report_only(
        _mapping(scorecard.get("contract"), "scorecard contract"),
        "scorecard contract",
    )
    open_section = _mapping(
        source.get("open_trade_reflections"), "open trade reflections"
    )
    _validate_report_only(
        _mapping(open_section.get("contract"), "open trade contract"),
        "open trade contract",
    )
    records = _mapping(scorecard.get("by_provider_symbol"), "scorecard routes")
    opens = _open_by_route(open_section.get("trades"))
    routes = {
        key: _route_record(key, _mapping(value, f"route {key}"), opens.get(key, ()))
        for key, value in sorted(records.items())
    }
    run = _mapping(source.get("run"), "audit run")
    return {
        "schema_version": 1,
        "mode": "cohort_successor_triage",
        "contract": _contract(),
        "source": _source_identity(run),
        "summary": _summary(routes),
        "routes": routes,
    }


def _route_record(
    key: str,
    record: Mapping[str, object],
    opens: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    strategy_id = _text(record.get("strategy_id"), "strategy_id")
    symbol = _text(record.get("symbol"), "symbol")
    if key != f"{strategy_id}|{symbol}":
        raise ValueError(f"route identity mismatch: {key}")
    state = _text(record.get("research_state"), "research_state")
    sides = _side_assessments(record.get("directional_research"))
    historical = _historical_assessment(state, sides)
    live = _live_translation(record)
    repeatability = _optional_mapping(record.get("repeatability_evidence"))
    horizons = _optional_mapping(record.get("eligible_signal_horizons"))
    triage, experiment = _decision(historical, sides, live, repeatability, horizons)
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "research_state": state,
        "confidence": record.get("confidence"),
        "historical_assessment": historical,
        "side_assessments": sides,
        "live_translation": live,
        "cost_survival": _cost_survival(live),
        "concentration": _concentration(repeatability),
        "forward_path_evidence": _forward_summary(horizons),
        "provisional_open": _provisional_open(opens),
        "triage": triage,
        "next_experiment": experiment,
        "execution_effect": "report_only",
    }


def _historical_assessment(state: str, sides: Mapping[str, str]) -> str:
    if "side_timing_set_falsified" in state.lower():
        return "tested_side_timing_set_falsified"
    if "side_relation_set_falsified" in state.lower():
        return "tested_side_relation_set_falsified"
    if _contains(state, _ADVERSE_MARKERS):
        return "adverse_exact_contract"
    if _contains(state, _CONTRADICTORY_MARKERS) or any(
        value in {"adverse", "contradictory"} for value in sides.values()
    ):
        return "directionally_contradictory"
    if _contains(state, _SUPPORTIVE_MARKERS):
        return "supportive_candidate"
    return "unresolved_or_unreviewed"


def _side_assessments(value: object) -> dict[str, str]:
    records = _optional_mapping(value)
    if not set(records).issubset(_SIDES):
        raise ValueError("directional research sides must be long or short")
    return {
        side: _side_assessment(
            _text(
                _mapping(record, f"{side} research").get("research_state"), "side state"
            )
        )
        for side, record in sorted(records.items())
    }


def _side_assessment(state: str) -> str:
    if _contains(state, _ADVERSE_MARKERS):
        return "adverse"
    if _contains(state, _CONTRADICTORY_MARKERS):
        return "contradictory"
    if _contains(state, _SUPPORTIVE_MARKERS):
        return "supportive"
    return "unresolved"


def _live_translation(record: Mapping[str, object]) -> dict[str, object]:
    if record.get("execution_outcomes_identifiable") is not True:
        return _empty_live_translation()
    performance = _mapping(record.get("execution_performance"), "execution performance")
    closed = _nonnegative_integer(performance.get("closed_trades"), "closed trades")
    sides = _optional_mapping(record.get("execution_performance_by_side"))
    if not set(sides).issubset(_SIDES):
        raise ValueError("execution sides must be long or short")
    observed = sorted(
        side
        for side, value in sides.items()
        if _nonnegative_integer(
            _mapping(value, f"{side} execution").get("closed_trades"),
            f"{side} closed trades",
        )
        > 0
    )
    return {
        "closed_trades": closed,
        "wins": _nonnegative_integer(performance.get("wins"), "wins"),
        "losses": _nonnegative_integer(performance.get("losses"), "losses"),
        "breakeven": _nonnegative_integer(performance.get("breakeven"), "breakeven"),
        "net_pnl_usd": _number(performance.get("net_pnl_usd"), "net PnL"),
        "profit_factor": _optional_number(performance.get("profit_factor")),
        "fees_usd": _number(performance.get("fees_usd"), "fees"),
        "funding_usd": _number(performance.get("funding_usd"), "funding"),
        "observed_sides": observed,
        "after_cost": True,
    }


def _decision(
    historical: str,
    sides: Mapping[str, str],
    live: Mapping[str, object],
    repeatability: Mapping[str, object],
    horizons: Mapping[str, object],
) -> tuple[str, str]:
    if historical in {
        "tested_side_timing_set_falsified",
        "tested_side_relation_set_falsified",
    }:
        return "REVISE", "new_side_mechanic_version_required"
    if historical == "adverse_exact_contract":
        return "STOP", "new_mechanic_version_required"
    if historical == "directionally_contradictory":
        return "REVISE", "separate_long_short_mechanisms"
    if historical != "supportive_candidate":
        return "REVISE", "establish_source_backed_mechanism"
    if set(sides) != _SIDES or set(sides.values()) != {"supportive"}:
        return "REVISE", "collect_side_specific_evidence"
    if set(_string_list(live.get("observed_sides"), "observed sides")) != _SIDES:
        return "REVISE", "collect_both_side_live_execution"
    if not _positive_live_result(live, repeatability, horizons):
        return "REVISE", "diagnose_signal_cost_or_concentration"
    return "PROCEED", "shared_portfolio_interaction_replay"


def _positive_live_result(
    live: Mapping[str, object],
    repeatability: Mapping[str, object],
    horizons: Mapping[str, object],
) -> bool:
    profit_factor = _optional_number(live.get("profit_factor"))
    ex_largest = repeatability.get("net_pnl_excluding_largest_winner_usd")
    return (
        _number(live.get("net_pnl_usd"), "live net PnL") > 0.0
        and profit_factor is not None
        and profit_factor > 1.0
        and ex_largest is not None
        and _number(ex_largest, "net excluding largest winner") > 0.0
        and _has_positive_independent_horizon(horizons)
    )


def _has_positive_independent_horizon(horizons: Mapping[str, object]) -> bool:
    return any(
        _nonnegative_integer(
            _mapping(value, "forward horizon").get("independent"),
            "independent paths",
        )
        > 0
        and _number(
            _mapping(value, "forward horizon").get("mean_directional_return_bps"),
            "mean directional return",
        )
        > 0.0
        for value in horizons.values()
    )


def _open_by_route(value: object) -> dict[str, tuple[Mapping[str, object], ...]]:
    if not isinstance(value, list):
        raise ValueError("open trades must be an array")
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for raw in value:
        row = _mapping(raw, "open trade")
        key = f"{_text(row.get('strategy_id'), 'open strategy')}|{_text(row.get('symbol'), 'open symbol')}"
        grouped.setdefault(key, []).append(row)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _provisional_open(rows: tuple[Mapping[str, object], ...]) -> dict[str, object]:
    sides = sorted({_text(row.get("side"), "open side") for row in rows})
    if not set(sides).issubset(_SIDES):
        raise ValueError("open sides must be long or short")
    marked = sum(
        _number(
            _mapping(row.get("marked_economics"), "marked economics").get(
                "active_lifecycle_marked_net_pnl_usd"
            ),
            "open marked net PnL",
        )
        for row in rows
    )
    return {"count": len(rows), "marked_net_pnl_usd": marked, "sides": sides}


def _forward_summary(horizons: Mapping[str, object]) -> dict[str, object]:
    return {
        "resolved_horizons": len(horizons),
        "independent_paths": sum(
            _nonnegative_integer(
                _mapping(value, "forward horizon").get("independent"),
                "independent paths",
            )
            for value in horizons.values()
        ),
        "execution_claim": False,
    }


def _cost_survival(live: Mapping[str, object]) -> str:
    if _nonnegative_integer(live.get("closed_trades"), "closed trades") == 0:
        return "unavailable"
    return (
        "positive_after_observed_costs"
        if _number(live.get("net_pnl_usd"), "net PnL") > 0.0
        else "nonpositive_after_observed_costs"
    )


def _concentration(value: Mapping[str, object]) -> str:
    amount = value.get("net_pnl_excluding_largest_winner_usd")
    if amount is None:
        return "unavailable"
    return (
        "positive_without_largest_winner"
        if _number(amount, "net excluding largest winner") > 0.0
        else "winner_concentrated_or_nonpositive"
    )


def _empty_live_translation() -> dict[str, object]:
    return {
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "net_pnl_usd": 0.0,
        "profit_factor": None,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "observed_sides": [],
        "after_cost": False,
    }


def _source_identity(run: Mapping[str, object]) -> dict[str, object]:
    return {
        "run_id": _text(run.get("run_id"), "run_id"),
        "profile_id": _text(run.get("profile_id"), "profile_id"),
        "profile_fingerprint": _text(
            run.get("profile_fingerprint"), "profile_fingerprint"
        ),
        "as_of_utc": _text(run.get("last_observed_at_utc"), "last observed time"),
    }


def _summary(routes: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    triage = Counter(_text(route.get("triage"), "triage") for route in routes.values())
    return {
        "routes": len(routes),
        "proceed": triage["PROCEED"],
        "revise": triage["REVISE"],
        "stop_exact_contract": triage["STOP"],
        "routes_with_both_side_live_execution": sum(
            set(
                _string_list(
                    _mapping(route.get("live_translation"), "live").get(
                        "observed_sides"
                    ),
                    "observed sides",
                )
            )
            == _SIDES
            for route in routes.values()
        ),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "open_marks_are_provisional": True,
    }


def _validate_report_only(value: Mapping[str, object], label: str) -> None:
    if value.get("report_only") is not True:
        raise ValueError(f"{label} must be report_only")
    if value.get("execution_authority") != "none":
        raise ValueError(f"{label} execution_authority must equal none")
    if value.get("performance_gate") is True or value.get("balance_gate") is True:
        raise ValueError(f"{label} cannot contain an execution gate")


def _contains(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _optional_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not result == result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return result


def _optional_number(value: object) -> float | None:
    return None if value is None else _number(value, "optional numeric value")


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text array")
    return list(value)
