"""Report-only risk-normalized allocation challenger for cohort growth."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

Record = Mapping[str, object]


@dataclass(frozen=True)
class _Plan:
    equity_usd: float
    leverage: float
    margin_fraction_per_slot: float
    notional_usd_per_slot: float
    asset_count: int
    maximum_positions: int


@dataclass(frozen=True)
class _AssetRisk:
    symbol: str
    sample_count: int
    complete_rate: float
    p50_bps: float
    p90_bps: float
    p99_bps: float


def build_risk_normalized_allocation(source: Record) -> dict[str, object]:
    """Redistribute a frozen growth plan by measured p99 loss intensity."""
    _validate_source_contract(source)
    plan = _read_plan(source)
    risks = _read_asset_risks(source, plan)
    total_notional = plan.notional_usd_per_slot * plan.asset_count
    inverse_total = sum(1.0 / risk.p99_bps for risk in risks)
    rows = {
        risk.symbol: _allocation_row(
            risk,
            plan,
            total_notional * (1.0 / risk.p99_bps) / inverse_total,
        )
        for risk in risks
    }
    comparison = _portfolio_comparison(rows, source, plan)
    return {
        "schema_version": 1,
        "mode": "cohort_p99_risk_normalized_allocation_v1",
        "status": "report_only_candidate",
        "contract": _contract(),
        "source_identity": _source_identity(source),
        "sizing_invariants": _sizing_invariants(plan),
        "by_asset": rows,
        "portfolio_comparison": comparison,
        "required_profile_changes": _profile_changes(rows),
        "exact_notional_repricing_required": True,
        "limitations": _limitations(plan),
    }


def _validate_source_contract(source: Record) -> None:
    if source.get("mode") != "cohort_growth_sizing_stress_v3":
        raise ValueError("source mode must be cohort_growth_sizing_stress_v3")
    contract = _mapping(source.get("contract"), "source contract")
    invalid = (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("performance_gate") is not False
        or contract.get("balance_gate") is not False
        or contract.get("automatic_sizing_change") is not False
    )
    if invalid:
        raise ValueError("source contract is not report-only and ungated")


def _read_plan(source: Record) -> _Plan:
    row = _mapping(source.get("sizing_plan"), "sizing plan")
    plan = _Plan(
        equity_usd=_positive(row.get("target_equity_usd"), "target equity"),
        leverage=_positive(row.get("leverage"), "leverage"),
        margin_fraction_per_slot=_fraction(
            row.get("margin_fraction_per_slot"), "margin fraction"
        ),
        notional_usd_per_slot=_positive(
            row.get("planned_notional_usd_per_slot"), "planned notional"
        ),
        asset_count=_positive_integer(row.get("configured_assets"), "asset count"),
        maximum_positions=_positive_integer(
            row.get("maximum_positions"), "maximum positions"
        ),
    )
    _validate_plan_arithmetic(row, plan)
    return plan


def _validate_plan_arithmetic(row: Record, plan: _Plan) -> None:
    expected_notional = plan.equity_usd * plan.margin_fraction_per_slot * plan.leverage
    if not _near(plan.notional_usd_per_slot, expected_notional):
        raise ValueError("sizing plan notional arithmetic is inconsistent")
    reported_fraction = _fraction(
        row.get("actual_roster_maximum_margin_fraction"), "roster margin fraction"
    )
    if not _near(reported_fraction, plan.asset_count * plan.margin_fraction_per_slot):
        raise ValueError("sizing plan roster margin arithmetic is inconsistent")
    if plan.maximum_positions < plan.asset_count:
        raise ValueError("maximum positions must cover configured assets")


def _read_asset_risks(source: Record, plan: _Plan) -> tuple[_AssetRisk, ...]:
    assets = _mapping(source.get("by_asset"), "source assets")
    if len(assets) != plan.asset_count:
        raise ValueError("source asset count conflicts with sizing plan")
    risks = tuple(
        _asset_risk(symbol, _mapping(raw, f"asset {symbol}"), plan)
        for symbol, raw in assets.items()
    )
    if not risks:
        raise ValueError("source assets must not be empty")
    return risks


def _asset_risk(symbol: object, row: Record, plan: _Plan) -> _AssetRisk:
    name = _text(symbol, "asset symbol")
    scenarios = {
        quantile: _scenario(name, quantile, row, plan.notional_usd_per_slot)
        for quantile in ("p50", "p90", "p99")
    }
    ordered = tuple(scenarios[key] for key in ("p50", "p90", "p99"))
    if ordered != tuple(sorted(ordered)):
        raise ValueError(f"{name} loss quantiles are not ordered")
    return _AssetRisk(
        symbol=name,
        sample_count=_positive_integer(
            row.get("visible_cost_sample_count"), f"{name} sample count"
        ),
        complete_rate=_fraction_or_zero(
            row.get("visible_depth_complete_rate"), f"{name} complete rate"
        ),
        p50_bps=scenarios["p50"],
        p90_bps=scenarios["p90"],
        p99_bps=scenarios["p99"],
    )


def _scenario(
    symbol: str, quantile: str, row: Record, baseline_notional: float
) -> float:
    scenario = _mapping(row.get(quantile), f"{symbol} {quantile}")
    bps = _positive(scenario.get("total_loss_bps"), f"{symbol} {quantile} bps")
    loss = _positive(scenario.get("total_loss_usd"), f"{symbol} {quantile} loss")
    if not _near(loss, baseline_notional * bps / 10_000.0):
        raise ValueError(f"{symbol} {quantile} loss arithmetic is inconsistent")
    return bps


def _allocation_row(
    risk: _AssetRisk, plan: _Plan, candidate_notional: float
) -> dict[str, float | int]:
    baseline_notional = plan.notional_usd_per_slot
    candidate_margin = candidate_notional / plan.leverage
    return {
        "visible_cost_sample_count": risk.sample_count,
        "visible_depth_complete_rate": risk.complete_rate,
        "frozen_p50_total_loss_bps": risk.p50_bps,
        "frozen_p90_total_loss_bps": risk.p90_bps,
        "frozen_p99_total_loss_bps": risk.p99_bps,
        "baseline_notional_usd": baseline_notional,
        "baseline_margin_fraction": plan.margin_fraction_per_slot,
        "baseline_p50_loss_usd": baseline_notional * risk.p50_bps / 10_000.0,
        "baseline_p90_loss_usd": baseline_notional * risk.p90_bps / 10_000.0,
        "baseline_p99_loss_usd": baseline_notional * risk.p99_bps / 10_000.0,
        "candidate_notional_usd": candidate_notional,
        "candidate_margin_usd": candidate_margin,
        "candidate_margin_fraction": candidate_margin / plan.equity_usd,
        "candidate_p50_loss_usd": candidate_notional * risk.p50_bps / 10_000.0,
        "candidate_p90_loss_usd": candidate_notional * risk.p90_bps / 10_000.0,
        "candidate_p99_loss_usd": candidate_notional * risk.p99_bps / 10_000.0,
        "notional_change_usd": candidate_notional - baseline_notional,
    }


def _portfolio_comparison(
    rows: Mapping[str, Record], source: Record, plan: _Plan
) -> dict[str, object]:
    baseline = _portfolio_row(rows, "baseline", plan.equity_usd)
    candidate = _portfolio_row(rows, "candidate", plan.equity_usd)
    _validate_reported_baseline(source, baseline)
    return {
        "baseline": baseline,
        "candidate": candidate,
        "candidate_minus_baseline": {
            key: _numeric(candidate.get(key), key) - _numeric(baseline.get(key), key)
            for key in (
                "p50_stop_wave_loss_usd",
                "p90_stop_wave_loss_usd",
                "p99_stop_wave_loss_usd",
            )
        },
    }


def _portfolio_row(
    rows: Mapping[str, Record], prefix: str, equity_usd: float
) -> dict[str, float]:
    losses = {
        quantile: sum(
            _numeric(row.get(f"{prefix}_{quantile}_loss_usd"), quantile)
            for row in rows.values()
        )
        for quantile in ("p50", "p90", "p99")
    }
    p99_assets = [
        _numeric(row.get(f"{prefix}_p99_loss_usd"), "asset p99 loss")
        for row in rows.values()
    ]
    result = {f"{key}_stop_wave_loss_usd": value for key, value in losses.items()}
    result["p99_stop_wave_loss_pct_equity"] = losses["p99"] / equity_usd * 100.0
    result["p99_asset_loss_max_min_ratio"] = max(p99_assets) / min(p99_assets)
    return result


def _validate_reported_baseline(source: Record, calculated: Record) -> None:
    stress = _mapping(source.get("portfolio_stress"), "portfolio stress")
    roster = _mapping(stress.get("configured_asset_roster"), "roster stress")
    for quantile in ("p50", "p90", "p99"):
        key = f"{quantile}_stop_wave_loss_usd"
        if not _near(
            _positive(roster.get(key), key), _positive(calculated.get(key), key)
        ):
            raise ValueError(f"source {quantile} portfolio arithmetic is inconsistent")


def _sizing_invariants(plan: _Plan) -> dict[str, float | int]:
    margin_fraction = plan.margin_fraction_per_slot * plan.asset_count
    return {
        "target_equity_usd": plan.equity_usd,
        "leverage": plan.leverage,
        "configured_assets": plan.asset_count,
        "maximum_positions": plan.maximum_positions,
        "total_margin_fraction": margin_fraction,
        "total_margin_usd": plan.equity_usd * margin_fraction,
        "total_notional_usd": plan.notional_usd_per_slot * plan.asset_count,
    }


def _source_identity(source: Record) -> dict[str, object]:
    return {
        "mode": source.get("mode"),
        "profile_id": source.get("profile_id"),
        "profile_fingerprint": source.get("profile_fingerprint"),
    }


def _profile_changes(rows: Mapping[str, Record]) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "margin_fraction": row["candidate_margin_fraction"],
            "minimum_nonbinding_max_notional_usd": row["candidate_notional_usd"],
        }
        for symbol, row in rows.items()
    ]


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "profit_forecast": False,
    }


def _limitations(plan: _Plan) -> list[str]:
    return [
        "p99 loss intensity is frozen from the equal-notional source artifact",
        "visible-depth costs are not repriced at each proposed asset notional",
        "inverse-p99 sizing does not establish strategy edge or forecast profit",
        "the allocation preserves total exposure and does not reduce correlation",
        f"the unused {plan.maximum_positions - plan.asset_count} slots are excluded",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _fraction(value: object, label: str) -> float:
    number = _positive(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must not exceed one")
    return number


def _fraction_or_zero(value: object, label: str) -> float:
    number = _numeric(value, label)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return number


def _positive(value: object, label: str) -> float:
    number = _numeric(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _numeric(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _near(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)
