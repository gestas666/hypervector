"""Report exact executable sizing and explicit simultaneous-loss sensitivities."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import math

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)

_BPS_PER_UNIT = 10_000.0
_PERCENT_PER_UNIT = 100.0


@dataclass(frozen=True)
class CapacityScenario:
    """Declared round-trip adverse costs, without an empirical probability."""

    name: str
    slippage_bps: float
    funding_bps: float

    def __post_init__(self) -> None:
        """Reject unnamed or invalid scenario assumptions."""
        if not self.name.strip():
            raise ValueError("capacity scenario name must be non-empty")
        _nonnegative(self.slippage_bps, "scenario slippage")
        _nonnegative(self.funding_bps, "scenario funding")


@dataclass(frozen=True)
class _Route:
    strategy_id: str
    symbol: str
    side: str
    notional_usd: float
    initial_margin_usd: float
    margin_fraction: float
    notional_cap_usd: float
    leverage: float
    stop_bps: float
    stop_basis: str
    one_way_taker_fee_bps: float


def build_executable_capacity(
    config: MultiAssetLiveConfig,
    equity_usd: float,
    one_way_taker_fees_bps: Mapping[str, float],
    *,
    scenarios: Sequence[CapacityScenario] | None = None,
) -> dict[str, object]:
    """Bound each metric independently across mutually exclusive symbol routes."""
    _positive(equity_usd, "equity")
    if scenarios is None:
        scenarios = (CapacityScenario("stop_and_fees", 0, 0),)
    if config.maximum_positions < 1:
        raise ValueError("capacity requires positive maximum_positions")
    if not scenarios or len({row.name for row in scenarios}) != len(scenarios):
        raise ValueError("capacity scenarios must be non-empty and uniquely named")
    assets = {asset.symbol: asset for asset in config.assets}
    routes = tuple(
        _route(provider, assets[symbol], side, equity_usd, one_way_taker_fees_bps)
        for provider in config.providers
        for symbol in provider.execution_symbols
        for side in sorted(provider.executable_sides(symbol))
    )
    covered = {row.symbol for row in routes}
    return {
        "schema_version": 1,
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "equity_usd": equity_usd,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "performance_gate": False,
            "runtime_strategy_changed": False,
        },
        "routes": [asdict(row) for row in routes],
        "uncovered_assets": [symbol for symbol in assets if symbol not in covered],
        "capacity": _capacity(routes, config.maximum_positions, equity_usd),
        "scenarios": [
            _scenario(row, routes, config.maximum_positions, equity_usd)
            for row in scenarios
        ],
        "limitations": _limitations(),
    }


def _route(
    provider: StrategyProviderConfig,
    asset: AssetLiveConfig,
    side: str,
    equity: float,
    fees: Mapping[str, float],
) -> _Route:
    if asset.symbol not in fees:
        raise ValueError(f"missing one-way taker fee: {asset.symbol}")
    fee = fees[asset.symbol]
    _nonnegative(fee, f"{asset.symbol} fee")
    sizing = provider.entry_sizing(asset.symbol, side) or CohortEntrySizing(
        asset.margin_fraction, asset.max_notional_usd
    )
    notional = sizing.planned_notional(
        account_value_usd=equity, leverage=asset.leverage
    )
    execution = provider.execution_for(asset.symbol, side)
    if execution.stop_policy == "fixed_bps":
        stop = execution.stop_bps
        basis = "provider_fixed_stop"
    elif execution.stop_policy == "structural_clamped_bps":
        stop = execution.maximum_stop_bps
        basis = "structural_stop_upper_sensitivity"
    else:
        raise ValueError(
            f"unsupported stop for capacity report: {provider.strategy_id}"
        )
    if stop is None:
        raise ValueError(f"missing stop for capacity report: {provider.strategy_id}")
    _positive(stop, "provider stop")
    return _Route(
        provider.strategy_id,
        asset.symbol,
        side,
        notional,
        notional / asset.leverage,
        sizing.margin_fraction,
        sizing.max_notional_usd,
        asset.leverage,
        stop,
        basis,
        fee,
    )


def _capacity(
    routes: tuple[_Route, ...], slots: int, equity: float
) -> dict[str, object]:
    margin = _bound(routes, slots, lambda row: row.initial_margin_usd)
    notional = _bound(routes, slots, lambda row: row.notional_usd)
    return {
        "bound_type": "independent_metric_maxima_one_position_per_symbol",
        "occupied_symbols": min(slots, len({row.symbol for row in routes})),
        "notional_usd": notional,
        "initial_margin_usd": margin,
        "initial_margin_pct_equity": margin / equity * _PERCENT_PER_UNIT,
        "gross_notional_to_equity": notional / equity,
        "long_notional_usd": _bound(
            routes, slots, lambda row: row.notional_usd if row.side == "long" else 0
        ),
        "short_notional_usd": _bound(
            routes, slots, lambda row: row.notional_usd if row.side == "short" else 0
        ),
    }


def _scenario(
    scenario: CapacityScenario,
    routes: tuple[_Route, ...],
    slots: int,
    equity: float,
) -> dict[str, object]:
    losses = {
        f"{row.strategy_id}|{row.symbol}|{row.side}": _loss(row, scenario)
        for row in routes
    }
    total = _bound(routes, slots, lambda row: _loss(row, scenario))
    return {
        **asdict(scenario),
        "loss_usd": total,
        "loss_pct_equity": total / equity * _PERCENT_PER_UNIT,
        "route_loss_usd": losses,
        "probability": None,
        "maximum_loss_claim": False,
    }


def _loss(route: _Route, scenario: CapacityScenario) -> float:
    cost_bps = (
        route.stop_bps
        + 2 * route.one_way_taker_fee_bps
        + scenario.slippage_bps
        + scenario.funding_bps
    )
    return route.notional_usd * cost_bps / _BPS_PER_UNIT


def _bound(
    routes: tuple[_Route, ...],
    slots: int,
    metric: Callable[[_Route], float],
) -> float:
    by_symbol: dict[str, float] = {}
    for row in routes:
        by_symbol[row.symbol] = max(by_symbol.get(row.symbol, 0.0), metric(row))
    return sum(sorted(by_symbol.values(), reverse=True)[:slots])


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _positive(value: float, label: str) -> None:
    _nonnegative(value, label)
    if value == 0:
        raise ValueError(f"{label} must be positive")


def _limitations() -> list[str]:
    return [
        "Static equity and entry notional; lot rounding and later equity changes omitted.",
        "Each metric is bounded independently; its maximizing routes may differ.",
        "All occupied symbols lose together in the scenarios; no probability is inferred.",
        "Slippage and funding are declared sensitivities, not measured tail quantiles.",
        "Stop gaps, liquidation, partial fills and changing exit notional can exceed these losses.",
        "IOC caps do not bound cumulative loss; failed exits can leave exposure open.",
        "No return forecast, correlation estimate, drawdown limit or execution gate is implied.",
    ]
