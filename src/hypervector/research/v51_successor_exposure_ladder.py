"""Report-only evidence ladder for a post-v51 successor portfolio."""

from __future__ import annotations

from collections.abc import Mapping
from math import floor, isfinite

Record = Mapping[str, object]

_CANARY_EQUITY_USD = 500.0
_CANARY_MARGIN_FRACTION = 0.03
_CANARY_LEVERAGE = 5.0
_CAPACITY_POSITIONS = 10
_REFERENCE_EXECUTION_LEVERAGE = 10.0
_CAPACITY_STOP_BPS = 80.0
_MARGIN_HEADROOM_FRACTION = 0.20
_CONDITIONAL = {
    "conditional_successor_candidate_not_full_size",
    "conditional_successor_candidate_selection_risk",
}
_NONLIVE = {
    "defer_pending_current_close_and_source_native_breadth",
    "defer_pending_source_native_breadth",
    "repair_candidate_alignment_hypothesis_not_ready",
    "research_only_censored_and_one_sided",
    "research_only_not_replacement_ready",
    "retire_after_current_protected_lifecycle",
    "retire_from_successor",
}
_STOP_BPS = {
    "hulk_expansion_short_robust_v3": 75.0,
    "liquidity_sweep_long_1h_stop60_target60_v2": 60.0,
}
_TARGET_BPS = {
    "hulk_expansion_short_robust_v3": 225.0,
    "liquidity_sweep_long_1h_stop60_target60_v2": 60.0,
}


def build_v51_successor_exposure_ladder(
    disposition: Record,
    *,
    account_equity_usd: float,
    core_taker_fee_bps_per_side: float,
    hip3_taker_fee_bps_per_side: float,
    slippage_stress_bps_per_side: float,
) -> dict[str, object]:
    """Translate current route evidence into advisory exposure ceilings."""
    _require_source(disposition)
    equity = _positive(account_equity_usd, "account equity")
    fees = {
        "core": _nonnegative(core_taker_fee_bps_per_side, "core taker fee"),
        "hip3": _nonnegative(hip3_taker_fee_bps_per_side, "HIP-3 taker fee"),
    }
    slippage = _nonnegative(slippage_stress_bps_per_side, "slippage stress")
    tiers = _tiers(equity, fees["core"], slippage)
    rows = _route_ceilings(disposition, tiers, equity, fees, slippage)
    return {
        "schema_version": "v51_successor_exposure_ladder_v2",
        "supersedes": "v51_successor_exposure_ladder_v1",
        "contract": _contract(),
        "reference_canary": _reference_canary(),
        "account_equity_usd": equity,
        "fee_evidence_bps_per_side": fees,
        "slippage_stress_bps_per_side": slippage,
        "exposure_tiers": tiers,
        "ten_slot_capacity_scenarios": _capacity_scenarios(
            tiers, equity, fees, slippage
        ),
        "current_route_ceilings": rows,
        "portfolio_ceiling": _portfolio_ceiling(rows, equity),
        "assessment": _assessment(rows),
        "limitations": _limitations(),
    }


def _require_source(source: Record) -> None:
    if (
        source.get("mode") != "report_only"
        or source.get("execution_authority") != "none"
        or source.get("automatic_live_change") is not False
    ):
        raise ValueError("successor disposition must be report-only")
    conclusion = _mapping(source.get("portfolio_conclusion"), "portfolio conclusion")
    supported = conclusion.get("full_size_routes_supported")
    if isinstance(supported, bool) or not isinstance(supported, int) or supported < 0:
        raise ValueError("full-size route count must be a nonnegative integer")
    _route_sequence(source.get("route_dispositions"))


def _tiers(equity: float, core_fee: float, slippage: float) -> list[dict[str, object]]:
    return [
        _fixed_tier("research_only", equity, 0.0, _research_requirements()),
        _fixed_tier("canary_equivalent", equity, 0.15, _canary_requirements()),
        _risk_tier("provisional_growth", equity, 0.005, 0.60, core_fee, slippage),
        _risk_tier("corroborated_growth", equity, 0.01, 1.00, core_fee, slippage),
        _risk_tier("expansion", equity, 0.015, 1.50, core_fee, slippage),
    ]


def _fixed_tier(
    tier: str, equity: float, gross_fraction: float, requirements: list[str]
) -> dict[str, object]:
    return {
        "tier_id": tier,
        "gross_account_fraction": gross_fraction,
        "risk_budget_fraction": None,
        "notional_usd": equity * gross_fraction,
        "minimum_evidence": requirements,
    }


def _risk_tier(
    tier: str,
    equity: float,
    risk_fraction: float,
    gross_cap: float,
    core_fee: float,
    slippage: float,
) -> dict[str, object]:
    loss_bps = _CAPACITY_STOP_BPS + 2.0 * (core_fee + slippage)
    risk_sized = equity * risk_fraction / (loss_bps / 10_000.0)
    return {
        "tier_id": tier,
        "gross_account_fraction": min(risk_sized / equity, gross_cap),
        "maximum_gross_account_fraction": gross_cap,
        "risk_budget_fraction": risk_fraction,
        "notional_usd": min(risk_sized, equity * gross_cap),
        "minimum_evidence": _growth_requirements(tier),
    }


def _route_ceilings(
    source: Record,
    tiers: list[dict[str, object]],
    equity: float,
    fees: Mapping[str, float],
    slippage: float,
) -> list[dict[str, object]]:
    notionals = {str(row["tier_id"]): float(row["notional_usd"]) for row in tiers}
    return [
        _route_ceiling(
            _mapping(raw, "route disposition"), notionals, equity, fees, slippage
        )
        for raw in _route_sequence(source.get("route_dispositions"))
    ]


def _route_ceiling(
    route: Record,
    notionals: Mapping[str, float],
    equity: float,
    fees: Mapping[str, float],
    slippage: float,
) -> dict[str, object]:
    strategy = _text(route.get("strategy_id"), "strategy id")
    symbol = _text(route.get("symbol"), "symbol")
    disposition = _text(route.get("disposition"), "disposition")
    tier = _current_tier(disposition)
    notional = notionals[tier]
    stop_bps = _route_stop(strategy, notional)
    target_bps = _route_target(strategy, notional)
    fee_class = "hip3" if symbol.startswith("xyz:") else "core"
    loss = _stop_friction_loss(notional, stop_bps, fees[fee_class], slippage)
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "side": _text(route.get("side"), "side"),
        "source_disposition": disposition,
        "maximum_proposal_tier": tier,
        "maximum_proposed_notional_usd": notional,
        "maximum_stop_bps": stop_bps,
        "maximum_target_bps": target_bps,
        "fee_class": fee_class,
        "taker_fee_bps_per_side": fees[fee_class],
        "slippage_stress_bps_per_side": slippage,
        "stop_plus_round_trip_friction_usd": loss,
        "maximum_net_target_usd": _net_target(
            notional, target_bps, fees[fee_class], slippage
        ),
        "stop_plus_round_trip_friction_fraction_equity": loss / equity,
        "live_authorized": False,
    }


def _current_tier(disposition: str) -> str:
    if disposition in _CONDITIONAL:
        return "canary_equivalent"
    if disposition in _NONLIVE:
        return "research_only"
    raise ValueError(f"unsupported successor disposition: {disposition}")


def _route_stop(strategy: str, notional: float) -> float | None:
    if notional == 0.0:
        return _STOP_BPS.get(strategy)
    stop = _STOP_BPS.get(strategy)
    if stop is None:
        raise ValueError(f"candidate route has no frozen stop contract: {strategy}")
    return stop


def _route_target(strategy: str, notional: float) -> float | None:
    if notional == 0.0:
        return _TARGET_BPS.get(strategy)
    target = _TARGET_BPS.get(strategy)
    if target is None:
        raise ValueError(f"candidate route has no frozen target contract: {strategy}")
    return target


def _stop_friction_loss(
    notional: float, stop_bps: float | None, fee_bps: float, slippage: float
) -> float:
    if notional == 0.0:
        return 0.0
    if stop_bps is None:
        raise ValueError("nonzero route exposure requires a stop")
    return notional * (stop_bps + 2.0 * (fee_bps + slippage)) / 10_000.0


def _net_target(
    notional: float, target_bps: float | None, fee_bps: float, slippage: float
) -> float:
    if notional == 0.0 or target_bps is None:
        return 0.0
    return notional * (target_bps - 2.0 * (fee_bps + slippage)) / 10_000.0


def _portfolio_ceiling(
    rows: list[dict[str, object]], equity: float
) -> dict[str, object]:
    active = [row for row in rows if float(row["maximum_proposed_notional_usd"]) > 0.0]
    by_symbol: dict[str, list[dict[str, object]]] = {}
    for row in active:
        by_symbol.setdefault(str(row["symbol"]), []).append(row)
    loss = sum(
        max(float(row["stop_plus_round_trip_friction_usd"]) for row in group)
        for group in by_symbol.values()
    )
    notional = sum(
        max(float(row["maximum_proposed_notional_usd"]) for row in group)
        for group in by_symbol.values()
    )
    return {
        "simultaneous_asset_slots": len(by_symbol),
        "maximum_simultaneous_notional_usd": notional,
        "maximum_stop_plus_friction_wave_usd": loss,
        "maximum_stop_plus_friction_wave_fraction_equity": loss / equity,
    }


def _capacity_scenarios(
    tiers: list[dict[str, object]],
    equity: float,
    fees: Mapping[str, float],
    slippage: float,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for tier in tiers:
        notional = float(tier["notional_usd"])
        gross = notional * _CAPACITY_POSITIONS
        margin_fraction = gross / _REFERENCE_EXECUTION_LEVERAGE / equity
        maximum_positions = _headroom_position_capacity(notional, equity)
        output.append(
            {
                "tier_id": tier["tier_id"],
                "position_capacity": _CAPACITY_POSITIONS,
                "notional_per_position_usd": notional,
                "gross_account_exposure_multiple": gross / equity,
                "margin_fraction_at_10x": margin_fraction,
                "ten_slot_margin_feasible_at_10x": margin_fraction <= 1.0,
                "margin_headroom_fraction": _MARGIN_HEADROOM_FRACTION,
                "maximum_positions_with_20pct_margin_headroom": maximum_positions,
                "ten_slot_margin_feasible_with_20pct_headroom": (
                    maximum_positions == _CAPACITY_POSITIONS
                ),
                "all_core_stop_friction_wave_usd": _capacity_loss(
                    notional, fees["core"], slippage
                ),
                "all_hip3_stop_friction_wave_usd": _capacity_loss(
                    notional, fees["hip3"], slippage
                ),
            }
        )
    return output


def _headroom_position_capacity(notional: float, equity: float) -> int:
    if notional == 0.0:
        return _CAPACITY_POSITIONS
    available_margin = equity * (1.0 - _MARGIN_HEADROOM_FRACTION)
    position_margin = notional / _REFERENCE_EXECUTION_LEVERAGE
    return min(_CAPACITY_POSITIONS, floor(available_margin / position_margin))


def _capacity_loss(notional: float, fee_bps: float, slippage: float) -> float:
    return (
        notional
        * _CAPACITY_POSITIONS
        * (_CAPACITY_STOP_BPS + 2.0 * (fee_bps + slippage))
        / 10_000.0
    )


def _assessment(rows: list[dict[str, object]]) -> dict[str, object]:
    canary_routes = [
        f"{row['strategy_id']}|{row['symbol']}|{row['side']}"
        for row in rows
        if row["maximum_proposal_tier"] == "canary_equivalent"
    ]
    return {
        "successor_live_ready": False,
        "growth_meaningful_portfolio_ready": False,
        "full_size_routes_supported": 0,
        "canary_equivalent_proposal_candidates": canary_routes,
        "interpretation": (
            "Only evidence-capture sizing is supportable; this is not a complete "
            "or automatically authorized successor portfolio."
        ),
        "growth_limitations": [
            "Both proposal candidates share one BTC asset slot.",
            "Neither candidate has a compatible v51 close or repeatable live expectancy.",
            "The bounded tier is designed to collect evidence, not meet an income target.",
        ],
    }


def _reference_canary() -> dict[str, float]:
    notional = _CANARY_EQUITY_USD * _CANARY_MARGIN_FRACTION * _CANARY_LEVERAGE
    return {
        "account_equity_usd": _CANARY_EQUITY_USD,
        "margin_fraction": _CANARY_MARGIN_FRACTION,
        "leverage": _CANARY_LEVERAGE,
        "notional_usd": notional,
        "gross_account_fraction": notional / _CANARY_EQUITY_USD,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_performance_gate": False,
        "human_approval_required": True,
    }


def _research_requirements() -> list[str]:
    return ["No live exposure; continue causal research and technical validation."]


def _canary_requirements() -> list[str]:
    return [
        "Exact implementation and source identity are frozen.",
        "Entry, stop, exit, fees, funding, and telemetry pass technical preflight.",
        "Human explicitly approves a bounded evidence-capture run.",
    ]


def _growth_requirements(tier: str) -> list[str]:
    if tier == "provisional_growth":
        return _provisional_requirements()
    if tier == "corroborated_growth":
        return _corroborated_requirements()
    if tier == "expansion":
        return _full_size_requirements()
    raise ValueError(f"unsupported growth tier: {tier}")


def _provisional_requirements() -> list[str]:
    return [
        "At least five compatible resolved closes including a nonwinner.",
        "Net and net excluding the largest winner are positive after exact costs.",
        "Profit factor exceeds one without unresolved technical lifecycles.",
    ]


def _corroborated_requirements() -> list[str]:
    return [
        "At least twelve compatible resolved closes with configured-side coverage.",
        "At least two of three chronological blocks are positive under stress costs.",
        "Net excluding the largest winner remains positive and costs stay in bounds.",
    ]


def _full_size_requirements() -> list[str]:
    return [
        "At least twenty-five compatible resolved closes and active-side robustness.",
        "At least three of four chronological blocks are positive under stress costs.",
        "Stress profit factor is at least 1.2 and largest-winner removal stays positive.",
        "A separately approved live proposal defines portfolio and rollback limits.",
    ]


def _limitations() -> list[str]:
    return [
        "Evidence thresholds are proposal-readiness heuristics, not profit guarantees.",
        "Stop-market gaps, latency, funding, and visible-depth loss can exceed this arithmetic.",
        "Leverage is not a confidence score; proposed exposure is controlled by notional.",
        "Each promotion requires new exact evidence and explicit human approval.",
    ]


def _route_sequence(value: object) -> list[object]:
    if not isinstance(value, list) or not value:
        raise ValueError("route dispositions must be a non-empty list")
    return value


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _positive(value: object, label: str) -> float:
    number = _nonnegative(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number
