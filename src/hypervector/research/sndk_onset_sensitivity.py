"""Controlled SNDK state-entry versus onset sensitivity on identical price inputs.

This isolates onset persistence under the same archive exchange-age filter.
It is not an exact V3 receipt-time or V4 prospective publication replay.
Input OHLC provenance and execution-path uncertainty remain caller obligations.
"""

from __future__ import annotations

import pandas as pd

from hypervector.hip3_pressure_contract import (
    ARCHIVE_PARITY_MAXIMUM_PRESSURE_AGE_MS,
    MINIMUM_PRESSURE_SNAPSHOTS,
)
from hypervector.live.hip3_breakout_shadow_specs import SNDK_SHADOW_SPEC
from hypervector.research.hip3_archive_inputs import fresh_pressure_bars
from hypervector.research.hip3_breakout_pressure_signals import (
    build_breakout_pressure_signals,
)


def build_sndk_onset_sensitivity_signals(
    bars: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Compare short entries with frozen recipe and known prior fresh pressure."""
    inputs = fresh_pressure_bars(bars)
    config = SNDK_SHADOW_SPEC.config
    canonical = build_breakout_pressure_signals(inputs, config)
    raw = (
        inputs["close"].lt(canonical["prior_breakout_low"])
        & canonical["fast_ema"].lt(canonical["slow_ema"])
        & inputs["decision_imbalance_10"].le(-config.minimum_abs_imbalance)
    )
    fresh = bars["end_boundary_age_ms"].le(
        ARCHIVE_PARITY_MAXIMUM_PRESSURE_AGE_MS
    ) & bars["source_snapshot_count"].ge(MINIMUM_PRESSURE_SNAPSHOTS)
    adjacent = bars.index.to_series().diff().eq(pd.Timedelta(minutes=15))
    prior_known = fresh.shift(1, fill_value=False) & adjacent
    onset = raw & ~raw.shift(1, fill_value=False) & prior_known
    return {
        "state_entry": _short_only_frame(canonical, raw),
        "durable_onset": _short_only_frame(canonical, onset),
    }


def _short_only_frame(canonical: pd.DataFrame, entries: pd.Series) -> pd.DataFrame:
    output = canonical.copy()
    output["short_entry"] = entries
    output["long_entry"] = False
    output["entry_direction"] = entries.map({True: "short", False: None})
    output["long_exit"] = False
    output["short_exit"] = False
    output["stop_price"] = float("nan")
    output["target_price"] = float("nan")
    return output
