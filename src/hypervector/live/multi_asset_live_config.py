"""Strict configuration for a shared multi-asset bidirectional canary."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    optional_path as _optional_path,
    optional_strings as _optional_strings,
    positive_number_overrides as _positive_number_overrides,
    provider_position_policy as _provider_position_policy,
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
        return stable_fingerprint(
            {
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
        )

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
    profile_id = _text(raw, "profile")
    network = _text(raw, "network")
    margin_mode = _text(raw, "margin_mode")
    runtime = _mapping(raw.get("runtime"), "runtime")
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
        )
        for row in rows
    )


def _providers(value: object) -> tuple[StrategyProviderConfig, ...]:
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
        for row in _mapping_rows(value, "providers")
    )


def _validate_config(config: MultiAssetLiveConfig) -> None:
    if config.network != "mainnet" or config.margin_mode != "isolated":
        raise MultiAssetLiveConfigError("cohort requires mainnet isolated margin")
    if config.maximum_positions < len(config.assets):
        raise MultiAssetLiveConfigError(
            "cohort maximum_positions must be at least enabled asset count"
        )
    if not 0.0 < config.poll_seconds <= 60.0 or config.lookback_days < 3:
        raise MultiAssetLiveConfigError("invalid cohort polling or lookback settings")
    if len(config.assets) < 2 or len(set(config.symbols)) != len(config.symbols):
        raise MultiAssetLiveConfigError("cohort assets must be unique and multi-asset")
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
    _validate_provider_scope(config, enabled)


def _require_live(
    *,
    mode: LiveMode,
    enabled: bool,
    accepts_live_risk: bool,
    credentials_present: bool,
) -> None:
    if mode != "live":
        raise MultiAssetLiveConfigError("live start refused because mode is observe")
    if not enabled:
        raise MultiAssetLiveConfigError("live start requires --enabled")
    if not accepts_live_risk:
        raise MultiAssetLiveConfigError("live start requires --i-accept-live-risk")
    if not credentials_present:
        raise MultiAssetLiveConfigError("live start requires configured credentials")
