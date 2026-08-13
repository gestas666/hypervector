"""Predeclared coherent search surfaces for rebuilt Hulk Smash."""

from __future__ import annotations

from itertools import product

import pandas as pd

from hypervector.research.hulk_smash_autotune import (
    HulkTuneFold,
    HulkTuneParameters,
    HulkTuneScenario,
)
from hypervector.research.market_cipher_strategy_research import (
    resolve_market_cipher_replay_config,
)


def local_signal_surface_v1() -> tuple[HulkTuneParameters, ...]:
    """Return 27 nearby signal trials around the development-selected Hulk."""
    values = product(
        (7, 8, 9),
        (6, 8, 10),
        ((16.0, 23.0), (18.0, 25.0), (20.0, 27.0)),
    )
    return tuple(
        HulkTuneParameters(
            supertrend_period=7,
            supertrend_multiplier=3.0,
            adx_period=20,
            squeeze_period=20,
            minimum_score=score,
            pivot_bars=pivot,
            adx_usable=usable,
            adx_trending=trending,
        )
        for score, pivot, (usable, trending) in values
    )


def development_folds_v1() -> tuple[HulkTuneFold, ...]:
    """Return three non-overlapping chronological development folds."""
    return (
        HulkTuneFold(
            "development_1",
            pd.Timestamp("2025-08-23T09:00:00Z"),
            pd.Timestamp("2025-10-16T00:00:00Z"),
        ),
        HulkTuneFold(
            "development_2",
            pd.Timestamp("2025-10-16T00:00:00Z"),
            pd.Timestamp("2025-12-08T00:00:00Z"),
        ),
        HulkTuneFold(
            "development_3",
            pd.Timestamp("2025-12-08T00:00:00Z"),
            pd.Timestamp("2026-02-01T00:00:00Z"),
        ),
    )


def robust_development_scenarios_v1() -> tuple[HulkTuneScenario, ...]:
    """Return nominal, cost, and delayed execution development scenarios."""
    return tuple(
        HulkTuneScenario(name, resolve_market_cipher_replay_config(name))
        for name in ("nominal", "cost_stress", "entry_delay_2_bars")
    )
