"""Tests for corrected Hulk Smash formation signals."""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd

from hypervector.research.hulk_smash_signals import (
    evaluate_hulk_smash_signals,
    hulk_fingerprint,
)


def _components() -> pd.DataFrame:
    """Return the exact current ST+wSlN+wxU long formation."""
    index = pd.date_range("2026-01-01", periods=5, freq="30min", tz=UTC)
    return pd.DataFrame(
        {
            "wt1": [-5.0, -6.0, -7.0, -8.0, -10.0],
            "wave_cross": [0, 0, 0, 0, 1],
            "money_flow_value": [5.0, 4.0, 3.0, 2.0, 1.0],
            "ema_11": [101.0] * 5,
            "ema_15": [100.0] * 5,
            "rsi_14": [50.0, 70.0, 60.0, 40.0, 30.0],
        },
        index=index,
    )


def test_current_long_formation_matches_causal_five_bar_window() -> None:
    """The current high-edge long fingerprint must remain exactly identifiable."""
    components = _components()
    supertrend = pd.Series([1] * 5, index=components.index)
    quality = pd.Series([4] * 5, index=components.index)

    decisions = evaluate_hulk_smash_signals(
        components, supertrend, quality, quality_threshold=4
    )

    decision = decisions.iloc[0]
    assert decision["side"] == "long"
    assert decision["formation"] == "ST+wSlN+wxU"
    assert decision["eligible"]
    assert decision["candidate"] == "hulk_current_q4"


def test_quality_three_and_four_remain_separate_trial_identities() -> None:
    """The user's q3 edit must not silently overwrite the committed q4 baseline."""
    components = _components()
    supertrend = pd.Series([1] * 5, index=components.index)
    quality = pd.Series([3] * 5, index=components.index)

    q3 = evaluate_hulk_smash_signals(
        components, supertrend, quality, quality_threshold=3
    ).iloc[0]
    q4 = evaluate_hulk_smash_signals(
        components, supertrend, quality, quality_threshold=4
    ).iloc[0]

    assert q3["eligible"]
    assert q3["candidate"] == "hulk_current_q3"
    assert not q4["eligible"]
    assert q4["reason"] == "quality_below_4"


def test_mfi_slope_uses_money_flow_value_not_rsi() -> None:
    """Correct the legacy defect that substituted RSI for the MFI series."""
    components = _components()
    components["money_flow_value"] = np.linspace(1.0, 5.0, len(components))
    components["rsi_14"] = np.linspace(80.0, 20.0, len(components))

    fingerprint = hulk_fingerprint(
        components,
        supertrend_direction=1,
        position=4,
        lookback_bars=5,
        side="long",
    )

    assert "mSlP" in fingerprint
    assert "wSlN" in fingerprint
