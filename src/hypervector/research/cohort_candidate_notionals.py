"""Exact per-asset route notional projection for cohort candidates."""

from __future__ import annotations

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig


def candidate_asset_notionals(
    config: MultiAssetLiveConfig, account_value_usd: float
) -> dict[str, float]:
    """Return each asset's largest executable route notional at one equity."""
    output: dict[str, float] = {}
    for asset in config.assets:
        values = []
        for provider in config.providers:
            if asset.symbol not in provider.symbols:
                continue
            sizing = provider.entry_sizing(asset.symbol) or CohortEntrySizing(
                asset.margin_fraction, asset.max_notional_usd
            )
            values.append(
                sizing.planned_notional(
                    account_value_usd=account_value_usd,
                    leverage=asset.leverage,
                )
            )
        if not values:
            raise ValueError(f"candidate asset has no route: {asset.symbol}")
        output[asset.symbol] = max(values)
    return output
