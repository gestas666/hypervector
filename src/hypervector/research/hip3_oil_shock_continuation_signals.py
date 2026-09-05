"""Causal five-minute shock-continuation signals for exact HIP-3 oil evidence."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
    build_hip3_oil_shock_reversion_signals,
)


def build_hip3_oil_shock_continuation_signals(
    bars: pd.DataFrame,
    config: Hip3OilShockReversionConfig = Hip3OilShockReversionConfig(),
) -> pd.DataFrame:
    """Enter with a fresh oil shock while preserving the frozen detector."""
    reversion = build_hip3_oil_shock_reversion_signals(bars, config)
    output = reversion.copy()
    long_entry = reversion["short_entry"].astype(bool)
    short_entry = reversion["long_entry"].astype(bool)
    recovery = bars["gap_before_bars"].gt(0)
    direction = pd.Series(None, index=bars.index, dtype=object)
    direction.loc[long_entry] = "long"
    direction.loc[short_entry] = "short"
    output["long_entry"] = long_entry
    output["short_entry"] = short_entry
    output["entry_direction"] = direction
    output["long_exit"] = short_entry | recovery
    output["short_exit"] = long_entry | recovery
    output["signal_name"] = direction.map(
        {
            "long": "hip3_oil_shock_continuation_long@5m",
            "short": "hip3_oil_shock_continuation_short@5m",
        }
    )
    return output
