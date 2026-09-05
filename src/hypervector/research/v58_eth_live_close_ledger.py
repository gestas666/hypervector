"""ETH compatibility wrapper for generic V58 live-close accounting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.v58_live_close_ledger import (
    LiveCloseLedger,
    fill_events,
    fill_time,
    reconcile_live_close_ledger,
)

Record = Mapping[str, object]
EthCloseLedger = LiveCloseLedger

__all__ = (
    "EthCloseLedger",
    "fill_events",
    "fill_time",
    "reconcile_eth_close_ledger",
)


def reconcile_eth_close_ledger(
    rows: Sequence[Record],
    close: Record,
    *,
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
) -> EthCloseLedger:
    """Reconcile exact V58 ETH long fills, funding, and fees."""
    return reconcile_live_close_ledger(
        rows,
        close,
        run_id=run_id,
        profile_id=profile_id,
        profile_fingerprint=profile_fingerprint,
        symbol="ETH",
        side="long",
    )
