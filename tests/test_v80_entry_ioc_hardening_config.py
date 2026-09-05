"""Acceptance contract for V80 entry/exit IOC separation."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.cohort_accounting_rollover import (
    load_required_accounting_epoch,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V79 = Path("configs/multi_asset_growth_first_5000_seven_asset_all_active_v79.toml")
_V78 = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_sndk_canary_sizing_repair_v78.toml"
)
_V80 = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_entry_ioc_hardened_v80.toml"
)
_EXPECTED_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "ZEC",
    "xyz:SPCX",
    "xyz:SNDK",
)


def test_v80_preserves_every_v79_route_and_requested_asset_order() -> None:
    """Entry hardening must not retire, reorder, or replace any strategy."""
    prior = load_multi_asset_live_config(_V79, mode="observe")
    candidate = load_multi_asset_live_config(_V80, mode="observe")

    assert candidate.symbols == _EXPECTED_SYMBOLS
    assert candidate.executable_provider_directions == (
        prior.executable_provider_directions
    )
    assert candidate.maximum_positions == 7


def test_v80_uses_tight_entries_and_wider_reduce_only_closes() -> None:
    """No opening IOC may consume a short stop before protection is placed."""
    candidate = load_multi_asset_live_config(_V80, mode="observe")

    assert all(
        asset.entry_slippage_cap_fraction == pytest.approx(0.002)
        for asset in candidate.assets
    )
    assert all(
        asset.market_slippage_cap_fraction == pytest.approx(0.01)
        for asset in candidate.assets
    )
    assert all(
        asset.effective_entry_slippage_cap_fraction * 10_000.0 < asset.stop_bps
        for asset in candidate.assets
    )


def test_v80_is_a_new_immutable_profile_generation() -> None:
    """The runtime change must not hide behind V79's approved fingerprint."""
    prior = load_multi_asset_live_config(_V79, mode="observe")
    candidate = load_multi_asset_live_config(_V80, mode="observe")

    assert candidate.profile_id == (
        "multi_asset_growth_first_5000_seven_asset_entry_ioc_hardened_v80"
    )
    assert candidate.profile_fingerprint != prior.profile_fingerprint
    assert candidate.transition_approval is not None


def test_v80_approval_binds_the_last_armed_profile_directly() -> None:
    """The never-started V79 generation must not be invented as live lineage."""
    previous = load_multi_asset_live_config(_V78, mode="observe")
    candidate = load_multi_asset_live_config(_V80, mode="observe")

    evidence = validate_profile_change_approval(
        previous,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == []
    assert evidence["execution_authority"] == "none"


def test_v80_requires_an_identity_bound_accounting_epoch() -> None:
    """The TUI may reset its display only through preserved immutable history."""
    candidate = load_multi_asset_live_config(_V80, mode="observe")

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, candidate)
