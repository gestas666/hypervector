"""One unsigned, uncached funding-context read for an exact HIP-3 roster."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hypervector.data.hip3_mark_snapshot_recorder import (
    Hip3ContextInfoProtocol,
    parse_optional_hip3_funding,
    select_hip3_asset_contexts,
)
from hypervector.data.oxa_api import validate_hip3_symbol


@runtime_checkable
class _ContextInfo(Hip3ContextInfoProtocol, Protocol):
    """Runtime-check the already established unsigned SDK context capability."""


class Hip3RosterFundingReader:
    """Fetch current hourly rates without account identity, credentials or caching."""

    def __init__(self, *, info: object, symbols: tuple[str, ...]) -> None:
        """Require one exact namespace and the existing public Info request surface."""
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("HIP-3 funding symbols must be unique and non-empty")
        dexes = {validate_hip3_symbol(symbol)[0] for symbol in symbols}
        if len(dexes) != 1:
            raise ValueError("HIP-3 funding symbols must use one exact namespace")
        if not isinstance(info, _ContextInfo) or not callable(info.post):
            raise ValueError("HIP-3 funding requires the unsigned Info post surface")
        self._info = info
        self._symbols = symbols
        self._dex = next(iter(dexes))

    def snapshot(self) -> dict[str, float | None]:
        """Fetch once per call and preserve missing values without reusing old rates."""
        response = self._info.post(
            "/info", {"type": "metaAndAssetCtxs", "dex": self._dex}
        )
        contexts = select_hip3_asset_contexts(response, symbols=self._symbols)
        return {
            symbol: parse_optional_hip3_funding(
                contexts[symbol].get("funding"), symbol=symbol
            )
            for symbol in self._symbols
        }
