"""History requirements for configured completed-bar profit locks."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from hypervector.live.cohort_profit_lock_override import CohortProfitLockOverride
from hypervector.live.cohort_profit_lock_history import (
    profit_lock_history_limits,
    profit_lock_market_bars,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


def test_disabled_profile_requests_no_private_exit_history() -> None:
    """Existing profiles retain chart-only data cost when every lock is disabled."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml",
        mode="observe",
    )

    assert profit_lock_history_limits(config.providers) == {}


def test_enabled_provider_requests_terminal_hold_plus_boundary_bars() -> None:
    """The lock history covers the whole possible lifecycle and boundary bars."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml",
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
        "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml",
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
