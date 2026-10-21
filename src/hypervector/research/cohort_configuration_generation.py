"""Read-only evidence comparing a live cohort with its current configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_configuration_exit_policy import (
    ProviderDirectionalExitExpectation,
    ProviderExitExpectation,
    provider_directional_exit_expectation,
    provider_directional_exit_policy_evidence,
    provider_exit_expectation,
    provider_exit_policy_evidence,
)


@dataclass(frozen=True)
class ConfigurationGenerationExpectation:
    """Non-secret identity of the configuration currently present on disk."""

    source_path: str
    source_modified_at_utc: str
    profile_fingerprint: str
    provider_execution_scopes: tuple[tuple[str, tuple[str, ...]], ...] = ()
    provider_observation_directions: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    provider_execution_directions: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    asset_sizing: tuple[tuple[str, float, float, float], ...] = ()
    asset_entry_slippage_caps: tuple[tuple[str, float], ...] = ()
    asset_market_slippage_caps: tuple[tuple[str, float], ...] = ()
    provider_sizing_overrides: tuple[tuple[str, str, float, float], ...] = ()
    provider_directional_sizing_overrides: tuple[
        tuple[str, str, str, float, float], ...
    ] = ()
    provider_exit_policies: tuple[ProviderExitExpectation, ...] = ()
    provider_directional_exit_policies: tuple[
        ProviderDirectionalExitExpectation, ...
    ] = ()


def load_configuration_expectation(
    config_path: Path,
) -> ConfigurationGenerationExpectation:
    """Load current non-secret config identity for one advisory comparison."""
    config = load_multi_asset_live_config(config_path, mode="observe")
    modified_at = datetime.fromtimestamp(
        config_path.stat().st_mtime,
        tz=timezone.utc,
    )
    return ConfigurationGenerationExpectation(
        source_path=str(config_path),
        source_modified_at_utc=modified_at.isoformat(),
        profile_fingerprint=config.profile_fingerprint,
        provider_execution_scopes=_provider_execution_scope_expectation(config),
        provider_observation_directions=_provider_observation_direction_expectation(
            config
        ),
        provider_execution_directions=_provider_execution_direction_expectation(config),
        asset_sizing=_asset_sizing_expectation(config),
        asset_entry_slippage_caps=_asset_entry_slippage_cap_expectation(config),
        asset_market_slippage_caps=_asset_market_slippage_cap_expectation(config),
        provider_sizing_overrides=_provider_sizing_expectation(config),
        provider_directional_sizing_overrides=_directional_sizing_expectation(config),
        provider_exit_policies=provider_exit_expectation(config),
        provider_directional_exit_policies=provider_directional_exit_expectation(
            config
        ),
    )


def _asset_sizing_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, float, float, float], ...]:
    return tuple(
        sorted(
            (
                asset.symbol,
                asset.leverage,
                asset.margin_fraction,
                asset.max_notional_usd,
            )
            for asset in config.assets
        )
    )


def _asset_market_slippage_cap_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, float], ...]:
    return tuple(
        sorted(
            (asset.symbol, asset.market_slippage_cap_fraction)
            for asset in config.assets
        )
    )


def _asset_entry_slippage_cap_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, float], ...]:
    return tuple(
        sorted(
            (asset.symbol, asset.effective_entry_slippage_cap_fraction)
            for asset in config.assets
        )
    )


def _provider_execution_scope_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        sorted(
            (
                provider.strategy_id,
                tuple(sorted(provider.execution_symbols)),
            )
            for provider in config.providers
        )
    )


def _provider_execution_direction_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    return tuple(
        sorted(
            (
                provider.strategy_id,
                symbol,
                tuple(sorted(provider.executable_sides(symbol))),
            )
            for provider in config.providers
            for symbol in provider.execution_symbols
        )
    )


def _provider_observation_direction_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    return tuple(
        sorted(
            (
                provider.strategy_id,
                symbol,
                tuple(sorted(provider.sides)),
            )
            for provider in config.providers
            for symbol in provider.symbols
        )
    )


def _provider_sizing_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, str, float, float], ...]:
    return tuple(
        sorted(
            (
                provider.strategy_id,
                symbol,
                sizing.margin_fraction,
                sizing.max_notional_usd,
            )
            for provider in config.providers
            for symbol, sizing in provider.sizing_overrides
        )
    )


def _directional_sizing_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, str, str, float, float], ...]:
    return tuple(
        sorted(
            (
                provider.strategy_id,
                symbol,
                side,
                sizing.margin_fraction,
                sizing.max_notional_usd,
            )
            for provider in config.providers
            for symbol, side, sizing in provider.directional_sizing_overrides
        )
    )


def configuration_generation_evidence(
    runtime_profile_fingerprint: str,
    expectation: ConfigurationGenerationExpectation,
    asset_health: Mapping[str, object],
) -> dict[str, object]:
    """Compare identities without restarting or changing strategy execution."""
    runtime = _required_text(runtime_profile_fingerprint, "runtime fingerprint")
    current = _required_text(expectation.profile_fingerprint, "current fingerprint")
    matches = runtime == current
    restart_state, blocking_assets = _restart_readiness(matches, asset_health)
    evidence: dict[str, object] = {
        "state": "current_runtime_configuration"
        if matches
        else "stale_runtime_configuration",
        "matches_runtime": matches,
        "runtime_profile_fingerprint": runtime,
        "current_profile_fingerprint": current,
        "source_path": _required_text(expectation.source_path, "config source path"),
        "source_modified_at_utc": _required_text(
            expectation.source_modified_at_utc,
            "config modification time",
        ),
        "current_asset_sizing": _asset_sizing_evidence(expectation.asset_sizing),
        "current_asset_entry_slippage_caps": _asset_market_slippage_cap_evidence(
            expectation.asset_entry_slippage_caps
        ),
        "current_asset_market_slippage_caps": _asset_market_slippage_cap_evidence(
            expectation.asset_market_slippage_caps
        ),
        "current_provider_sizing_overrides": _provider_sizing_override_evidence(
            expectation.provider_sizing_overrides
        ),
        "current_provider_directional_sizing_overrides": (
            _provider_directional_sizing_override_evidence(
                expectation.provider_directional_sizing_overrides
            )
        ),
        "current_provider_exit_policies": provider_exit_policy_evidence(
            expectation.provider_exit_policies
        ),
        "current_provider_directional_exit_policies": (
            provider_directional_exit_policy_evidence(
                expectation.provider_directional_exit_policies
            )
        ),
        "restart_state": restart_state,
        "blocking_assets": blocking_assets,
        "execution_authority": "none",
        "automatic_restart": False,
    }
    _attach_provider_scope_evidence(evidence, expectation)
    return evidence


def _attach_provider_scope_evidence(
    evidence: dict[str, object],
    expectation: ConfigurationGenerationExpectation,
) -> None:
    if expectation.provider_execution_scopes:
        evidence["current_provider_execution_scopes"] = (
            _provider_execution_scope_evidence(expectation.provider_execution_scopes)
        )
    if expectation.provider_observation_directions:
        evidence["current_provider_observation_directions"] = (
            _provider_execution_direction_evidence(
                expectation.provider_observation_directions
            )
        )
    if expectation.provider_execution_directions:
        evidence["current_provider_execution_directions"] = (
            _provider_execution_direction_evidence(
                expectation.provider_execution_directions
            )
        )


def _provider_execution_scope_evidence(
    scopes: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for strategy_id, raw_symbols in scopes:
        strategy = _required_text(strategy_id, "provider strategy")
        if "|" in strategy or strategy in evidence:
            raise ValueError("provider execution strategy identity is invalid")
        symbols = [
            _required_text(symbol, "provider execution symbol")
            for symbol in raw_symbols
        ]
        if any("|" in symbol for symbol in symbols) or len(symbols) != len(
            set(symbols)
        ):
            raise ValueError("provider execution symbols are invalid")
        evidence[strategy] = sorted(symbols)
    return evidence


def _provider_execution_direction_evidence(
    rows: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for strategy_id, symbol, raw_sides in rows:
        strategy = _required_text(strategy_id, "provider direction strategy")
        asset = _required_text(symbol, "provider direction symbol")
        sides = sorted(_required_text(side, "provider side") for side in raw_sides)
        if (
            "|" in strategy
            or "|" in asset
            or set(sides)
            not in (
                {"long"},
                {"short"},
                {"long", "short"},
            )
        ):
            raise ValueError("provider execution direction is invalid")
        key = f"{strategy}|{asset}"
        if key in evidence:
            raise ValueError("provider execution direction must be unique")
        evidence[key] = sides
    return evidence


def _asset_sizing_evidence(
    sizing: tuple[tuple[str, float, float, float], ...],
) -> dict[str, dict[str, float]]:
    evidence: dict[str, dict[str, float]] = {}
    for symbol, leverage, margin_fraction, max_notional_usd in sizing:
        asset = _required_text(symbol, "asset sizing symbol")
        lev = _finite_number(leverage, "asset leverage")
        margin = _finite_number(margin_fraction, "asset margin fraction")
        cap = _finite_number(max_notional_usd, "asset maximum notional")
        if "|" in asset or lev <= 0.0 or not 0.0 < margin <= 1.0 or cap <= 0.0:
            raise ValueError("asset sizing values are invalid")
        if asset in evidence:
            raise ValueError("asset sizing symbol must be unique")
        evidence[asset] = {
            "leverage": lev,
            "margin_fraction": margin,
            "max_notional_usd": cap,
        }
    return evidence


def _asset_market_slippage_cap_evidence(
    caps: tuple[tuple[str, float], ...],
) -> dict[str, float]:
    evidence: dict[str, float] = {}
    for symbol, market_slippage_cap_fraction in caps:
        asset = _required_text(symbol, "asset IOC cap symbol")
        cap = _finite_number(
            market_slippage_cap_fraction,
            "asset market slippage cap fraction",
        )
        if "|" in asset or not 0.0 <= cap <= 0.05:
            raise ValueError("asset market slippage cap is invalid")
        if asset in evidence:
            raise ValueError("asset IOC cap symbol must be unique")
        evidence[asset] = cap
    return evidence


def _provider_sizing_override_evidence(
    overrides: tuple[tuple[str, str, float, float], ...],
) -> dict[str, dict[str, float]]:
    evidence: dict[str, dict[str, float]] = {}
    for strategy_id, symbol, margin_fraction, max_notional_usd in overrides:
        strategy = _required_text(strategy_id, "provider sizing strategy")
        asset = _required_text(symbol, "provider sizing symbol")
        margin = _finite_number(margin_fraction, "provider margin fraction")
        cap = _finite_number(max_notional_usd, "provider maximum notional")
        if "|" in strategy or "|" in asset:
            raise ValueError("provider sizing identity must not contain '|'")
        if not 0.0 < margin <= 1.0 or cap <= 0.0:
            raise ValueError("provider sizing values are invalid")
        key = f"{strategy}|{asset}"
        if key in evidence:
            raise ValueError("provider sizing identity must be unique")
        evidence[key] = {
            "margin_fraction": margin,
            "max_notional_usd": cap,
        }
    return evidence


def _provider_directional_sizing_override_evidence(
    overrides: tuple[tuple[str, str, str, float, float], ...],
) -> dict[str, dict[str, float]]:
    evidence: dict[str, dict[str, float]] = {}
    for strategy_id, symbol, side, margin_fraction, max_notional_usd in overrides:
        strategy = _required_text(strategy_id, "directional sizing strategy")
        asset = _required_text(symbol, "directional sizing symbol")
        direction = _required_text(side, "directional sizing side")
        margin = _finite_number(margin_fraction, "directional margin fraction")
        cap = _finite_number(max_notional_usd, "directional maximum notional")
        if "|" in strategy or "|" in asset or direction not in {"long", "short"}:
            raise ValueError("directional sizing identity is invalid")
        if not 0.0 < margin <= 1.0 or cap <= 0.0:
            raise ValueError("directional sizing values are invalid")
        key = f"{strategy}|{asset}|{direction}"
        if key in evidence:
            raise ValueError("directional sizing identity must be unique")
        evidence[key] = {
            "margin_fraction": margin,
            "max_notional_usd": cap,
        }
    return evidence


def _restart_readiness(
    matches_runtime: bool,
    asset_health: Mapping[str, object],
) -> tuple[str, list[str]]:
    if matches_runtime:
        return "not_required_current_configuration", []
    if not asset_health:
        raise ValueError("asset health must not be empty")
    blockers = [
        symbol
        for symbol, raw in sorted(asset_health.items())
        if _asset_blocks_restart(symbol, raw)
    ]
    state = "wait_for_flat_and_no_orders" if blockers else "candidate_flat_no_orders"
    return state, blockers


def _asset_blocks_restart(symbol: str, value: object) -> bool:
    name = _required_text(symbol, "asset symbol")
    health = _mapping(value, f"{name} health")
    state = _required_object_text(health.get("final_state"), f"{name} state")
    size = _finite_number(health.get("position_size_signed"), f"{name} size")
    orders = health.get("open_order_ids")
    if not isinstance(orders, list) or any(
        isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0 for oid in orders
    ):
        raise ValueError(f"{name} open order ids must be positive integers")
    return state not in {"FLAT", "STOPPED"} or size != 0.0 or bool(orders)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _required_object_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    return _required_text(value, label)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _required_text(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
