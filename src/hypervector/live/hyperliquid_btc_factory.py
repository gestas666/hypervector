"""Fail-closed construction of the official-SDK BTC source-follow adapter."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Protocol

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_sol_factory import (
    OfficialSolReadOnlySdkBuilder,
    OfficialSolSdkBuilder,
    SolReadOnlySdkBuilderProtocol,
    SolSdkBuilderProtocol,
)
from hypervector.live.hyperliquid_sol_parsing import validate_address
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET

_MAXIMUM_HOLD_SLIPPAGE_FRACTION = 0.01


class ArmedBtcConfigProtocol(Protocol):
    """Minimum fail-closed configuration surface needed by the BTC factory."""

    max_notional_usd: float

    def require_live_start(self, *, credentials_present: bool) -> None: ...


class HulkArmedBtcConfigProtocol(ArmedBtcConfigProtocol, Protocol):
    """Hulk-specific execution envelope required by its adapter factory."""

    market_slippage_cap_fraction: float


def create_read_only_btc_reader(
    *,
    environ: Mapping[str, str] | None = None,
    builder: SolReadOnlySdkBuilderProtocol | None = None,
) -> HyperliquidPerpReader:
    """Construct a BTC reader using only the configured public wallet address."""
    env = environ if environ is not None else os.environ
    address = (env.get(SECRET_ENV_WALLET) or "").strip()
    if not address:
        raise ValueError("read-only BTC preflight requires a wallet address")
    sdk_builder = builder if builder is not None else OfficialSolReadOnlySdkBuilder()
    return HyperliquidPerpReader(
        info=sdk_builder.build(),
        account_address=validate_address(address),
        symbol="BTC",
    )


def create_armed_btc_adapter(
    config: ArmedBtcConfigProtocol,
    *,
    environ: Mapping[str, str] | None = None,
    builder: SolSdkBuilderProtocol | None = None,
) -> BtcHyperliquidAdapter:
    """Construct authenticated mainnet clients only after both live flags pass."""
    return _create_armed_adapter(
        config,
        slippage_fraction=_MAXIMUM_HOLD_SLIPPAGE_FRACTION,
        environ=environ,
        builder=builder,
    )


def create_armed_hulk_btc_adapter(
    config: HulkArmedBtcConfigProtocol,
    *,
    environ: Mapping[str, str] | None = None,
    builder: SolSdkBuilderProtocol | None = None,
) -> BtcHyperliquidAdapter:
    """Construct Hulk authority with its frozen IOC slippage protection."""
    return _create_armed_adapter(
        config,
        slippage_fraction=config.market_slippage_cap_fraction,
        environ=environ,
        builder=builder,
    )


def _create_armed_adapter(
    config: ArmedBtcConfigProtocol,
    *,
    slippage_fraction: float,
    environ: Mapping[str, str] | None,
    builder: SolSdkBuilderProtocol | None,
) -> BtcHyperliquidAdapter:
    env = environ if environ is not None else os.environ
    address = (env.get(SECRET_ENV_WALLET) or "").strip()
    private_key = (env.get(SECRET_ENV_API_KEY) or "").strip()
    config.require_live_start(credentials_present=bool(address and private_key))
    validated = validate_address(address)
    sdk_builder = builder if builder is not None else OfficialSolSdkBuilder()
    info, exchange = sdk_builder.build(
        account_address=validated,
        private_key=private_key,
    )
    return BtcHyperliquidAdapter(
        info=info,
        exchange=exchange,
        account_address=validated,
        max_notional_usd=config.max_notional_usd,
        slippage_fraction=slippage_fraction,
    )
