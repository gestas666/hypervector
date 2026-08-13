"""Frozen candidate-selection contracts for rebuilt Hulk Smash."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hulk_smash_candidates import (
    HULK_EXPANSION_MODERATE_ADX_V1,
    select_hulk_expansion_moderate_adx,
)


def test_frozen_candidate_requires_expansion_and_moderate_adx() -> None:
    """Development selection remains explicit and cannot drift on validation."""
    signals = pd.DataFrame(
        {
            "candidate": [
                "hulk_rebuilt_expansion_v1",
                "hulk_rebuilt_expansion_v1",
                "hulk_rebuilt_continuation_v1",
            ],
            "evidence": [
                ("squeeze_release", "adx_usable"),
                ("squeeze_release", "adx_trending"),
                ("adx_usable",),
            ],
            "eligible": [True, True, True],
        }
    )

    selected = select_hulk_expansion_moderate_adx(signals)

    assert len(selected) == 1
    assert selected.iloc[0]["candidate"] == HULK_EXPANSION_MODERATE_ADX_V1
