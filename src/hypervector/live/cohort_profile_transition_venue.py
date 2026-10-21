"""Current venue boundary for retained and retired profile symbols."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from hypervector.live.bidirectional_cohort_factory import MultiAssetCohortAdapters
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_change_approval import previous_profile_config
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_read_only_factory import (
    create_multi_asset_read_only_readers,
)


class ReconciliationReader(Protocol):
    """Minimum venue surface required by the transition boundary."""

    def reconcile(self) -> HyperliquidReconciliationSnapshot:
        """Return current position and open-order truth."""


RetiredReaderFactory = Callable[[tuple[str, ...]], Mapping[str, ReconciliationReader]]


def require_profile_transition_venue_boundary(
    config: MultiAssetLiveConfig,
    backup: CohortPrestartBackupResult,
    adapters: MultiAssetCohortAdapters,
    *,
    previous_config: MultiAssetLiveConfig | None = None,
    retired_reader_factory: RetiredReaderFactory = create_multi_asset_read_only_readers,
) -> None:
    """Require current flat venue truth for every retained and retired symbol."""
    if not backup.strategy_changed:
        return
    previous = previous_config or previous_profile_config(config, backup)
    for symbol in config.symbols:
        _require_flat(symbol, adapters.by_symbol[symbol].reconcile(), retired=False)
    retired_symbols = tuple(
        symbol for symbol in previous.symbols if symbol not in config.symbols
    )
    if not retired_symbols:
        return
    readers = retired_reader_factory(retired_symbols)
    if set(readers) != set(retired_symbols):
        raise CohortTransitionDrainError("retired venue reader coverage differs")
    for symbol in retired_symbols:
        _require_flat(symbol, readers[symbol].reconcile(), retired=True)


def _require_flat(
    symbol: str,
    venue: HyperliquidReconciliationSnapshot,
    *,
    retired: bool,
) -> None:
    if venue.position.size_signed == 0.0 and not venue.open_orders:
        return
    prefix = "retired asset " if retired else ""
    raise CohortTransitionDrainError(
        f"changed-profile venue boundary for {prefix}{symbol} "
        "is not flat and order-free"
    )
