"""Exact TUI friction-contract coverage for the V79 active roster."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
    SOL_RANGE_SHORT_STRATEGY,
)
from hypervector.live.multi_asset_cohort_payloads import (
    asset_config_payload,
    provider_config_payload,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
)
from hypervector.live.zec_donchian_provider import ZEC_DONCHIAN_LONG_STRATEGY
from hypervector.research.cohort_friction_parity import build_friction_parity

_V79 = Path("configs/multi_asset_growth_first_5000_seven_asset_all_active_v79.toml")


def test_v79_friction_parity_models_every_active_route() -> None:
    """The TUI must not report missing execution evidence for V79 routes."""
    report = build_friction_parity(_v79_identity(), [])

    assert report["summary"] == {
        "provider_symbols": 9,
        "runtime_shape_aligned": 9,
        "contract_mismatch": 0,
        "unsupported_contract": 0,
        "runtime_contract_missing": 0,
        "provider_symbols_with_entry_fills": 0,
    }


def test_v79_zec_tui_evidence_discloses_exact_capped_shape_replay() -> None:
    """ZEC display evidence must not substitute the wider source-risk replay."""
    evidence = strategy_research_evidence(ZEC_DONCHIAN_LONG_STRATEGY, "ZEC")

    assert evidence.research_state == (
        "v79_shape_replayed_largest_winner_falsified_live_probation"
    )
    assert "9 exact V79-shape" in evidence.cadence
    assert "3W/6L" in evidence.summary
    assert "+$160.73" in evidence.summary
    assert "-$45.98 after largest-winner removal" in evidence.summary
    assert "two extra stop exits" in evidence.summary
    assert evidence.evidence_source.endswith(
        "v84_v79_friction_contract_completion_20260903_v1.json"
    )


@pytest.mark.parametrize(
    "strategy,symbol,stop_policy,stop_bps,min_stop,max_stop,hold,target,target_bps",
    [
        (
            ETH_RANGE_LONG_STRATEGY,
            "ETH",
            "fixed_bps",
            60.0,
            None,
            None,
            172_800,
            "none",
            None,
        ),
        (
            SOL_RANGE_SHORT_STRATEGY,
            "SOL",
            "fixed_bps",
            60.0,
            None,
            None,
            172_800,
            "none",
            None,
        ),
        (
            ZEC_DONCHIAN_LONG_STRATEGY,
            "ZEC",
            "structural_clamped_bps",
            None,
            20.0,
            250.0,
            2_592_000,
            "none",
            None,
        ),
        (
            SPCX_CASH_SESSION_LONG_STRATEGY,
            "xyz:SPCX",
            "fixed_bps",
            60.0,
            None,
            None,
            22_500,
            "fixed_bps",
            120.0,
        ),
    ],
)
def test_v79_new_route_modeled_contracts_match_runtime_shape(
    strategy: str,
    symbol: str,
    stop_policy: str,
    stop_bps: float | None,
    min_stop: float | None,
    max_stop: float | None,
    hold: int,
    target: str,
    target_bps: float | None,
) -> None:
    """New-route evidence must preserve exact stop, hold, and target shape."""
    modeled = build_friction_parity(_v79_identity(), [])["by_provider_symbol"][
        f"{strategy}|{symbol}"
    ]["modeled_contract"]

    assert modeled["stop_policy"] == stop_policy
    assert modeled["stop_bps"] == stop_bps
    assert modeled["minimum_stop_bps"] == min_stop
    assert modeled["maximum_stop_bps"] == max_stop
    assert modeled["maximum_hold_seconds"] == hold
    assert modeled["target_policy"] == target
    assert modeled["target_bps"] == target_bps


def _v79_identity() -> dict[str, object]:
    config = load_multi_asset_live_config(_V79, mode="observe")
    return {
        "assets": [asset_config_payload(asset) for asset in config.assets],
        "providers": [provider_config_payload(row) for row in config.providers],
    }
