"""Least-privilege construction of multi-symbol perpetual venue readers."""

from __future__ import annotations

from collections.abc import Mapping
import os
from threading import RLock

from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_sol_factory import (
    OfficialSolReadOnlySdkBuilder,
    SolReadOnlySdkBuilderProtocol,
)
from hypervector.live.hyperliquid_sol_parsing import validate_address
from hypervector.live.perp_venue_identity import (
    configured_perp_dexes,
    parse_perp_venue_identity,
)
from hypervector.live.policy import SECRET_ENV_WALLET
from hypervector.live.serialized_hyperliquid_clients import SerializedHyperliquidInfo


def create_multi_asset_read_only_readers(
    symbols: tuple[str, ...],
    *,
    environ: Mapping[str, str] | None = None,
    builder: SolReadOnlySdkBuilderProtocol | None = None,
) -> dict[str, HyperliquidPerpReader]:
    """Create exact mainnet Info-only readers sharing one serialized client."""
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("read-only perpetual symbols must be unique and non-empty")
    env = os.environ if environ is None else environ
    address = validate_address((env.get(SECRET_ENV_WALLET) or "").strip())
    sdk_builder = builder if builder is not None else OfficialSolReadOnlySdkBuilder()
    raw = sdk_builder.build(perp_dexes=configured_perp_dexes(symbols))
    info = SerializedHyperliquidInfo(raw, RLock())
    return {
        symbol: HyperliquidPerpReader(
            info=info,
            account_address=address,
            symbol=(identity := parse_perp_venue_identity(symbol)).symbol,
            perp_dex=identity.perp_dex,
        )
        for symbol in symbols
    }
