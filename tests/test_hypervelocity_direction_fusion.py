"""Report-only 1m/5m direction-fusion challenger tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_prefer_1m_direction_fusion,
)


def test_direction_fusion_prefers_1m_then_falls_back_to_5m_entry() -> None:
    decisions = pd.DataFrame(
        {
            "state_1m": [
                "TREND_UP",
                "TREND_DOWN",
                "RANGE",
                "TRANSITION",
                "UNKNOWN",
                "BREAKOUT",
            ],
            "entry_direction": ["short", "long", "long", "short", None, None],
        }
    )

    result = apply_prefer_1m_direction_fusion(decisions)

    assert result["entry_direction"].tolist() == [
        "long",
        "short",
        "long",
        "short",
        None,
        None,
    ]
    assert result["direction_fusion_source"].tolist() == [
        "1m",
        "1m",
        "5m",
        "5m",
        "none",
        "none",
    ]
    assert result["direction_fusion_overrode_5m"].tolist() == [
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert decisions["entry_direction"].iloc[:4].tolist() == [
        "short",
        "long",
        "long",
        "short",
    ]
    assert decisions["entry_direction"].iloc[4:].isna().all()


def test_direction_fusion_requires_1m_state_and_entry_direction() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        apply_prefer_1m_direction_fusion(pd.DataFrame({"state_1m": ["TREND_UP"]}))
