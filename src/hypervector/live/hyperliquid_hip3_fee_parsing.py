"""Strict parsing for causal HIP-3 market fee metadata."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.hyperliquid_protocol import Hip3MarketFeeMetadata
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    mapping,
    nonnegative_integer,
    number,
    sequence,
    text,
)


def parse_hip3_market_fee_metadata(
    *,
    metadata: object,
    dexes: object,
    symbol: str,
    perp_dex: str,
) -> Hip3MarketFeeMetadata:
    """Parse exact market mode, collateral, and deployer fee scale."""
    market_metadata = mapping(metadata, f"{perp_dex} metadata")
    market = _exact_market(market_metadata, symbol)
    dex = _exact_dex(dexes, perp_dex)
    growth_mode = _growth_mode(market, symbol)
    fee_scale = _deployer_fee_scale(market, dex)
    if fee_scale is not None and not 0.0 <= fee_scale <= 3.0:
        raise HyperliquidAdapterError("deployerFeeScale must be between zero and three")
    return Hip3MarketFeeMetadata(
        deployer_fee_scale=fee_scale,
        growth_mode=growth_mode,
        collateral_token_index=nonnegative_integer(
            market_metadata.get("collateralToken"),
            "collateralToken",
        ),
    )


def _deployer_fee_scale(
    market: Mapping[str, object],
    dex: Mapping[str, object],
) -> float | None:
    """Prefer the market-specific fee scale, then the dex-wide legacy field."""
    value = market.get("deployerFeeScale")
    if value is None:
        value = dex.get("deployerFeeScale")
    return None if value is None else number(value, "deployerFeeScale")


def _growth_mode(market: Mapping[str, object], symbol: str) -> bool | None:
    raw = market.get("growthMode")
    if raw is None:
        return None
    growth_mode = text(raw, f"{symbol} growthMode")
    if growth_mode not in {"enabled", "disabled"}:
        raise HyperliquidAdapterError(f"{symbol} growthMode is unsupported")
    return growth_mode == "enabled"


def _exact_market(
    metadata: Mapping[str, object],
    symbol: str,
) -> Mapping[str, object]:
    matches = [
        mapping(row, "market metadata")
        for row in sequence(metadata.get("universe"), "market universe")
        if mapping(row, "market metadata").get("name") == symbol
    ]
    if len(matches) != 1:
        raise HyperliquidAdapterError(
            f"{symbol} fee metadata must contain exactly one market"
        )
    return matches[0]


def _exact_dex(value: object, perp_dex: str) -> Mapping[str, object]:
    matches = [
        mapping(row, "perp dex")
        for row in sequence(value, "perp dexes")
        if isinstance(row, Mapping)
        if mapping(row, "perp dex").get("name") == perp_dex
    ]
    if len(matches) != 1:
        raise HyperliquidAdapterError(
            f"{perp_dex} deployer fee metadata must resolve exactly once"
        )
    return matches[0]
