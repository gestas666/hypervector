"""Bounded read-only startup consistency for a known owned position becoming venue-flat."""

from collections.abc import Mapping, Sequence

from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_reconcile import (
    AssetStartupReceiptPending,
    AssetStartupReconciliation,
    reconcile_asset_startup,
)


def wait_for_stable_startup(
    *,
    records: Sequence[Mapping[str, object]],
    venue: HyperliquidReconciliationSnapshot,
    expected_profile_fingerprint: str,
    poller: AssetReconciliationPoller,
) -> tuple[AssetStartupReconciliation, HyperliquidReconciliationSnapshot]:
    """Reuse configured read bounds only for missing receipts of an exact locally owned exit."""

    def reconcile(current: HyperliquidReconciliationSnapshot) -> AssetStartupReconciliation:
        return reconcile_asset_startup(
            records=records,
            venue=current,
            expected_profile_fingerprint=expected_profile_fingerprint,
        )

    def resolved(current: HyperliquidReconciliationSnapshot) -> bool:
        try:
            reconcile(current)
        except AssetStartupReceiptPending:
            return False
        return True

    try:
        return reconcile(venue), venue
    except AssetStartupReceiptPending:
        confirmed = poller.wait_for(resolved)
        return reconcile(confirmed), confirmed
