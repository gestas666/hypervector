"""History requirements for configured completed-bar profit locks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from hypervector.live.cohort_profit_lock_override import CohortProfitLockOverride
from hypervector.live.cohort_profit_lock_history import (
    profit_lock_history_limits,
    profit_lock_market_bars,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_FIXTURE_PROFILES = Path("tests/fixtures/profiles")
_RANGE_RETIRED = _FIXTURE_PROFILES / "hype_compression_range_retired_current.toml"
_BTC_HULK_SMART_EXIT = _FIXTURE_PROFILES / "eight_asset_btc_hulk_smart_exit.toml"
_PROFILE_B = Path("tests/fixtures/cohort_chain/profile_b.toml")


def test_disabled_profile_requests_no_private_exit_history() -> None:
    """Existing profiles retain chart-only data cost when every lock is disabled."""
    config = load_multi_asset_live_config(
        _RANGE_RETIRED,
        mode="observe",
    )

    assert profit_lock_history_limits(config.providers) == {}


def test_enabled_provider_requests_terminal_hold_plus_boundary_bars() -> None:
    """The lock history covers the whole possible lifecycle and boundary bars."""
    config = load_multi_asset_live_config(
        _RANGE_RETIRED,
        mode="observe",
    )
    provider = config.providers[0]
    enabled = replace(
        provider,
        symbols=("BTC",),
        execution=replace(
            provider.execution,
            maximum_hold_policy="fixed",
            hard_maximum_hold_seconds=None,
            maximum_hold_seconds=28_800,
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=25.0,
            profit_lock_floor_bps=15.0,
            profit_lock_giveback_bps=10.0,
        ),
    )

    assert profit_lock_history_limits((enabled,)) == {"BTC": 482}

    timestamps = pd.date_range("2026-08-01T00:00:00Z", periods=500, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": range(100, 600),
            "high": range(101, 601),
            "low": range(99, 599),
            "close": range(100, 600),
            "volume": [1.0] * 500,
        }
    )
    output = profit_lock_market_bars(
        (enabled,),
        {("BTC", "1m"): frame},
        timestamps[-1] + pd.Timedelta(minutes=1),
    )

    assert len(output["BTC"]) == 482


def test_directional_override_requests_history_when_base_lock_is_disabled() -> None:
    """A side-only lock must receive the same complete lifecycle history."""
    config = load_multi_asset_live_config(
        _RANGE_RETIRED,
        mode="observe",
    )
    provider = config.providers[0]
    enabled = replace(
        provider,
        symbols=("BTC",),
        execution=replace(
            provider.execution,
            maximum_hold_policy="fixed",
            hard_maximum_hold_seconds=None,
            maximum_hold_seconds=28_800,
            profit_lock_policy="none",
            profit_lock_activation_bps=None,
            profit_lock_floor_bps=None,
            profit_lock_giveback_bps=None,
        ),
        profit_lock_overrides=(
            CohortProfitLockOverride(
                symbol="BTC",
                side="long",
                policy="completed_bar_trailing",
                activation_bps=25.0,
                floor_bps=15.0,
                giveback_bps=10.0,
            ),
        ),
    )

    assert profit_lock_history_limits((enabled,)) == {"BTC": 482}


def test_btc_hulk_component_floor_retains_restart_stable_warmup() -> None:
    """The specialized policy retains 24h seed plus its full 24h lifecycle."""
    config = load_multi_asset_live_config(_BTC_HULK_SMART_EXIT, mode="observe")

    limits = profit_lock_history_limits(config.providers)

    assert limits["BTC"] == 2_882


def test_profile_b_exit_policy_v2_requests_full_lifecycle_history_per_route() -> None:
    """Profile B's adaptive exits need terminal hold, boundary bars and warmup."""
    config = load_multi_asset_live_config(_PROFILE_B, mode="observe")

    assert all(
        provider.execution.profit_lock_policy == "none"
        and provider.execution.adaptive_exit_policy
        == "regime_flip_floor_retention_v2"
        for provider in config.providers
    )
    # 24h holds: 1440 bars + 2 boundary + 21 regime warmup; ETH holds 48h.
    assert profit_lock_history_limits(config.providers) == {
        "BTC": 1_463,
        "ETH": 2_903,
        "SOL": 1_463,
        "xyz:SNDK": 1_463,
        "xyz:BRENTOIL": 1_463,
        "xyz:TSLA": 1_463,
    }
