"""Strict configuration for a shared multi-asset bidirectional canary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Literal

from hypervector.live.cohort_entry_sizing import (
    CohortEntrySizing,
    provider_directional_sizing_overrides as _provider_directional_sizing_overrides,
    provider_sizing_overrides as _provider_sizing_overrides,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_profit_lock_override import (
    CohortProfitLockOverride,
    provider_profit_lock_overrides as _provider_profit_lock_overrides,
)
from hypervector.live.multi_asset_live_config_parsing import (
    MultiAssetLiveConfigError,
    entry_context_overrides as _entry_context_overrides,
    integer as _integer,
    load_toml as _load_toml,
    mapping as _mapping,
    mapping_rows as _mapping_rows,
    number as _number,
    optional_number as _optional_number,
    optional_path as _optional_path,
    optional_strings as _optional_strings,
    positive_number_overrides as _positive_number_overrides,
    provider_position_policy as _provider_position_policy,
    require_known_keys as _require_known_keys,
    require_live_start as _require_live,
    side_overrides as _side_overrides,
    sides as _sides,
    strings as _strings,
    text as _text,
)
from hypervector.live.multi_asset_live_identity import stable_fingerprint
from hypervector.live.multi_asset_live_profile_values import (
    asset_profile_values as _asset_profile_values,
    provider_profile_values as _provider_profile_values,
)
from hypervector.live.multi_asset_live_provider_validation import (
    validate_provider_scope as _validate_provider_scope,
)
from hypervector.live.perp_venue_identity import parse_perp_venue_identity

LiveMode = Literal["observe", "live"]
_BOTH_SIDES = frozenset({"long", "short"})
# Every key the loader consumes; any other key is refused so a typo cannot
# silently fall back to a default. A checked-in profile key that is read by
# another consumer must be added here with a comment naming that consumer.
_TOP_LEVEL_KEYS = frozenset(
    {
        "profile",
        "network",
        "margin_mode",
        "maximum_positions",
        "runtime",
        "assets",
        "providers",
    }
)
_RUNTIME_KEYS = frozenset(
    {
        "cohort_ledger",
        "stop_file",
        "poll_seconds",
        "lookback_days",
        "transition_approval",
    }
)
_ASSET_KEYS = frozenset(
    {
        "symbol",
        "sides",
        "leverage",
        "venue_max_leverage",
        "margin_fraction",
        "max_notional_usd",
        "market_slippage_cap_fraction",
        "stop_bps",
        "maximum_hold_seconds",
        "entry_slippage_cap_fraction",
    }
)
_PROVIDER_KEYS = frozenset(
    {
        "strategy_id",
        "symbols",
        "sides",
        "priority",
        "timeframe",
        "maximum_entry_delay_seconds",
        "execution_symbols",
        "execution",
        "source_profile",
        "execution_side_overrides",
        "entry_context_overrides",
        "stop_bps_overrides",
        "sizing_overrides",
        "directional_sizing_overrides",
        "profit_lock_overrides",
        "position_policy",
    }
)
_EXECUTION_KEYS = frozenset(field.name for field in fields(ProviderExecutionContract))


@dataclass(frozen=True)
class AssetLiveConfig:
    """One symbol's bidirectional execution and protection envelope."""

    parent_profile_id: str
    network: str
    margin_mode: str
    symbol: str
    sides: frozenset[str]
    leverage: float
    venue_max_leverage: float
    margin_fraction: float
    max_notional_usd: float
    market_slippage_cap_fraction: float
    stop_bps: float
    maximum_hold_seconds: int
    live_ledger: Path
    mode: LiveMode
    enabled: bool
    accepts_live_risk: bool
    entry_slippage_cap_fraction: float | None = None
    strategy_id: str = "multi_strategy_bidirectional_router"
    max_positions_per_symbol: int = 1
    capital_source: str = "shared_live_account"
    portfolio_purpose: str = "multi_asset_canary_validation"
    metalabel_mode: str = "observe"

    @property
    def profile_id(self) -> str:
        """Return the symbol-specific immutable profile identity."""
        return f"{self.parent_profile_id}_{self.symbol.lower()}"

    @property
    def authoritative_ledger(self) -> Path:
        """Return the only symbol ledger owned by the live engine."""
        return self.live_ledger

    @property
    def effective_entry_slippage_cap_fraction(self) -> float:
        """Return the opening IOC cap, falling back to the legacy shared cap."""
        if self.entry_slippage_cap_fraction is None:
            return self.market_slippage_cap_fraction
        return self.entry_slippage_cap_fraction

    @property
    def profile_fingerprint(self) -> str:
        """Hash stable symbol execution settings without live flags."""
        return stable_fingerprint(_asset_profile_values(self))

    @property
    def run_fingerprint(self) -> str:
        """Hash the profile with the requested authority mode."""
        return stable_fingerprint(
            {"profile_fingerprint": self.profile_fingerprint, "mode": self.mode}
        )

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Apply the same independent fail-closed gates as the parent cohort."""
        _require_live(
            mode=self.mode,
            enabled=self.enabled,
            accepts_live_risk=self.accepts_live_risk,
            credentials_present=credentials_present,
        )


@dataclass(frozen=True)
class StrategyProviderConfig:
    """One attributed bidirectional intent source and explicit priority."""

    strategy_id: str
    symbols: tuple[str, ...]
    sides: frozenset[str]
    priority: int
    timeframe: str
    maximum_entry_delay_seconds: int
    execution_symbols: tuple[str, ...]
    execution: ProviderExecutionContract
    source_profile: Path | None = None
    execution_side_overrides: tuple[tuple[str, frozenset[str]], ...] = ()
    entry_context_overrides: tuple[tuple[str, str], ...] = ()
    stop_bps_overrides: tuple[tuple[str, float], ...] = ()
    sizing_overrides: tuple[tuple[str, CohortEntrySizing], ...] = ()
    directional_sizing_overrides: tuple[tuple[str, str, CohortEntrySizing], ...] = ()
    profit_lock_overrides: tuple[CohortProfitLockOverride, ...] = ()
    position_policy: Literal["enter_and_close", "flat_entry_only"] = "enter_and_close"

    def executable_sides(self, symbol: str) -> frozenset[str]:
        """Return effective automatic execution sides for one symbol."""
        overrides = dict(self.execution_side_overrides)
        return overrides.get(symbol, self.sides)

    def entry_context_policy(self, symbol: str) -> str | None:
        """Return an explicit symbol policy or source-contract behavior."""
        return dict(self.entry_context_overrides).get(symbol)

    def execution_for(
        self,
        symbol: str,
        side: str | None = None,
    ) -> ProviderExecutionContract:
        """Return provider, symbol-stop, then directional-lock contract."""
        stop_bps = dict(self.stop_bps_overrides).get(symbol)
        contract = (
            self.execution
            if stop_bps is None
            else replace(self.execution, stop_bps=stop_bps)
        )
        if side is None:
            return contract
        override = next(
            (
                row
                for row in self.profit_lock_overrides
                if row.symbol == symbol and row.side == side
            ),
            None,
        )
        return contract if override is None else override.apply(contract)

    def entry_sizing(
        self,
        symbol: str,
        side: str | None = None,
    ) -> CohortEntrySizing | None:
        """Return side-specific sizing first, then provider-symbol sizing."""
        if side is not None:
            directional = {
                (configured_symbol, configured_side): sizing
                for configured_symbol, configured_side, sizing in (
                    self.directional_sizing_overrides
                )
            }
            selected = directional.get((symbol, side))
            if selected is not None:
                return selected
        return dict(self.sizing_overrides).get(symbol)


@dataclass(frozen=True)
class MultiAssetLiveConfig:
    """One account-owning cohort configuration."""

    profile_id: str
    source_path: Path
    network: str
    margin_mode: str
    maximum_positions: int
    cohort_ledger: Path
    stop_file: Path
    poll_seconds: float
    lookback_days: int
    assets: tuple[AssetLiveConfig, ...]
    providers: tuple[StrategyProviderConfig, ...]
    mode: LiveMode
    enabled: bool
    accepts_live_risk: bool
    transition_approval: Path | None = None

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return enabled symbols in deterministic configuration order."""
        return tuple(asset.symbol for asset in self.assets)

    @property
    def executable_provider_symbols(self) -> frozenset[tuple[str, str]]:
        """Return the explicitly authorized provider-symbol canary pairs."""
        return frozenset(
            (provider.strategy_id, symbol)
            for provider in self.providers
            for symbol in provider.execution_symbols
        )

    @property
    def executable_provider_directions(self) -> frozenset[tuple[str, str, str]]:
        """Return explicit provider, symbol, and direction authority."""
        return frozenset(
            (provider.strategy_id, symbol, side)
            for provider in self.providers
            for symbol in provider.execution_symbols
            for side in provider.executable_sides(symbol)
        )

    @property
    def provider_execution_contracts(
        self,
    ) -> dict[str | tuple[str, str] | tuple[str, str, str], ProviderExecutionContract]:
        """Return defaults plus exact symbol and direction overrides."""
        contracts: dict[
            str | tuple[str, str] | tuple[str, str, str], ProviderExecutionContract
        ] = {provider.strategy_id: provider.execution for provider in self.providers}
        contracts.update(
            {
                (provider.strategy_id, symbol): provider.execution_for(symbol)
                for provider in self.providers
                for symbol, _ in provider.stop_bps_overrides
            }
        )
        contracts.update(
            {
                (provider.strategy_id, override.symbol, override.side): (
                    provider.execution_for(override.symbol, override.side)
                )
                for provider in self.providers
                for override in provider.profit_lock_overrides
            }
        )
        return contracts

    @property
    def provider_entry_sizing(
        self,
    ) -> dict[tuple[str, str], CohortEntrySizing]:
        """Return every explicit provider-symbol sizing override."""
        return {
            (provider.strategy_id, symbol): sizing
            for provider in self.providers
            for symbol, sizing in provider.sizing_overrides
        }

    @property
    def provider_directional_entry_sizing(
        self,
    ) -> dict[tuple[str, str, str], CohortEntrySizing]:
        """Return every explicit provider-symbol-side sizing override."""
        return {
            (provider.strategy_id, symbol, side): sizing
            for provider in self.providers
            for symbol, side, sizing in provider.directional_sizing_overrides
        }

    @property
    def profile_fingerprint(self) -> str:
        """Hash the full non-secret cohort identity."""
        values: dict[str, object] = {
            "profile_id": self.profile_id,
            "network": self.network,
            "margin_mode": self.margin_mode,
            "maximum_positions": self.maximum_positions,
            "cohort_ledger": self.cohort_ledger,
            "stop_file": self.stop_file,
            "poll_seconds": self.poll_seconds,
            "lookback_days": self.lookback_days,
            "assets": tuple(_asset_profile_values(asset) for asset in self.assets),
            "providers": tuple(
                _provider_profile_values(provider) for provider in self.providers
            ),
        }
        if self.transition_approval is not None:
            values["transition_approval"] = self.transition_approval
        return stable_fingerprint(values)

    @property
    def run_fingerprint(self) -> str:
        """Hash the profile with requested authority mode."""
        return stable_fingerprint(
            {"profile_fingerprint": self.profile_fingerprint, "mode": self.mode}
        )

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Reject live startup unless mode, both flags, and credentials agree."""
        _require_live(
            mode=self.mode,
            enabled=self.enabled,
            accepts_live_risk=self.accepts_live_risk,
            credentials_present=credentials_present,
        )


def load_multi_asset_live_config(
    path: Path | str,
    *,
    mode: LiveMode,
    enabled: bool = False,
    accepts_live_risk: bool = False,
) -> MultiAssetLiveConfig:
    """Load and validate one multi-asset profile without reading secrets."""
    if mode not in {"observe", "live"}:
        raise MultiAssetLiveConfigError("mode must be observe or live")
    raw = _load_toml(Path(path))
    _require_known_keys(raw, _TOP_LEVEL_KEYS, "top-level table")
    profile_id = _text(raw, "profile")
    network = _text(raw, "network")
    margin_mode = _text(raw, "margin_mode")
    runtime = _mapping(raw.get("runtime"), "runtime")
    _require_known_keys(runtime, _RUNTIME_KEYS, "[runtime]")
    cohort_ledger = Path(_text(runtime, "cohort_ledger"))
    assets = _assets(
        raw.get("assets"),
        parent_profile_id=profile_id,
        network=network,
        margin_mode=margin_mode,
        cohort_ledger=cohort_ledger,
        mode=mode,
        enabled=enabled,
        accepts_live_risk=accepts_live_risk,
    )
    config = MultiAssetLiveConfig(
        profile_id=profile_id,
        source_path=Path(path),
        network=network,
        margin_mode=margin_mode,
        maximum_positions=_integer(raw, "maximum_positions"),
        cohort_ledger=cohort_ledger,
        stop_file=Path(_text(runtime, "stop_file")),
        poll_seconds=_number(runtime, "poll_seconds"),
        lookback_days=_integer(runtime, "lookback_days"),
        assets=assets,
        providers=_providers(raw.get("providers")),
        mode=mode,
        enabled=bool(enabled),
        accepts_live_risk=bool(accepts_live_risk),
        transition_approval=_optional_path(runtime.get("transition_approval")),
    )
    _validate_config(config)
    return config


def validate_multi_asset_live_config(config: MultiAssetLiveConfig) -> None:
    """Validate a programmatically staged profile using the loader's rules."""
    _validate_config(config)


def _assets(
    value: object,
    *,
    parent_profile_id: str,
    network: str,
    margin_mode: str,
    cohort_ledger: Path,
    mode: LiveMode,
    enabled: bool,
    accepts_live_risk: bool,
) -> tuple[AssetLiveConfig, ...]:
    rows = _mapping_rows(value, "assets")
    for row in rows:
        _require_known_keys(row, _ASSET_KEYS, f"[[assets]] {_row_name(row, 'symbol')}")
    return tuple(
        AssetLiveConfig(
            parent_profile_id=parent_profile_id,
            network=network,
            margin_mode=margin_mode,
            symbol=_text(row, "symbol"),
            sides=_sides(row.get("sides"), "asset sides"),
            leverage=_number(row, "leverage"),
            venue_max_leverage=_number(row, "venue_max_leverage"),
            margin_fraction=_number(row, "margin_fraction"),
            max_notional_usd=_number(row, "max_notional_usd"),
            market_slippage_cap_fraction=_number(row, "market_slippage_cap_fraction"),
            stop_bps=_number(row, "stop_bps"),
            maximum_hold_seconds=_integer(row, "maximum_hold_seconds"),
            live_ledger=cohort_ledger.parent / f"{_text(row, 'symbol').lower()}.jsonl",
            mode=mode,
            enabled=bool(enabled),
            accepts_live_risk=bool(accepts_live_risk),
            entry_slippage_cap_fraction=_optional_number(
                row,
                "entry_slippage_cap_fraction",
            ),
        )
        for row in rows
    )


def _providers(value: object) -> tuple[StrategyProviderConfig, ...]:
    rows = _mapping_rows(value, "providers")
    for row in rows:
        name = f"[[providers]] {_row_name(row, 'strategy_id')}"
        _require_known_keys(row, _PROVIDER_KEYS, name)
        execution = row.get("execution")
        if isinstance(execution, Mapping):
            _require_known_keys(execution, _EXECUTION_KEYS, f"{name} execution")
    return tuple(
        StrategyProviderConfig(
            strategy_id=_text(row, "strategy_id"),
            symbols=_strings(row.get("symbols"), "provider symbols"),
            sides=_sides(row.get("sides"), "provider sides"),
            priority=_integer(row, "priority"),
            timeframe=_text(row, "timeframe"),
            maximum_entry_delay_seconds=_integer(
                row,
                "maximum_entry_delay_seconds",
            ),
            execution_symbols=_optional_strings(
                row.get("execution_symbols"),
                "provider execution_symbols",
            ),
            execution=ProviderExecutionContract.from_payload(row.get("execution")),
            source_profile=_optional_path(row.get("source_profile")),
            execution_side_overrides=_side_overrides(
                row.get("execution_side_overrides"),
            ),
            entry_context_overrides=_entry_context_overrides(
                row.get("entry_context_overrides"),
            ),
            stop_bps_overrides=_positive_number_overrides(
                row.get("stop_bps_overrides"),
                "provider stop_bps_overrides",
            ),
            sizing_overrides=_provider_sizing_overrides(
                row.get("sizing_overrides"),
            ),
            directional_sizing_overrides=_provider_directional_sizing_overrides(
                row.get("directional_sizing_overrides"),
            ),
            profit_lock_overrides=_provider_profit_lock_overrides(
                row.get("profit_lock_overrides"),
            ),
            position_policy=_provider_position_policy(row.get("position_policy")),
        )
        for row in rows
    )


def _row_name(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else "(unnamed)"


def _validate_config(config: MultiAssetLiveConfig) -> None:
    if config.network != "mainnet" or config.margin_mode != "isolated":
        raise MultiAssetLiveConfigError("cohort requires mainnet isolated margin")
    if not 0.0 < config.poll_seconds <= 60.0 or config.lookback_days < 3:
        raise MultiAssetLiveConfigError("invalid cohort polling or lookback settings")
    if not config.assets or len(set(config.symbols)) != len(config.symbols):
        raise MultiAssetLiveConfigError("cohort assets must be unique and multi-asset")
    if config.mode == "live" and len(config.assets) < 2:
        raise MultiAssetLiveConfigError("live cohort requires at least two assets")
    enabled = set(config.symbols)
    provider_ids = [provider.strategy_id for provider in config.providers]
    priorities = [provider.priority for provider in config.providers]
    if len(set(provider_ids)) != len(provider_ids):
        raise MultiAssetLiveConfigError("provider strategy_id values must be unique")
    if len(set(priorities)) != len(priorities):
        raise MultiAssetLiveConfigError("provider priority values must be unique")
    for asset in config.assets:
        try:
            parse_perp_venue_identity(asset.symbol)
        except ValueError as exc:
            raise MultiAssetLiveConfigError(
                f"{asset.symbol} venue identity is invalid: {exc}"
            ) from exc
        if asset.sides != _BOTH_SIDES:
            raise MultiAssetLiveConfigError(
                f"{asset.symbol} must support both long and short"
            )
        if asset.leverage > asset.venue_max_leverage:
            raise MultiAssetLiveConfigError(
                f"{asset.symbol} leverage exceeds configured venue maximum"
            )
        if not 0.0 < asset.margin_fraction <= 1.0:
            raise MultiAssetLiveConfigError("asset margin_fraction must be in (0, 1]")
        if not 0.0 < asset.effective_entry_slippage_cap_fraction <= 0.05:
            raise MultiAssetLiveConfigError(
                "asset entry_slippage_cap_fraction must be in (0, 0.05]"
            )
    _validate_provider_scope(config, enabled)
    executable_symbols = {
        symbol for provider in config.providers for symbol in provider.execution_symbols
    }
    if config.maximum_positions < len(executable_symbols):
        raise MultiAssetLiveConfigError(
            "cohort maximum_positions must be at least executable asset count"
        )
