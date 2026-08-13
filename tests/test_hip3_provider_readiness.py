"""Truthful entry-trigger readiness for HIP-3 Swing/HA evaluations."""

from __future__ import annotations

import pandas as pd

from hypervector.live.hip3_provider_evaluations import swing_evaluation
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _bar() -> pd.Series:
    return pd.Series({"close": 101.0})


def _aligned_signal(*, long_entry: bool) -> pd.Series:
    return pd.Series(
        {
            "long_entry": long_entry,
            "short_entry": False,
            "buy_state": True,
            "sell_state": False,
            "ha_color": 1,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
            "active_ob_direction": 1,
            "long_exit": False,
            "short_exit": False,
        }
    )


def test_aligned_onset_recipe_discloses_missing_fresh_entry_trigger() -> None:
    """Four aligned components cannot render as fully ready without an onset."""
    evaluation = swing_evaluation(
        strategy_id="hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
        symbol="xyz:GOLD",
        timestamp=pd.Timestamp("2026-08-08T10:00:00Z"),
        bar=_bar(),
        signal=_aligned_signal(long_entry=False),
        config=SwingHaSignalConfig(
            entry_mode="onset",
            order_block_role="agreement",
        ),
    )

    assert evaluation.eligible is False
    assert evaluation.readiness.conditions_met == 4
    assert evaluation.readiness.conditions_required == 5
    assert evaluation.readiness.blockers == ("fresh_entry_onset_absent",)
    assert evaluation.readiness.fraction == 0.8


def test_aligned_onset_entry_reports_five_of_five() -> None:
    """A real fresh trigger plus all four confirmations is fully ready."""
    evaluation = swing_evaluation(
        strategy_id="hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
        symbol="xyz:GOLD",
        timestamp=pd.Timestamp("2026-08-08T10:00:00Z"),
        bar=_bar(),
        signal=_aligned_signal(long_entry=True),
        config=SwingHaSignalConfig(
            entry_mode="onset",
            order_block_role="agreement",
        ),
    )

    assert evaluation.eligible is True
    assert evaluation.readiness.conditions_met == 5
    assert evaluation.readiness.conditions_required == 5
    assert evaluation.readiness.blockers == ()
    assert evaluation.readiness.fraction == 1.0
