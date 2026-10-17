"""Accounting identity validation shared by headless checkpoint services."""

from collections.abc import Mapping
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfigError
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch


def require_checkpoint_accounting_epoch(
    document: object,
    epoch: CohortAccountingEpoch,
) -> None:
    """Reject a checkpoint whose portfolio view uses another epoch."""
    if not isinstance(document, Mapping):
        raise MultiAssetLiveConfigError("checkpoint accounting epoch differs")
    audit = document.get("audit")
    archive = audit.get("portfolio_archive") if isinstance(audit, Mapping) else None
    observed = archive.get("accounting_epoch") if isinstance(archive, Mapping) else None
    if observed != epoch.to_dict():
        raise MultiAssetLiveConfigError("checkpoint accounting epoch differs")
