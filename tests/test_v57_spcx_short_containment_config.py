"""Acceptance contract for the approved SPCX long-side containment successor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V56 = Path("configs/multi_asset_growth_first_5000_btc_tuned_v2_increment_v56.toml")
_V57 = Path("configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml")
_SPCX = "xyz:SPCX"
_SPCX_ROUTE = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1"


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def test_v57_changes_only_profile_and_spcx_long_authority() -> None:
    """BTC/HYPE and SPCX risk/exits stay exact while SPCX becomes short-only."""
    v56 = _load(_V56)
    v57 = _load(_V57)

    assert v57.profile_id == "multi_asset_growth_first_5000_spcx_short_containment_v57"
    assert v57.network == v56.network == "mainnet"
    assert v57.margin_mode == v56.margin_mode == "isolated"
    assert v57.maximum_positions == v56.maximum_positions == 10
    assert v57.cohort_ledger == v56.cohort_ledger
    assert v57.stop_file == v56.stop_file
    assert v57.poll_seconds == v56.poll_seconds
    assert v57.lookback_days == v56.lookback_days
    assert v57.providers[:-1] == v56.providers[:-1]

    old_spcx = v56.providers[-1]
    new_spcx = v57.providers[-1]
    assert old_spcx.strategy_id == new_spcx.strategy_id == _SPCX_ROUTE
    assert new_spcx.symbols == new_spcx.execution_symbols == (_SPCX,)
    assert new_spcx.sides == old_spcx.sides
    assert new_spcx.execution_side_overrides == ((_SPCX, frozenset({"short"})),)
    assert new_spcx.execution == old_spcx.execution
    assert new_spcx.priority == old_spcx.priority
    assert new_spcx.timeframe == old_spcx.timeframe
    assert new_spcx.maximum_entry_delay_seconds == old_spcx.maximum_entry_delay_seconds


def test_v57_removes_every_spcx_long_execution_path() -> None:
    """Provider direction authority must reject automatic and manual SPCX long."""
    v56 = _load(_V56)
    v57 = _load(_V57)
    old_assets = {row.symbol: row for row in v56.assets}
    new_assets = {row.symbol: row for row in v57.assets}

    assert (
        replace(new_assets["BTC"], parent_profile_id=v56.profile_id)
        == old_assets["BTC"]
    )
    assert (
        replace(new_assets["HYPE"], parent_profile_id=v56.profile_id)
        == old_assets["HYPE"]
    )
    assert new_assets[_SPCX].sides == old_assets[_SPCX].sides
    assert new_assets[_SPCX].leverage == old_assets[_SPCX].leverage
    assert new_assets[_SPCX].margin_fraction == old_assets[_SPCX].margin_fraction
    assert new_assets[_SPCX].max_notional_usd == old_assets[_SPCX].max_notional_usd
    assert new_assets[_SPCX].stop_bps == old_assets[_SPCX].stop_bps
    assert (
        new_assets[_SPCX].maximum_hold_seconds == old_assets[_SPCX].maximum_hold_seconds
    )
    assert (_SPCX_ROUTE, _SPCX, "long") not in v57.executable_provider_directions
    assert (_SPCX_ROUTE, _SPCX, "short") in v57.executable_provider_directions
