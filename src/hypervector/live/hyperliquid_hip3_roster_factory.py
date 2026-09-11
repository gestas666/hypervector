"""Shared least-privilege construction for a same-dex HIP-3 reader roster."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hypervector.data.oxa_api import validate_hip3_symbol
from hypervector.live.hyperliquid_hip3_factory import (
    Hip3ReadOnlySdkBuilderProtocol,
)
from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_protocol import HyperliquidInfoProtocol
from hypervector.live.hyperliquid_sol_factory import OfficialSolReadOnlySdkBuilder
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    validate_address,
)
from hypervector.live.policy import SECRET_ENV_WALLET
from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader


@dataclass(frozen=True)
class Hip3RosterSources:
    """Same-client market/account readers and public funding telemetry."""

    readers: Mapping[str, HyperliquidPerpReader]
    funding: Hip3RosterFundingReader


def create_read_only_hip3_roster_readers(
    *,
    symbols: tuple[str, ...],
    environ: Mapping[str, str],
    builder: Hip3ReadOnlySdkBuilderProtocol | None = None,
) -> dict[str, HyperliquidPerpReader]:
    """Build exact same-dex readers around one shared Info-only SDK client."""
    readers, _info = _build_roster(symbols=symbols, environ=environ, builder=builder)
    return readers


def create_read_only_hip3_roster_sources(
    *,
    symbols: tuple[str, ...],
    environ: Mapping[str, str],
    builder: Hip3ReadOnlySdkBuilderProtocol | None = None,
) -> Hip3RosterSources:
    """Share one unsigned Info client across account, book and funding sources."""
    readers, info = _build_roster(symbols=symbols, environ=environ, builder=builder)
    return Hip3RosterSources(
        readers, Hip3RosterFundingReader(info=info, symbols=symbols)
    )


def _build_roster(
    *,
    symbols: tuple[str, ...],
    environ: Mapping[str, str],
    builder: Hip3ReadOnlySdkBuilderProtocol | None,
) -> tuple[dict[str, HyperliquidPerpReader], HyperliquidInfoProtocol]:
    dex = _shared_roster_dex(symbols)
    address = (environ.get(SECRET_ENV_WALLET) or "").strip()
    if not address:
        raise HyperliquidAdapterError("read-only HIP-3 telemetry requires a wallet")
    validated_address = validate_address(address)
    sdk_builder = builder if builder is not None else OfficialSolReadOnlySdkBuilder()
    info = sdk_builder.build(perp_dexes=(dex,))
    readers = {
        symbol: HyperliquidPerpReader(
            info=info,
            account_address=validated_address,
            symbol=symbol,
            perp_dex=dex,
        )
        for symbol in symbols
    }
    return readers, info


def _shared_roster_dex(symbols: tuple[str, ...]) -> str:
    if not symbols or len(set(symbols)) != len(symbols):
        raise HyperliquidAdapterError(
            "read-only HIP-3 roster symbols must be non-empty and unique"
        )
    try:
        dexes = {validate_hip3_symbol(symbol)[0] for symbol in symbols}
    except ValueError as exc:
        raise HyperliquidAdapterError(str(exc)) from exc
    if len(dexes) != 1:
        raise HyperliquidAdapterError(
            "read-only HIP-3 roster must use one exact namespace"
        )
    return next(iter(dexes))
