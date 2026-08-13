"""Report-only p99 risk-balanced sizing comparison for the v49 candidate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

Record = Mapping[str, object]
_PROFILE = "multi_asset_growth_first_5000_repaired_candidate_v49"
_SCHEMA = "v49_portfolio_friction_stress_v1"


@dataclass(frozen=True)
class _Slot:
    symbol: str
    baseline_margin_fraction: float
    baseline_notional_usd: float
    baseline_p99_loss_usd: float
    p99_loss_bps: float


def build_v49_risk_balanced_sizing(source: Record) -> dict[str, object]:
    """Compare equal-margin v49 sizing with capital-neutral inverse-p99 sizing."""
    _validate_source(source)
    scenario = _target_scenario(source)
    equity = _positive(scenario.get("account_value_usd"), "account value")
    leverage = _positive(
        _mapping(source.get("sizing_policy"), "sizing policy").get(
            "configured_leverage"
        ),
        "configured leverage",
    )
    slots = _slots(scenario)
    total_margin = sum(slot.baseline_margin_fraction for slot in slots)
    inverse_total = sum(1.0 / slot.p99_loss_bps for slot in slots)
    rows = {
        slot.symbol: _candidate_row(slot, equity, leverage, total_margin, inverse_total)
        for slot in slots
    }
    comparison = _comparison(scenario, rows, equity, leverage, total_margin)
    return {
        "schema_version": "v49_risk_balanced_sizing_v1",
        "profile_id": source.get("profile_id"),
        "profile_fingerprint": source.get("profile_fingerprint"),
        "contract": _contract(),
        "by_asset": rows,
        "comparison": comparison,
        "recommendation": "forward_compare_equal_and_risk_balanced_without_auto_change",
        "limitations": _limitations(),
    }


def _validate_source(source: Record) -> None:
    contract = _mapping(source.get("contract"), "source contract")
    valid = (
        source.get("schema_version") == _SCHEMA
        and source.get("profile_id") == _PROFILE
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("automatic_sizing_change") is False
        and contract.get("runtime_strategy_changed") is False
    )
    if not valid:
        raise ValueError("source must be the exact report-only v49 stress contract")


def _target_scenario(source: Record) -> Record:
    scenarios = source.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("source scenarios must be a list")
    matches = [
        _mapping(row, "scenario")
        for row in scenarios
        if isinstance(row, Mapping) and row.get("account_value_usd") == 5000.0
    ]
    if len(matches) != 1:
        raise ValueError("source must contain one exact $5000 scenario")
    return matches[0]


def _slots(scenario: Record) -> tuple[_Slot, ...]:
    assets = _mapping(scenario.get("asset_slots"), "asset slots")
    slots = tuple(
        _slot(symbol, _mapping(row, f"slot {symbol}")) for symbol, row in assets.items()
    )
    if not slots:
        raise ValueError("asset slots must not be empty")
    reported_margin = _positive(
        scenario.get("route_aware_maximum_margin_fraction"), "reported margin"
    )
    if not _near(sum(slot.baseline_margin_fraction for slot in slots), reported_margin):
        raise ValueError("asset margin fractions do not reconcile")
    return slots


def _slot(symbol: object, row: Record) -> _Slot:
    name = _text(symbol, "symbol")
    routes = row.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError(f"{name} routes must be a nonempty list")
    notionals = {
        _positive(
            _mapping(route, f"{name} route").get("planned_notional_usd"), "notional"
        )
        for route in routes
    }
    if len(notionals) != 1:
        raise ValueError(f"{name} route notionals disagree")
    notional = notionals.pop()
    loss = _positive(row.get("stacked_p99_slot_loss_usd"), f"{name} p99 loss")
    return _Slot(
        symbol=name,
        baseline_margin_fraction=_positive(
            row.get("maximum_margin_fraction"), f"{name} margin"
        ),
        baseline_notional_usd=notional,
        baseline_p99_loss_usd=loss,
        p99_loss_bps=loss / notional * 10_000.0,
    )


def _candidate_row(
    slot: _Slot,
    equity: float,
    leverage: float,
    total_margin: float,
    inverse_total: float,
) -> dict[str, float]:
    margin_fraction = total_margin * (1.0 / slot.p99_loss_bps) / inverse_total
    notional = equity * margin_fraction * leverage
    return {
        "frozen_p99_loss_bps": slot.p99_loss_bps,
        "baseline_margin_fraction": slot.baseline_margin_fraction,
        "baseline_notional_usd": slot.baseline_notional_usd,
        "baseline_p99_loss_usd": slot.baseline_p99_loss_usd,
        "candidate_margin_fraction": margin_fraction,
        "candidate_notional_usd": notional,
        "candidate_p99_loss_usd": notional * slot.p99_loss_bps / 10_000.0,
    }


def _comparison(
    scenario: Record,
    rows: Record,
    equity: float,
    leverage: float,
    total_margin: float,
) -> dict[str, float]:
    baseline_losses = [
        _row_number(row, "baseline_p99_loss_usd") for row in rows.values()
    ]
    candidate_losses = [
        _row_number(row, "candidate_p99_loss_usd") for row in rows.values()
    ]
    baseline = sum(baseline_losses)
    candidate = sum(candidate_losses)
    reported = _positive(
        scenario.get("stacked_p99_stop_wave_loss_usd"), "reported p99 loss"
    )
    if not _near(baseline, reported):
        raise ValueError("baseline p99 loss does not reconcile")
    return {
        "total_margin_fraction": total_margin,
        "total_margin_usd": equity * total_margin,
        "total_notional_usd": equity * total_margin * leverage,
        "baseline_p99_loss_usd": baseline,
        "candidate_p99_loss_usd": candidate,
        "baseline_p99_max_min_ratio": max(baseline_losses) / min(baseline_losses),
        "candidate_p99_max_min_ratio": max(candidate_losses) / min(candidate_losses),
        "candidate_minus_baseline_p99_loss_usd": candidate - baseline,
        "baseline_p99_loss_pct_equity": baseline / equity * 100.0,
        "candidate_p99_loss_pct_equity": candidate / equity * 100.0,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_sizing_change": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "profit_forecast": False,
    }


def _limitations() -> list[str]:
    return [
        "frozen p99 loss intensity is assumed linear at candidate notionals",
        "exact visible depth must be repriced before any sizing change",
        "risk balancing does not establish or weight strategy edge",
        "correlation and simultaneous trigger probability remain unmodeled",
        "p99 is an empirical scenario rather than a worst-case loss bound",
    ]


def _row_number(value: object, key: str) -> float:
    return _positive(_mapping(value, "allocation row").get(key), key)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return number


def _near(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)
