"""Configuration binding for all-asset breakout forward evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.research.cohort_breakout_policy_models import (
    BreakoutPolicyForwardSpec,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    payload,
    timestamp,
)

_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_MODELED_ROUND_TRIP_FRICTION_BPS = 13.0


def breakout_policy_forward_spec(
    source: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
    records: Sequence[Mapping[str, object]],
    *,
    run_id: str,
) -> BreakoutPolicyForwardSpec:
    """Bind one observer run to an unchanged wider breakout execution contract."""
    if source.mode != "observe" or candidate.mode != "observe":
        raise ValueError("breakout forward binding requires disarmed configurations")
    source_provider = _provider(source)
    candidate_provider = _provider(candidate)
    expected = replace(
        source_provider,
        execution_symbols=candidate_provider.execution_symbols,
    )
    if candidate_provider != expected:
        raise ValueError("candidate changes more than breakout execution scope")
    _validate_execution_contract(candidate_provider)
    identity = _runtime_identity(source, records, run_id)
    symbols = candidate_provider.execution_symbols
    assets = {asset.symbol: asset for asset in candidate.assets}
    notionals = {
        symbol: _notional(candidate_provider, symbol, assets[symbol].max_notional_usd)
        for symbol in symbols
    }
    execution = candidate_provider.execution
    hard_seconds = execution.hard_maximum_hold_seconds
    if hard_seconds is None:
        raise RuntimeError("validated extension unexpectedly lacks a hard hold")
    return BreakoutPolicyForwardSpec(
        source_strategy_id=_BREAKOUT,
        source_run_id=run_id,
        cutoff_time_ms=int(timestamp(identity).timestamp() * 1_000),
        symbols=symbols,
        source_execution_symbols=source_provider.execution_symbols,
        competing_execution_providers_by_symbol=_competing_providers(
            candidate, symbols
        ),
        stop_bps=float(execution.stop_bps or 0.0),
        soft_hold_minutes=execution.maximum_hold_seconds // 60,
        hard_hold_minutes=hard_seconds // 60,
        maximum_entry_delay_seconds=candidate_provider.maximum_entry_delay_seconds,
        modeled_round_trip_friction_bps=_MODELED_ROUND_TRIP_FRICTION_BPS,
        notional_usd_by_symbol=notionals,
    )


def _provider(config: MultiAssetLiveConfig) -> StrategyProviderConfig:
    matches = [value for value in config.providers if value.strategy_id == _BREAKOUT]
    if len(matches) != 1:
        raise ValueError("breakout provider must be unique")
    return matches[0]


def _competing_providers(
    config: MultiAssetLiveConfig, symbols: Sequence[str]
) -> dict[str, tuple[str, ...]]:
    output: dict[str, tuple[str, ...]] = {}
    for symbol in symbols:
        providers = tuple(
            value.strategy_id
            for value in config.providers
            if value.strategy_id != _BREAKOUT and symbol in value.execution_symbols
        )
        if providers:
            output[symbol] = providers
    return output


def _validate_execution_contract(provider: StrategyProviderConfig) -> None:
    execution = provider.execution
    if (
        not provider.execution_symbols
        or not set(provider.execution_symbols).issubset(provider.symbols)
        or provider.position_policy != "enter_and_close"
        or execution.entry_liquidity != "taker_ioc"
        or execution.stop_policy != "fixed_bps"
        or execution.stop_bps is None
        or execution.target_policy != "none"
        or execution.maximum_hold_policy != "extend_while_regime_supported"
        or execution.hard_maximum_hold_seconds is None
        or execution.maximum_hold_seconds % 60
        or execution.hard_maximum_hold_seconds % 60
    ):
        raise ValueError("breakout execution contract is unsupported by this audit")


def _runtime_identity(
    source: MultiAssetLiveConfig,
    records: Sequence[Mapping[str, object]],
    run_id: str,
) -> Mapping[str, object]:
    matches = [
        row
        for row in event_rows(records, "configuration_identity")
        if row.get("run_id") == run_id
    ]
    if len(matches) != 1:
        raise ValueError("source run configuration identity must be unique")
    identity = matches[0]
    if payload(identity).get("profile_fingerprint") != source.profile_fingerprint:
        raise ValueError("source run and observer profile fingerprints differ")
    return identity


def _notional(
    provider: StrategyProviderConfig,
    symbol: str,
    asset_notional: float,
) -> float:
    sizing = provider.entry_sizing(symbol)
    return sizing.max_notional_usd if sizing is not None else asset_notional
