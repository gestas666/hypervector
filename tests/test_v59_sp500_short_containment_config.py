"""Acceptance contract for the inactive SP500 short-containment successor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_V58 = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_V59 = Path(
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml"
)
_PROFILE = (
    "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59"
)
_SP500 = "xyz:SP500"
_ROUTE = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"


def test_v59_changes_only_profile_and_sp500_long_execution_authority() -> None:
    """Every V58 contract except SP500-long authority must remain exact."""
    baseline = _load(_V58)
    candidate = _load(_V59)

    assert candidate.profile_id == _PROFILE
    assert candidate.network == baseline.network == "mainnet"
    assert candidate.margin_mode == baseline.margin_mode == "isolated"
    assert candidate.maximum_positions == baseline.maximum_positions == 10
    assert candidate.cohort_ledger == baseline.cohort_ledger
    assert candidate.stop_file == baseline.stop_file
    assert candidate.poll_seconds == baseline.poll_seconds
    assert candidate.lookback_days == baseline.lookback_days
    assert _normalized_assets(candidate, baseline.profile_id) == baseline.assets
    assert _providers_except_sp500(candidate) == _providers_except_sp500(baseline)

    old_sp500 = _sp500_provider(baseline)
    new_sp500 = _sp500_provider(candidate)
    assert new_sp500 == replace(
        old_sp500,
        execution_side_overrides=((_SP500, frozenset({"short"})),),
    )


def test_v59_observes_both_sp500_sides_but_executes_only_short() -> None:
    """Containment must preserve long telemetry while removing long authority."""
    baseline = _load(_V58)
    candidate = _load(_V59)
    provider = _sp500_provider(candidate)
    long_direction = (_ROUTE, _SP500, "long")
    short_direction = (_ROUTE, _SP500, "short")

    assert provider.sides == frozenset({"long", "short"})
    assert provider.symbols == provider.execution_symbols == (_SP500,)
    assert provider.execution_side_overrides == ((_SP500, frozenset({"short"})),)
    assert long_direction in baseline.executable_provider_directions
    assert long_direction not in candidate.executable_provider_directions
    assert short_direction in candidate.executable_provider_directions
    assert baseline.executable_provider_directions - {long_direction} == (
        candidate.executable_provider_directions
    )


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _sp500_provider(config: MultiAssetLiveConfig) -> StrategyProviderConfig:
    return next(row for row in config.providers if row.strategy_id == _ROUTE)


def _providers_except_sp500(
    config: MultiAssetLiveConfig,
) -> tuple[StrategyProviderConfig, ...]:
    return tuple(row for row in config.providers if row.strategy_id != _ROUTE)


def _normalized_assets(
    candidate: MultiAssetLiveConfig,
    baseline_profile_id: str,
) -> tuple[object, ...]:
    return tuple(
        replace(asset, parent_profile_id=baseline_profile_id)
        for asset in candidate.assets
    )
