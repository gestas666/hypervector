"""Development-frozen Hulk Smash candidate definitions."""

from __future__ import annotations

import pandas as pd

HULK_EXPANSION_MODERATE_ADX_V1 = "hulk_smash_expansion_moderate_adx_v1"


def select_hulk_expansion_moderate_adx(signals: pd.DataFrame) -> pd.DataFrame:
    """Select the pre-validation 30m expansion and ADX 18–25 candidate."""
    required = {"candidate", "evidence", "eligible"}
    missing = sorted(required.difference(signals.columns))
    if missing:
        raise ValueError(f"Hulk candidate signals missing columns: {missing}")
    expansion = signals["candidate"].eq("hulk_rebuilt_expansion_v1")
    moderate_adx = signals["evidence"].map(lambda values: "adx_usable" in values)
    selected = signals.loc[expansion & moderate_adx & signals["eligible"]].copy()
    selected["candidate"] = HULK_EXPANSION_MODERATE_ADX_V1
    return selected.reset_index(drop=True)
