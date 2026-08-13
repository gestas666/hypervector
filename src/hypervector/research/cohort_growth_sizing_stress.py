"""Report-only percentage sizing and correlated-loss stress for cohort growth."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class VisibleCostQuantiles:
    """Observed adverse one-way exit visible-depth costs at proposed notional."""

    sample_count: int
    complete_rate: float
    p50: float
    p90: float
    p99: float

    def __post_init__(self) -> None:
        """Validate ordered finite empirical cost evidence."""
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count <= 0
        ):
            raise ValueError("visible cost sample_count must be positive")
        _unit_interval(self.complete_rate, "visible cost complete_rate")
        values = (self.p50, self.p90, self.p99)
        if any(not isfinite(value) or value < 0.0 for value in values):
            raise ValueError("visible cost quantiles must be finite and nonnegative")
        if values != tuple(sorted(values)):
            raise ValueError("visible cost quantiles must be ordered")


@dataclass(frozen=True)
class AssetGrowthStressInput:
    """One asset's frozen stop, fee, liquidity, funding, and current cap inputs."""

    symbol: str
    stop_bps: float
    one_way_taker_fee_bps: float
    visible_cost: VisibleCostQuantiles
    latest_hourly_funding_rate: float
    current_profile_cap_usd: float

    def __post_init__(self) -> None:
        """Reject incomplete or success-shaped asset evidence."""
        if not self.symbol.strip():
            raise ValueError("asset symbol must be non-empty")
        _positive(self.stop_bps, f"{self.symbol} stop_bps")
        _nonnegative(self.one_way_taker_fee_bps, f"{self.symbol} fee")
        if not isfinite(self.latest_hourly_funding_rate):
            raise ValueError(f"{self.symbol} funding rate must be finite")
        _positive(self.current_profile_cap_usd, f"{self.symbol} current cap")


def build_growth_sizing_stress(
    *,
    equity_usd: float,
    margin_fraction: float,
    leverage: float,
    maximum_positions: int,
    assets: Sequence[AssetGrowthStressInput],
) -> dict[str, object]:
    """Project measured per-slot and simultaneous losses without changing runtime."""
    equity = _positive(equity_usd, "equity_usd")
    margin = _fraction(margin_fraction, "margin_fraction")
    configured_leverage = _positive(leverage, "leverage")
    capacity = _positive_integer(maximum_positions, "maximum_positions")
    rows = tuple(assets)
    if not rows:
        raise ValueError("assets must be non-empty")
    symbols = tuple(row.symbol for row in rows)
    if len(set(symbols)) != len(symbols):
        raise ValueError("asset symbols must be unique")
    if capacity < len(rows):
        raise ValueError("maximum positions must cover assets")
    planned_margin = equity * margin
    planned_notional = planned_margin * configured_leverage
    by_asset = {
        row.symbol: _asset_projection(row, equity, planned_notional) for row in rows
    }
    return {
        "schema_version": 3,
        "mode": "cohort_growth_sizing_stress_v3",
        "contract": _contract(),
        "sizing_plan": _sizing_plan(
            equity, margin, configured_leverage, capacity, len(rows)
        ),
        "by_asset": by_asset,
        "portfolio_stress": _portfolio_stress(
            by_asset, equity, planned_margin, capacity
        ),
        "repeated_wave_sensitivity": _repeated_wave_sensitivity(
            by_asset, equity, capacity
        ),
        "limitations": _limitations(),
    }


def _asset_projection(
    asset: AssetGrowthStressInput,
    equity_usd: float,
    notional_usd: float,
) -> dict[str, object]:
    fee_bps = 2.0 * asset.one_way_taker_fee_bps
    funding_bps = abs(asset.latest_hourly_funding_rate) * 24.0 * 10_000.0
    return {
        "stop_bps": asset.stop_bps,
        "one_way_taker_fee_bps": asset.one_way_taker_fee_bps,
        "round_trip_taker_fee_bps": fee_bps,
        "latest_hourly_funding_rate": asset.latest_hourly_funding_rate,
        "adverse_24h_funding_bps": funding_bps,
        "visible_cost_sample_count": asset.visible_cost.sample_count,
        "visible_depth_complete_rate": asset.visible_cost.complete_rate,
        "current_profile_cap_usd": asset.current_profile_cap_usd,
        "current_profile_cap_binding_at_target_equity": (
            asset.current_profile_cap_usd < notional_usd
        ),
        "candidate_nonbinding_cap_usd": notional_usd,
        "p50": _loss_scenario(
            asset.stop_bps, fee_bps, asset.visible_cost.p50, funding_bps, notional_usd
        ),
        "p90": _loss_scenario(
            asset.stop_bps, fee_bps, asset.visible_cost.p90, funding_bps, notional_usd
        ),
        "p99": _loss_scenario(
            asset.stop_bps, fee_bps, asset.visible_cost.p99, funding_bps, notional_usd
        ),
        "p99_total_loss_pct_equity": (
            _total_loss_bps(asset, fee_bps, funding_bps, "p99")
            * notional_usd
            / 10_000.0
            / equity_usd
            * 100.0
        ),
    }


def _loss_scenario(
    stop_bps: float,
    fee_bps: float,
    visible_bps: float,
    funding_bps: float,
    notional_usd: float,
) -> dict[str, float]:
    total_bps = stop_bps + fee_bps + visible_bps + funding_bps
    return {
        "market_stop_loss_bps": stop_bps,
        "round_trip_taker_fee_bps": fee_bps,
        "adverse_exit_visible_cost_bps": visible_bps,
        "adverse_24h_funding_bps": funding_bps,
        "total_loss_bps": total_bps,
        "total_loss_usd": notional_usd * total_bps / 10_000.0,
    }


def _sizing_plan(
    equity: float,
    margin: float,
    leverage: float,
    capacity: int,
    asset_count: int,
) -> dict[str, float | int]:
    return {
        "target_equity_usd": equity,
        "margin_fraction_per_slot": margin,
        "leverage": leverage,
        "planned_margin_usd_per_slot": equity * margin,
        "planned_notional_usd_per_slot": equity * margin * leverage,
        "configured_assets": asset_count,
        "maximum_positions": capacity,
        "unused_capacity_slots": capacity - asset_count,
        "actual_roster_maximum_margin_fraction": asset_count * margin,
        "ten_slot_maximum_margin_fraction": capacity * margin,
    }


def _portfolio_stress(
    by_asset: dict[str, dict[str, object]],
    equity: float,
    margin_per_slot: float,
    capacity: int,
) -> dict[str, object]:
    actual = _portfolio_scenario(tuple(by_asset.values()), equity, margin_per_slot)
    synthetic = capacity - len(by_asset)
    capacity_row = _capacity_scenario(
        by_asset, actual, equity, margin_per_slot, capacity, synthetic
    )
    capacity_row["synthetic_slot_count"] = synthetic
    capacity_row["synthetic_slot_policy"] = "repeat_highest_loss_per_quantile"
    return {
        "configured_asset_roster": actual,
        "hypothetical_ten_slot_capacity": capacity_row,
    }


def _capacity_scenario(
    by_asset: dict[str, dict[str, object]],
    actual: dict[str, object],
    equity: float,
    margin_per_slot: float,
    capacity: int,
    synthetic: int,
) -> dict[str, object]:
    """Add each unused slot using the worst observed asset per quantile."""
    result = dict(actual)
    result["position_count"] = capacity
    for quantile in ("p50", "p90", "p99"):
        key = f"{quantile}_stop_wave_loss_usd"
        base = _numeric(result.get(key), key)
        worst = max(_loss(row, quantile) for row in by_asset.values())
        total = base + synthetic * worst
        result[key] = total
        result[f"{quantile}_stop_wave_loss_pct_equity"] = total / equity * 100.0
    result["isolated_margin_at_risk_usd"] = margin_per_slot * capacity
    result["isolated_margin_at_risk_pct_equity"] = (
        margin_per_slot * capacity / equity * 100.0
    )
    return result


def _portfolio_scenario(
    rows: Sequence[dict[str, object]],
    equity: float,
    margin_per_slot: float,
) -> dict[str, object]:
    result: dict[str, object] = {"position_count": len(rows)}
    for quantile in ("p50", "p90", "p99"):
        loss = sum(_loss(row, quantile) for row in rows)
        result[f"{quantile}_stop_wave_loss_usd"] = loss
        result[f"{quantile}_stop_wave_loss_pct_equity"] = loss / equity * 100.0
    result["isolated_margin_at_risk_usd"] = margin_per_slot * len(rows)
    result["isolated_margin_at_risk_pct_equity"] = (
        margin_per_slot * len(rows) / equity * 100.0
    )
    return result


def _repeated_wave_sensitivity(
    by_asset: dict[str, dict[str, object]],
    equity: float,
    capacity: int,
) -> dict[str, float]:
    rows = list(by_asset.values())
    while len(rows) < capacity:
        rows.append(max(by_asset.values(), key=lambda row: _loss(row, "p90")))
    one_wave = sum(_loss(row, "p90") for row in rows)
    return {
        "one_p90_wave_loss_usd": one_wave,
        "three_p90_waves_loss_usd": 3.0 * one_wave,
        "three_p90_waves_loss_pct_equity": 3.0 * one_wave / equity * 100.0,
        "five_p90_waves_loss_usd": 5.0 * one_wave,
        "five_p90_waves_loss_pct_equity": 5.0 * one_wave / equity * 100.0,
    }


def _loss(row: dict[str, object], quantile: str) -> float:
    scenario = row.get(quantile)
    if not isinstance(scenario, dict):
        raise ValueError(f"asset stress is missing {quantile}")
    value = scenario.get("total_loss_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"asset stress {quantile} loss must be numeric")
    return float(value)


def _numeric(value: object, label: str) -> float:
    """Return one finite numeric report field."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _total_loss_bps(
    asset: AssetGrowthStressInput,
    fee_bps: float,
    funding_bps: float,
    quantile: str,
) -> float:
    visible = getattr(asset.visible_cost, quantile)
    return asset.stop_bps + fee_bps + visible + funding_bps


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "performance_gate": False,
        "balance_gate": False,
        "profit_forecast": False,
    }


def _limitations() -> list[str]:
    return [
        "stop_gap_and_liquidation_execution_can_exceed_configured_stop_loss",
        "latest_hourly_funding_is_held_constant_for_24h_as_a_sensitivity_not_forecast",
        "visible_depth_excludes_queue_position_latency_and_adverse_selection",
        "simultaneous_stop_wave_is_deterministic_stress_not_a_correlation_estimate",
        "isolated_margin_at_risk_is_not_a_precise_liquidation_loss_forecast",
        "tenth_slot_is_hypothetical_until_a_tenth_asset_is_venue_qualified",
        "asset_liquidity_windows_are_not_synchronized",
        "no_joint_loss_probability_is_estimated",
    ]


def _positive(value: float, label: str) -> float:
    if isinstance(value, bool) or not isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return float(value)


def _nonnegative(value: float, label: str) -> float:
    if isinstance(value, bool) or not isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be nonnegative and finite")
    return float(value)


def _fraction(value: float, label: str) -> float:
    number = _positive(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must not exceed one")
    return number


def _unit_interval(value: float, label: str) -> float:
    if isinstance(value, bool) or not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return float(value)


def _positive_integer(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
