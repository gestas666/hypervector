"""Least-privilege current L2 collector for the disarmed cohort observer."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.hyperliquid_perp_parsing import parse_book_for_symbol
from hypervector.live.hyperliquid_protocol import (
    HyperliquidInfoProtocol,
    SolBookSnapshot,
)


class MultiAssetPublicBookCollector:
    """Collect strict venue-maximum books without wallet or signer access."""

    def __init__(
        self,
        *,
        info: HyperliquidInfoProtocol,
        symbols: tuple[str, ...],
        depth_levels: int = 20,
    ) -> None:
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("public book symbols must be unique and non-empty")
        if depth_levels <= 0:
            raise ValueError("public book depth must be positive")
        self._info = info
        self._symbols = symbols
        self._depth_levels = depth_levels

    def collect(self) -> Mapping[str, SolBookSnapshot]:
        """Return one validated two-sided snapshot for every configured symbol."""
        return {
            symbol: parse_book_for_symbol(
                self._info.l2_snapshot(symbol),
                symbol=symbol,
                depth_levels=self._depth_levels,
            )
            for symbol in self._symbols
        }
