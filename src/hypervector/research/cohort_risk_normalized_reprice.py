"""Exact-notional liquidity audit for a frozen allocation challenger."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

Record = Mapping[str, object]


@dataclass(frozen=True)
class ExactVisibleCost:
    """Exact-notional adverse one-way visible-depth quantiles."""

    notional_usd: float
    sample_count: int
    complete_rate: float
    p50: float
    p90: float
    p99: float
    evidence_source: str

    def __post_init__(self) -> None:
        """Validate exact size, ordered quantiles, and provenance."""
        _positive(self.notional_usd, "exact notional")
        _positive_integer(self.sample_count, "exact sample count")
        _fraction_or_zero(self.complete_rate, "exact completion rate")
        values = tuple(
            _nonnegative(value, "exact visible cost")
            for value in (self.p50, self.p90, self.p99)
        )
        if values != tuple(sorted(values)):
            raise ValueError("exact visible cost quantiles must be ordered")
        _text(self.evidence_source, "exact evidence source")


def build_exact_reprice_audit(
    source: Record,
    allocation: Record,
    exact_costs: Mapping[str, ExactVisibleCost],
) -> dict[str, object]:
    """Reprice one frozen allocation without changing its notionals."""
    _validate_contracts(source, allocation)
    source_assets = _mapping(source.get("by_asset"), "source assets")
    allocation_assets = _mapping(allocation.get("by_asset"), "allocation assets")
    symbols = set(source_assets)
    if symbols != set(allocation_assets) or symbols != set(exact_costs):
        raise ValueError("source, allocation, and exact evidence assets must match")
    rows = {
        _text(symbol, "asset symbol"): _asset_reprice(
            _text(symbol, "asset symbol"),
            _mapping(source_assets[symbol], f"source {symbol}"),
            _mapping(allocation_assets[symbol], f"allocation {symbol}"),
            exact_costs[symbol],
        )
        for symbol in source_assets
    }
    return {
        "schema_version": 1,
        "mode": "cohort_p99_risk_normalized_exact_reprice_v1",
        "status": "exact_notional_repriced",
        "contract": _contract(),
        "source_identity": dict(
            _mapping(allocation.get("source_identity"), "allocation source identity")
        ),
        "allocation_mode": allocation.get("mode"),
        "allocation_reoptimized_after_reprice": False,
        "exact_notional_repricing_complete": True,
        "by_asset": rows,
        "portfolio_comparison": _portfolio_comparison(allocation, rows),
        "limitations": _limitations(),
    }


def _validate_contracts(source: Record, allocation: Record) -> None:
    if source.get("mode") != "cohort_growth_sizing_stress_v3":
        raise ValueError("source growth stress mode is invalid")
    if allocation.get("mode") != "cohort_p99_risk_normalized_allocation_v1":
        raise ValueError("allocation mode is invalid")
    for label, document in (("source", source), ("allocation", allocation)):
        contract = _mapping(document.get("contract"), f"{label} contract")
        if (
            contract.get("report_only") is not True
            or contract.get("execution_authority") != "none"
            or contract.get("performance_gate") is not False
            or contract.get("balance_gate") is not False
        ):
            raise ValueError(f"{label} contract is not report-only and ungated")
    identity = _mapping(allocation.get("source_identity"), "allocation source identity")
    for key in ("mode", "profile_id", "profile_fingerprint"):
        if identity.get(key) != source.get(key):
            raise ValueError(f"allocation source identity conflicts on {key}")


def _asset_reprice(
    symbol: str,
    source: Record,
    allocation: Record,
    exact: ExactVisibleCost,
) -> dict[str, object]:
    notional = _positive(
        allocation.get("candidate_notional_usd"), f"{symbol} candidate notional"
    )
    if not _near(notional, exact.notional_usd):
        raise ValueError(f"{symbol} exact notional does not match allocation")
    exact_by_quantile = {"p50": exact.p50, "p90": exact.p90, "p99": exact.p99}
    repriced = {
        quantile: _repriced_scenario(
            symbol, quantile, source, notional, exact_by_quantile[quantile]
        )
        for quantile in ("p50", "p90", "p99")
    }
    return {
        "candidate_notional_usd": notional,
        "exact_visible_cost_sample_count": exact.sample_count,
        "exact_visible_depth_complete_rate": exact.complete_rate,
        "exact_evidence_source": exact.evidence_source,
        **{
            f"repriced_{quantile}_total_loss_bps": row[0]
            for quantile, row in repriced.items()
        },
        **{
            f"repriced_{quantile}_loss_usd": row[1]
            for quantile, row in repriced.items()
        },
    }


def _repriced_scenario(
    symbol: str,
    quantile: str,
    source: Record,
    notional: float,
    exact_visible_bps: float,
) -> tuple[float, float]:
    scenario = _mapping(source.get(quantile), f"{symbol} {quantile}")
    total = _positive(scenario.get("total_loss_bps"), f"{symbol} total bps")
    frozen_visible = _nonnegative(
        scenario.get("adverse_exit_visible_cost_bps"), f"{symbol} visible bps"
    )
    repriced = total - frozen_visible + exact_visible_bps
    if repriced <= 0.0:
        raise ValueError(f"{symbol} {quantile} repriced loss must be positive")
    return repriced, notional * repriced / 10_000.0


def _portfolio_comparison(
    allocation: Record, rows: Mapping[str, Record]
) -> dict[str, object]:
    prior = _mapping(allocation.get("portfolio_comparison"), "allocation portfolio")
    baseline = dict(_mapping(prior.get("baseline"), "allocation baseline"))
    frozen = dict(_mapping(prior.get("candidate"), "frozen candidate"))
    repriced = _repriced_portfolio(rows)
    return {
        "baseline": baseline,
        "frozen_cost_candidate": frozen,
        "repriced_candidate": repriced,
        "repriced_minus_baseline": {
            key: _positive(repriced.get(key), key) - _positive(baseline.get(key), key)
            for key in (
                "p50_stop_wave_loss_usd",
                "p90_stop_wave_loss_usd",
                "p99_stop_wave_loss_usd",
            )
        },
    }


def _repriced_portfolio(rows: Mapping[str, Record]) -> dict[str, float]:
    totals = {
        quantile: sum(
            _positive(row.get(f"repriced_{quantile}_loss_usd"), quantile)
            for row in rows.values()
        )
        for quantile in ("p50", "p90", "p99")
    }
    p99 = [
        _positive(row.get("repriced_p99_loss_usd"), "asset p99")
        for row in rows.values()
    ]
    return {
        **{
            f"{quantile}_stop_wave_loss_usd": value
            for quantile, value in totals.items()
        },
        "p99_asset_loss_max_min_ratio": max(p99) / min(p99),
        "minimum_visible_depth_complete_rate": min(
            _fraction_or_zero(
                row.get("exact_visible_depth_complete_rate"), "completion rate"
            )
            for row in rows.values()
        ),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "repricing audits the frozen candidate notionals without reoptimizing them",
        "visible depth can cancel before a market IOC reaches the venue",
        "liquidity samples are not conditioned on future strategy entry timestamps",
        "p99 is an empirical quantile rather than a worst-case loss bound",
        "risk normalization does not establish signal edge or reduce correlation",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _fraction_or_zero(value: object, label: str) -> float:
    number = _nonnegative(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must not exceed one")
    return number


def _positive(value: object, label: str) -> float:
    number = _nonnegative(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


def _near(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)
