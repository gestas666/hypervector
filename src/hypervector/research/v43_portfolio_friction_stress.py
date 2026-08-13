"""Report-only full-roster friction stress for the proposed v43 profile."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class SlippageQuantile:
    """One nonnegative empirical adverse-slippage quantile."""

    sample_count: int
    p99_bps: float

    def __post_init__(self) -> None:
        """Reject missing or success-shaped empirical evidence."""
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count <= 0
        ):
            raise ValueError("slippage sample_count must be a positive integer")
        _nonnegative(self.p99_bps, "slippage p99_bps")


@dataclass(frozen=True)
class ExecutionFriction:
    """Observed entry, adverse-exit, and optional target-exit slippage."""

    entry: SlippageQuantile
    adverse_exit: SlippageQuantile
    target_exit: SlippageQuantile | None
    exit_evidence_scope: str

    def __post_init__(self) -> None:
        """Require an explicit exact-symbol or proxy evidence label."""
        if not self.exit_evidence_scope.strip():
            raise ValueError("exit_evidence_scope must be non-empty")


def build_v43_portfolio_friction_stress(
    profile: Path,
    *,
    venue_stress_path: Path,
    execution_friction: Mapping[str, Record],
    account_values_usd: Sequence[float],
    schema_version: str = "v43_portfolio_friction_stress_v1",
    visible_depth_p99_bps: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Stress every specialist asset slot without granting execution authority."""
    config = load_multi_asset_live_config(profile, mode="observe")
    venue = _mapping(json.loads(venue_stress_path.read_text()), "venue stress")
    accounts = _account_values(account_values_usd)
    friction = _execution_rows(config, execution_friction)
    depth_overrides = _depth_overrides(config, visible_depth_p99_bps)
    return {
        "schema_version": _schema_version(schema_version),
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "contract": _contract(),
        "visible_depth_contract": _depth_contract(depth_overrides),
        "scenarios": [
            _scenario(config, venue, friction, depth_overrides, account)
            for account in accounts
        ],
        "limitations": _limitations(),
    }


def _scenario(
    config: MultiAssetLiveConfig,
    venue: Record,
    friction: Mapping[str, ExecutionFriction],
    depth_overrides: Mapping[str, float] | None,
    account: float,
) -> dict[str, object]:
    slots = {
        asset.symbol: _asset_slot(
            config,
            asset,
            venue,
            friction[asset.symbol],
            None if depth_overrides is None else depth_overrides[asset.symbol],
            account,
        )
        for asset in config.assets
    }
    wave = sum(
        _number(row["stacked_p99_slot_loss_usd"], "slot loss") for row in slots.values()
    )
    return {
        "account_value_usd": account,
        "maximum_simultaneous_positions": len(slots),
        "account_position_capacity": config.maximum_positions,
        "route_aware_maximum_margin_fraction": sum(
            _number(row["maximum_margin_fraction"], "slot margin")
            for row in slots.values()
        ),
        "asset_slots": slots,
        "stacked_p99_stop_wave_loss_usd": wave,
        "stacked_p99_stop_wave_loss_pct_equity": wave / account * 100.0,
    }


def _asset_slot(
    config: MultiAssetLiveConfig,
    asset: AssetLiveConfig,
    venue: Record,
    friction: ExecutionFriction,
    depth_override: float | None,
    account: float,
) -> dict[str, object]:
    providers = tuple(row for row in config.providers if asset.symbol in row.symbols)
    if not providers:
        raise ValueError(f"{asset.symbol} has no executable provider")
    venue_row = _venue_row(venue, asset.symbol)
    routes = tuple(
        _route(asset, provider, venue_row, friction, depth_override, account)
        for provider in providers
    )
    worst = max(
        routes, key=lambda row: _number(row["stacked_p99_stop_loss_usd"], "route loss")
    )
    return {
        "simultaneous_route_count": 1,
        "maximum_margin_fraction": max(
            _number(row["margin_fraction"], "route margin") for row in routes
        ),
        "routes": routes,
        "stacked_p99_slot_loss_usd": worst["stacked_p99_stop_loss_usd"],
        "worst_route_strategy_id": worst["strategy_id"],
    }


def _route(
    asset: AssetLiveConfig,
    provider: StrategyProviderConfig,
    venue: Record,
    friction: ExecutionFriction,
    depth_override: float | None,
    account: float,
) -> dict[str, object]:
    sizing = provider.entry_sizing(asset.symbol) or CohortEntrySizing(
        asset.margin_fraction, asset.max_notional_usd
    )
    notional = sizing.planned_notional(
        account_value_usd=account, leverage=asset.leverage
    )
    execution = provider.execution_for(asset.symbol)
    stop = _stop_bps(provider.strategy_id, execution)
    maximum_hold_hours = _maximum_hold_hours(provider.strategy_id, execution)
    components = _components(venue, friction, depth_override, maximum_hold_hours)
    stacked_stop_bps = stop + sum(components.values())
    payload: dict[str, object] = {
        "strategy_id": provider.strategy_id,
        "sides": sorted(provider.executable_sides(asset.symbol)),
        "margin_fraction": sizing.margin_fraction,
        "planned_notional_usd": notional,
        "maximum_hold_hours": maximum_hold_hours,
        "stop_bps": stop,
        "friction_components_bps": components,
        "stacked_p99_stop_loss_bps": stacked_stop_bps,
        "stacked_p99_stop_loss_usd": notional * stacked_stop_bps / 10_000.0,
        "execution_friction": _friction_payload(friction),
    }
    payload.update(
        _target_payload(
            provider.strategy_id,
            execution,
            friction,
            venue,
            notional,
            stacked_stop_bps,
        )
    )
    return payload


def _components(
    venue: Record,
    friction: ExecutionFriction,
    depth_override: float | None,
    maximum_hold_hours: float,
) -> dict[str, float]:
    p99 = _mapping(venue.get("p99"), "venue p99")
    depth = (
        _number(p99.get("adverse_exit_visible_cost_bps"), "depth")
        if depth_override is None
        else depth_override
    )
    return {
        "round_trip_taker_fee": _number(venue.get("round_trip_taker_fee_bps"), "fee"),
        "adverse_maximum_hold_funding": _number(
            venue.get("adverse_24h_funding_bps"), "funding"
        )
        * maximum_hold_hours
        / 24.0,
        "visible_depth_p99": depth,
        "live_entry_slippage_p99": friction.entry.p99_bps,
        "live_adverse_exit_slippage_p99": friction.adverse_exit.p99_bps,
    }


def _maximum_hold_hours(
    strategy_id: str,
    execution: ProviderExecutionContract,
) -> float:
    """Return the longest automatic provider lifecycle in hours."""
    seconds = execution.hard_maximum_hold_seconds or execution.maximum_hold_seconds
    if seconds is None or seconds <= 0:
        raise ValueError(f"{strategy_id} maximum hold must be positive")
    return seconds / 3_600.0


def _target_payload(
    strategy_id: str,
    execution: ProviderExecutionContract,
    friction: ExecutionFriction,
    venue: Record,
    notional: float,
    stop_loss_bps: float,
) -> dict[str, object]:
    target = _target_bps(strategy_id, execution)
    if target is None:
        return {"target_bps": None, "friction_adjusted_breakeven_win_rate": None}
    if friction.target_exit is None:
        raise ValueError(f"{strategy_id} requires target-exit friction")
    p99 = _mapping(venue.get("p99"), "venue p99")
    costs = (
        _number(venue.get("round_trip_taker_fee_bps"), "fee")
        + _number(p99.get("adverse_exit_visible_cost_bps"), "depth")
        + friction.entry.p99_bps
        + friction.target_exit.p99_bps
    )
    net_bps = target - costs
    net_usd = notional * net_bps / 10_000.0
    breakeven = None if net_bps <= 0.0 else stop_loss_bps / (stop_loss_bps + net_bps)
    return {
        "target_bps": target,
        "stacked_target_net_before_funding_bps": net_bps,
        "stacked_target_net_before_funding_usd": net_usd,
        "friction_adjusted_breakeven_win_rate": breakeven,
    }


def _stop_bps(strategy_id: str, execution: ProviderExecutionContract) -> float:
    value = execution.maximum_stop_bps or execution.stop_bps
    return _positive(value, f"{strategy_id} stop")


def _target_bps(
    strategy_id: str,
    execution: ProviderExecutionContract,
) -> float | None:
    if execution.target_bps is not None:
        return _positive(execution.target_bps, f"{strategy_id} target")
    if execution.target_r_multiple is None:
        return None
    return _stop_bps(strategy_id, execution) * _positive(
        execution.target_r_multiple, f"{strategy_id} target R"
    )


def _venue_row(venue: Record, symbol: str) -> Record:
    rows = _mapping(venue.get("by_asset"), "venue by_asset")
    row = rows.get(symbol)
    if row is None:
        raise ValueError(f"venue stress is missing {symbol}")
    return _mapping(row, f"venue stress {symbol}")


def _execution_rows(
    config: MultiAssetLiveConfig, rows: Mapping[str, Record]
) -> dict[str, ExecutionFriction]:
    missing = set(config.symbols).difference(rows)
    if missing:
        raise ValueError("missing execution friction for " + ", ".join(sorted(missing)))
    return {symbol: _execution_row(rows[symbol], symbol) for symbol in config.symbols}


def _execution_row(row: Record, symbol: str) -> ExecutionFriction:
    target_value = row.get("target_exit")
    target = None
    if target_value is not None:
        target_row = _mapping(target_value, f"{symbol} target exit")
        count = target_row.get("sample_count")
        if count != 0:
            target = _slippage(target_row, f"{symbol} target exit")
    scope = row.get("exit_evidence_scope")
    if not isinstance(scope, str):
        raise ValueError(f"{symbol} exit_evidence_scope must be text")
    return ExecutionFriction(
        entry=_slippage(
            _mapping(row.get("entry"), f"{symbol} entry"), f"{symbol} entry"
        ),
        adverse_exit=_slippage(
            _mapping(row.get("adverse_exit"), f"{symbol} adverse exit"),
            f"{symbol} adverse exit",
        ),
        target_exit=target,
        exit_evidence_scope=scope,
    )


def _slippage(row: Record, label: str) -> SlippageQuantile:
    count = row.get("sample_count")
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError(f"{label} sample_count must be an integer")
    return SlippageQuantile(count, _number(row.get("p99_bps"), f"{label} p99"))


def _friction_payload(value: ExecutionFriction) -> dict[str, object]:
    return {
        "entry_sample_count": value.entry.sample_count,
        "adverse_exit_sample_count": value.adverse_exit.sample_count,
        "target_exit_sample_count": (
            None if value.target_exit is None else value.target_exit.sample_count
        ),
        "exit_evidence_scope": value.exit_evidence_scope,
    }


def _depth_overrides(
    config: MultiAssetLiveConfig,
    values: Mapping[str, float] | None,
) -> dict[str, float] | None:
    if values is None:
        return None
    if set(values) != set(config.symbols):
        raise ValueError("visible-depth overrides must exactly match profile symbols")
    return {
        symbol: _nonnegative(values[symbol], f"{symbol} visible-depth p99")
        for symbol in config.symbols
    }


def _depth_contract(values: Mapping[str, float] | None) -> dict[str, object]:
    if values is None:
        return {
            "source": "venue_stress_asset_curve",
            "p99_bps_by_asset": None,
        }
    return {
        "source": "explicit_candidate_notional_override",
        "p99_bps_by_asset": dict(values),
    }


def _account_values(values: Sequence[float]) -> tuple[float, ...]:
    output = tuple(_positive(value, "account value") for value in values)
    if not output or len(set(output)) != len(output):
        raise ValueError("account values must be non-empty and unique")
    return output


def _schema_version(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("schema_version must be non-empty text")
    return value


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "performance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "stacked depth and realized slippage can double-count one execution cost",
        "p99 components are marginal quantiles, not a joint loss probability",
        "small live samples make empirical p99 estimates unstable",
        "funding linearly scales a frozen adverse 24h sensitivity to each route's "
        "maximum hold and is not a funding forecast",
        "SP500 adverse-exit slippage uses an explicitly labeled SPCX provider proxy",
        "stop gaps and venue outages can exceed every modeled stop-wave loss",
        "strategy edge and signal frequency are not established by sizing arithmetic",
    ]
