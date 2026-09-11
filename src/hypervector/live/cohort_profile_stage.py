"""Validate and atomically publish a disarmed next-run cohort profile."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_profit_lock_override import CohortProfitLockOverride
from hypervector.live.cohort_operator_commands import CohortProfileSettings
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)


def stage_cohort_profile(
    *,
    config: MultiAssetLiveConfig,
    settings: CohortProfileSettings,
    output_path: Path,
) -> str:
    """Validate full staged settings and publish one restart-only TOML profile."""
    candidate = _candidate(config, settings, output_path)
    validate_multi_asset_live_config(candidate)
    content = _toml(candidate)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        serialized = load_multi_asset_live_config(temporary, mode="observe")
        if serialized.profile_fingerprint != candidate.profile_fingerprint:
            raise ValueError("staged serialization changed the profile fingerprint")
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return (
        f"staged profile written to {output_path}; apply only by disarmed restart; "
        f"fingerprint {candidate.profile_fingerprint[:12]}"
    )


def _candidate(
    config: MultiAssetLiveConfig,
    settings: CohortProfileSettings,
    output_path: Path,
) -> MultiAssetLiveConfig:
    assets = _assets(config, settings)
    providers = _providers(config, settings)
    return replace(
        config,
        profile_id=f"{config.profile_id}_staged",
        source_path=output_path,
        maximum_positions=settings.maximum_positions,
        poll_seconds=settings.poll_seconds,
        assets=assets,
        providers=providers,
        mode="observe",
        enabled=False,
        accepts_live_risk=False,
        transition_approval=None,
    )


def _assets(
    config: MultiAssetLiveConfig,
    settings: CohortProfileSettings,
) -> tuple[AssetLiveConfig, ...]:
    by_symbol = {asset.symbol: asset for asset in settings.assets}
    if set(by_symbol) != set(config.symbols) or len(by_symbol) != len(settings.assets):
        raise ValueError("staged assets must cover every configured symbol exactly")
    return tuple(
        replace(
            asset,
            parent_profile_id=f"{config.profile_id}_staged",
            leverage=by_symbol[asset.symbol].leverage,
            margin_fraction=by_symbol[asset.symbol].margin_fraction,
            max_notional_usd=by_symbol[asset.symbol].max_notional_usd,
            stop_bps=by_symbol[asset.symbol].stop_bps,
            maximum_hold_seconds=by_symbol[asset.symbol].maximum_hold_seconds,
            mode="observe",
            enabled=False,
            accepts_live_risk=False,
        )
        for asset in config.assets
    )


def _providers(
    config: MultiAssetLiveConfig,
    settings: CohortProfileSettings,
) -> tuple[StrategyProviderConfig, ...]:
    by_id = {provider.strategy_id: provider for provider in settings.providers}
    expected = {provider.strategy_id for provider in config.providers}
    if set(by_id) != expected or len(by_id) != len(settings.providers):
        raise ValueError(
            "staged providers must cover every configured provider exactly"
        )
    return tuple(
        replace(
            provider,
            execution_symbols=by_id[provider.strategy_id].execution_symbols,
        )
        for provider in config.providers
    )


def _toml(config: MultiAssetLiveConfig) -> str:
    lines = [
        f"profile = {_quoted(config.profile_id)}",
        f"network = {_quoted(config.network)}",
        f"margin_mode = {_quoted(config.margin_mode)}",
        f"maximum_positions = {config.maximum_positions}",
        "",
        "[runtime]",
        f"cohort_ledger = {_quoted(str(config.cohort_ledger))}",
        f"stop_file = {_quoted(str(config.stop_file))}",
        f"poll_seconds = {config.poll_seconds}",
        f"lookback_days = {config.lookback_days}",
    ]
    for asset in config.assets:
        lines.extend(_asset_toml(asset))
    for provider in config.providers:
        lines.extend(_provider_toml(provider))
    return "\n".join(lines) + "\n"


def _asset_toml(asset: AssetLiveConfig) -> list[str]:
    lines = [
        "",
        "[[assets]]",
        f"symbol = {_quoted(asset.symbol)}",
        f"sides = {_strings(tuple(sorted(asset.sides)))}",
        f"leverage = {asset.leverage}",
        f"venue_max_leverage = {asset.venue_max_leverage}",
        f"margin_fraction = {asset.margin_fraction}",
        f"max_notional_usd = {asset.max_notional_usd}",
        f"market_slippage_cap_fraction = {asset.market_slippage_cap_fraction}",
        f"stop_bps = {asset.stop_bps}",
        f"maximum_hold_seconds = {asset.maximum_hold_seconds}",
    ]
    if asset.entry_slippage_cap_fraction is not None:
        lines.append(f"entry_slippage_cap_fraction = {asset.entry_slippage_cap_fraction}")
    return lines


def _provider_toml(provider: StrategyProviderConfig) -> list[str]:
    lines = [
        "",
        "[[providers]]",
        f"strategy_id = {_quoted(provider.strategy_id)}",
        f"symbols = {_strings(provider.symbols)}",
        f"sides = {_strings(tuple(sorted(provider.sides)))}",
        f"priority = {provider.priority}",
        f"timeframe = {_quoted(provider.timeframe)}",
        f"maximum_entry_delay_seconds = {provider.maximum_entry_delay_seconds}",
        f"execution_symbols = {_strings(provider.execution_symbols)}",
        f"position_policy = {_quoted(provider.position_policy)}",
        f"execution = {_inline_table(provider.execution.as_payload())}",
    ]
    if provider.source_profile is not None:
        lines.append(f"source_profile = {_quoted(str(provider.source_profile))}")
    if provider.execution_side_overrides:
        lines.append(
            "execution_side_overrides = "
            + _side_override_table(provider.execution_side_overrides)
        )
    if provider.entry_context_overrides:
        lines.append(
            "entry_context_overrides = "
            + _entry_context_override_table(provider.entry_context_overrides)
        )
    if provider.stop_bps_overrides:
        lines.append(
            "stop_bps_overrides = "
            + _number_override_table(provider.stop_bps_overrides)
        )
    if provider.sizing_overrides:
        lines.append(
            "sizing_overrides = " + _sizing_override_table(provider.sizing_overrides)
        )
    if provider.directional_sizing_overrides:
        lines.append(
            "directional_sizing_overrides = "
            + _directional_sizing_override_table(provider.directional_sizing_overrides)
        )
    if provider.profit_lock_overrides:
        lines.append(
            "profit_lock_overrides = "
            + _profit_lock_override_table(provider.profit_lock_overrides)
        )
    return lines


def _quoted(value: str) -> str:
    return json.dumps(value)


def _strings(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_quoted(value) for value in values) + "]"


def _inline_table(values: dict[str, object]) -> str:
    fields = []
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool):
            token = str(value).lower()
        elif isinstance(value, str):
            token = _quoted(value)
        else:
            token = str(value)
        fields.append(f"{key} = {token}")
    return "{ " + ", ".join(fields) + " }"


def _side_override_table(
    values: tuple[tuple[str, frozenset[str]], ...],
) -> str:
    fields = (
        f"{symbol} = {_strings(tuple(sorted(sides)))}" for symbol, sides in values
    )
    return "{ " + ", ".join(fields) + " }"


def _entry_context_override_table(values: tuple[tuple[str, str], ...]) -> str:
    fields = (f"{symbol} = {_quoted(policy)}" for symbol, policy in values)
    return "{ " + ", ".join(fields) + " }"


def _number_override_table(values: tuple[tuple[str, float], ...]) -> str:
    fields = (f"{symbol} = {number}" for symbol, number in values)
    return "{ " + ", ".join(fields) + " }"


def _sizing_override_table(
    values: tuple[tuple[str, CohortEntrySizing], ...],
) -> str:
    fields = (
        f"{symbol} = {_inline_table(sizing.as_payload())}" for symbol, sizing in values
    )
    return "{ " + ", ".join(fields) + " }"


def _directional_sizing_override_table(
    values: tuple[tuple[str, str, CohortEntrySizing], ...],
) -> str:
    grouped: dict[str, list[tuple[str, CohortEntrySizing]]] = {}
    for symbol, side, sizing in values:
        grouped.setdefault(symbol, []).append((side, sizing))
    symbols = []
    for symbol, sides in grouped.items():
        policies = ", ".join(
            f"{side} = {_inline_table(sizing.as_payload())}" for side, sizing in sides
        )
        symbols.append(f"{symbol} = {{ {policies} }}")
    return "{ " + ", ".join(symbols) + " }"


def _profit_lock_override_table(
    values: tuple[CohortProfitLockOverride, ...],
) -> str:
    grouped: dict[str, list[CohortProfitLockOverride]] = {}
    for override in values:
        grouped.setdefault(override.symbol, []).append(override)
    symbols = []
    for symbol, overrides in grouped.items():
        sides = ", ".join(
            f"{row.side} = {_inline_table(row.as_payload())}" for row in overrides
        )
        symbols.append(f"{symbol} = {{ {sides} }}")
    return "{ " + ", ".join(symbols) + " }"
