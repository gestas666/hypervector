"""Bounded read-only startup consistency for a known owned position becoming venue-flat."""

from collections.abc import Mapping, Sequence

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_reconcile import (
    SolStartupReceiptPending,
    SolStartupReconciliation,
    reconcile_sol_startup,
)


def wait_for_stable_startup(
    *,
    records: Sequence[Mapping[str, object]],
    venue: SolReconciliationSnapshot,
    expected_profile_fingerprint: str,
    poller: SolReconciliationPoller,
) -> tuple[SolStartupReconciliation, SolReconciliationSnapshot]:
    """Reuse configured read bounds only for missing receipts of an exact locally owned exit."""

    def reconcile(current: SolReconciliationSnapshot) -> SolStartupReconciliation:
        return reconcile_sol_startup(
            records=records,
            venue=current,
            expected_profile_fingerprint=expected_profile_fingerprint,
        )

    def resolved(current: SolReconciliationSnapshot) -> bool:
        try:
            reconcile(current)
        except SolStartupReceiptPending:
            return False
        return True

    try:
        return reconcile(venue), venue
    except SolStartupReceiptPending:
        confirmed = poller.wait_for(resolved)
        return reconcile(confirmed), confirmed
