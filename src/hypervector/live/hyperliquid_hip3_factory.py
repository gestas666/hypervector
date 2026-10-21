"""Least-privilege construction for namespaced HIP-3 venue readers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from hypervector.data.oxa_api import validate_hip3_symbol
from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_protocol import HyperliquidInfoProtocol
from hypervector.live.hyperliquid_sdk_factory import OfficialHyperliquidReadOnlySdkBuilder
from hypervector.live.hyperliquid_parsing import (
    HyperliquidAdapterError,
    validate_address,
)
from hypervector.live.policy import SECRET_ENV_WALLET


class Hip3ReadOnlySdkBuilderProtocol(Protocol):
    """Info-only SDK constructor that binds explicit perp-dex namespaces."""

    def build(self, *, perp_dexes: tuple[str, ...]) -> HyperliquidInfoProtocol:
        """Construct a read client without accepting signing material."""
        ...


def create_read_only_hip3_reader(
    *,
    symbol: str,
    environ: Mapping[str, str],
    builder: Hip3ReadOnlySdkBuilderProtocol | None = None,
) -> HyperliquidPerpReader:
    """Construct one exact namespaced reader with no execution capability."""
    try:
        dex, _ = validate_hip3_symbol(symbol)
    except ValueError as exc:
        raise HyperliquidAdapterError(str(exc)) from exc
    address = (environ.get(SECRET_ENV_WALLET) or "").strip()
    if not address:
        raise HyperliquidAdapterError("read-only HIP-3 telemetry requires a wallet")
    sdk_builder = builder if builder is not None else OfficialHyperliquidReadOnlySdkBuilder()
    return HyperliquidPerpReader(
        info=sdk_builder.build(perp_dexes=(dex,)),
        account_address=validate_address(address),
        symbol=symbol,
        perp_dex=dex,
    )
