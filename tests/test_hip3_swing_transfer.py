"""Bounded HIP-3 Swing/HA transfer experiment contracts."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    common_transfer_windows,
    literal_swing_control_config,
    run_hip3_swing_transfer,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _asset(symbol: str, *, poison_holdout: bool = False) -> Hip3TransferAsset:
    index = pd.date_range("2026-01-01", periods=120, freq="15min", tz="UTC")
    pattern = [100.0, 102.0, 105.0, 103.0, 99.0, 101.0, 106.0, 104.0]
    close = [
        pattern[position % len(pattern)] + position * 0.02 for position in range(120)
    ]
    bars = pd.DataFrame(
        {
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "gap_before_bars": [0] * 120,
            "funding_rate": [0.0] * 120,
        },
        index=index,
    )
    if poison_holdout:
        bars.loc[index[96] :, ["open", "high", "low", "close"]] = float("nan")
    return Hip3TransferAsset(symbol, 50.0, bars)


def _friction() -> Hip3ExecutionFriction:
    return Hip3ExecutionFriction(
        notional_usd=75.0,
        effective_taker_fee_rate=0.0000864,
        nominal_visible_round_trip_bps=0.80,
        nominal_latency_bps_per_side=1.0,
        stress_visible_round_trip_bps=2.10,
        stress_latency_bps_per_side=2.0,
    )


def test_common_windows_are_chronological_sixty_twenty_twenty() -> None:
    windows = common_transfer_windows((_asset("xyz:SP500"),))
    full = windows.holdout_end_utc - windows.development_start_utc
    development = windows.development_end_utc - windows.development_start_utc
    validation = windows.validation_end_utc - windows.development_end_utc
    holdout = windows.holdout_end_utc - windows.validation_end_utc

    assert development / full == pytest.approx(0.60, abs=0.02)
    assert validation / full == pytest.approx(0.20, abs=0.02)
    assert holdout / full == pytest.approx(0.20, abs=0.02)
    assert len(windows.development_folds) == 3


def test_friction_maps_measured_costs_to_exact_canary_notional() -> None:
    nominal = _friction().screen_config(stress=False)
    stress = _friction().screen_config(stress=True)

    assert nominal.initial_equity == pytest.approx(500.0)
    assert nominal.margin_fraction == pytest.approx(0.03)
    assert nominal.leverage == pytest.approx(5.0)
    assert nominal.fee_rate_per_side == pytest.approx(0.0000864)
    assert nominal.slippage_bps_per_side == pytest.approx(1.4)
    assert stress.slippage_bps_per_side == pytest.approx(3.05)


def test_run_accounts_for_all_trials_and_does_not_open_holdout() -> None:
    asset = _asset("xyz:SP500", poison_holdout=True)
    base = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)
    block = replace(base, order_block_role="structural_stop", order_block_periods=1)

    result = run_hip3_swing_transfer(
        (asset,),
        {asset.symbol: _friction()},
        base_configs=(base,),
        order_block_configs=(block,),
    )

    assert len(result.base_evaluations) == 1
    assert len(result.order_block_evaluations) == 1
    assert result.searched_trial_count == 2
    assert len(result.validation_nominal) == 1
    assert len(result.validation_stress) == 1
    assert result.literal_control == literal_swing_control_config()
    assert len(result.literal_control_nominal) == 1
    assert len(result.literal_control_stress) == 1
    assert result.holdout_status == "sealed_not_evaluated"
    assert result.execution_authority == "none"


def test_literal_control_matches_requested_buy_green_sell_red_rule() -> None:
    control = literal_swing_control_config()

    assert (control.fast_ema, control.slow_ema) == (9, 21)
    assert control.entry_mode == "state"
    assert control.exit_mode == "alignment_loss"
    assert control.order_block_role == "none"
