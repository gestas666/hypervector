"""Scaled-account depth and fee evidence for HIP-3 oil research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution

Record = Mapping[str, object]

_NORMALIZED_EQUITY_USD = 500.0
_NORMALIZED_NOTIONAL_USD = 75.0
_SCALED_EQUITY_USD = 5_000.0
_SCALED_NOTIONAL_USD = 750.0
_NOMINAL_LATENCY_BPS_PER_SIDE = 1.0
_STRESS_LATENCY_BPS_PER_SIDE = 2.0


@dataclass(frozen=True)
class Hip3OilFrictionContract:
    """Auditable normalized replay mapped to one scaled live hypothesis."""

    execution: MuArchiveExecution
    normalized_equity_usd: float
    scaled_equity_usd: float
    scaled_notional_usd: float
    spread_p90_bps: float
    spread_p99_bps: float
    visible_p90_bps: float
    visible_p99_bps: float
    nominal_depth_impact_bps_per_side: float
    stress_depth_impact_bps_per_side: float
    live_stress_floor_bps_per_side: float | None = None
    live_slippage_observations: int = 0


def build_hip3_oil_friction_contract(
    *,
    symbol: str,
    venue_max_leverage: float,
    fee_profile: Record,
    liquidity_profile: Record,
    live_stress_floor_bps_per_side: float | None = None,
    live_slippage_observations: int = 0,
) -> Hip3OilFrictionContract:
    """Bind exact-symbol fees and scaled depth without double-counting BBO."""
    _require_symbol(fee_profile, symbol, "fee profile")
    _require_symbol(liquidity_profile, symbol, "liquidity profile")
    scaled_notional = _SCALED_NOTIONAL_USD
    fees = _mapping(fee_profile.get("fees"), "fee evidence")
    fee_rate = _positive(fees.get("effective_taker_rate"), "effective taker rate")
    spread = _mapping(liquidity_profile.get("spread_bps"), "spread evidence")
    notional = _scaled_notional(liquidity_profile, scaled_notional)
    visible = _mapping(
        notional.get("round_trip_visible_cost_bps"), "visible cost evidence"
    )
    p90_spread, p99_spread = _quantiles(spread, "spread")
    p90_visible, p99_visible = _quantiles(visible, "visible cost")
    nominal_depth = max((p90_visible - p90_spread) / 2.0, 0.0)
    stress_depth = max((p99_visible - p99_spread) / 2.0, nominal_depth)
    stress_floor = _stress_floor(
        live_stress_floor_bps_per_side, live_slippage_observations
    )
    execution = _archive_execution(
        symbol,
        venue_max_leverage,
        fee_rate,
        nominal_depth,
        stress_depth,
        stress_floor,
    )
    return Hip3OilFrictionContract(
        execution,
        _NORMALIZED_EQUITY_USD,
        _SCALED_EQUITY_USD,
        scaled_notional,
        p90_spread,
        p99_spread,
        p90_visible,
        p99_visible,
        nominal_depth,
        stress_depth,
        live_stress_floor_bps_per_side,
        live_slippage_observations,
    )


def _archive_execution(
    symbol: str,
    venue_max_leverage: float,
    fee_rate: float,
    nominal_depth: float,
    stress_depth: float,
    stress_floor: float,
) -> MuArchiveExecution:
    stress = max(_STRESS_LATENCY_BPS_PER_SIDE + stress_depth, stress_floor)
    return MuArchiveExecution(
        fee_rate,
        _NORMALIZED_NOTIONAL_USD,
        _positive(venue_max_leverage, "venue maximum leverage"),
        _NOMINAL_LATENCY_BPS_PER_SIDE + nominal_depth,
        stress,
        0.0,
        maximum_hold_bars=288,
        symbol=symbol,
    )


def observed_live_slippage_floor(
    report: Record, expected_symbol: str
) -> tuple[float, int]:
    """Return the maximum absolute live slippage as a sparse stress floor."""
    _require_symbol(report, expected_symbol, "live execution report")
    if report.get("execution_authority") != "none":
        raise ValueError("live execution report must have zero execution authority")
    lifecycles = report.get("lifecycles")
    if not isinstance(lifecycles, Sequence) or isinstance(lifecycles, (str, bytes)):
        raise ValueError("live execution lifecycles must be a sequence")
    values: list[float] = []
    for lifecycle in lifecycles:
        row = _mapping(lifecycle, "live execution lifecycle")
        for role in ("entry", "exit"):
            event = _mapping(row.get(role), f"live {role}")
            values.append(abs(_number(event.get("slippage_bps"), "live slippage")))
    if not values:
        raise ValueError("live execution report contains no slippage observations")
    return max(values), len(values)


def _scaled_notional(profile: Record, expected: float) -> Record:
    rows = profile.get("notionals")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("liquidity notionals must be a sequence")
    matches = [
        _mapping(row, "liquidity notional")
        for row in rows
        if isinstance(row, Mapping)
        and math.isclose(_number(row.get("notional_usd"), "notional"), expected)
    ]
    if len(matches) != 1:
        raise ValueError(f"liquidity evidence requires exact ${expected:.0f} notional")
    if _number(matches[0].get("both_complete_rate"), "completion rate") != 1.0:
        raise ValueError("scaled oil depth must be complete on both sides")
    return matches[0]


def _stress_floor(value: float | None, observations: int) -> float:
    if value is None:
        if observations != 0:
            raise ValueError("live slippage observations require a stress floor")
        return 0.0
    floor = _nonnegative(value, "live stress floor")
    if (
        isinstance(observations, bool)
        or not isinstance(observations, int)
        or observations <= 0
    ):
        raise ValueError("live slippage observations must be a positive integer")
    return floor


def _quantiles(values: Record, label: str) -> tuple[float, float]:
    p90 = _nonnegative(values.get("p90"), f"{label} p90")
    p99 = _nonnegative(values.get("p99"), f"{label} p99")
    if p99 < p90:
        raise ValueError(f"{label} p99 cannot be below p90")
    return p90, p99


def _require_symbol(values: Record, expected: str, label: str) -> None:
    if values.get("symbol") != expected:
        raise ValueError(f"{label} symbol does not match {expected}")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative(value: object, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
