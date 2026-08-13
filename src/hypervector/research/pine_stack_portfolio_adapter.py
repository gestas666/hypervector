"""Adapter from four-Pine feature events to shared portfolio signals."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

PineStackExitVariant = Literal[
    "cs_flip",
    "trend_or_cs",
    "tp80_or_cs",
    "tp100_or_cs",
]

_EXIT_VARIANTS: tuple[PineStackExitVariant, ...] = (
    "cs_flip",
    "trend_or_cs",
    "tp80_or_cs",
    "tp100_or_cs",
)
_FEATURE_COLUMNS = {
    "bar_open_at",
    "cs_long_onset",
    "cs_short_onset",
    "trend_levels_state",
    "tp_density_80_onset",
    "tp_density_100_onset",
}
_ENTRY_COLUMNS = {
    "candidate",
    "signal_bar_open_at",
    "decision_time_utc",
    "side",
    "execution_authority",
}


def declared_pine_stack_exit_variants() -> tuple[PineStackExitVariant, ...]:
    """Return the source and three causal exit-ablation identities."""
    return _EXIT_VARIANTS


def pine_stack_portfolio_signals(
    features: pd.DataFrame,
    entries: pd.DataFrame,
    *,
    candidate: str,
    exit_variant: PineStackExitVariant,
) -> pd.DataFrame:
    """Return index-aligned close-known entries and side-specific exits."""
    frame, index = _validated_inputs(features, entries, exit_variant)
    selected = entries.loc[entries["candidate"].eq(candidate)]
    long_entry = np.zeros(len(frame), dtype=np.bool_)
    short_entry = np.zeros(len(frame), dtype=np.bool_)
    for row in selected.itertuples(index=False):
        position = index.get_loc(pd.Timestamp(row.signal_bar_open_at))
        _validate_entry_decision(index, position, pd.Timestamp(row.decision_time_utc))
        if row.side == "long":
            long_entry[position] = True
        elif row.side == "short":
            short_entry[position] = True
        else:
            raise ValueError("Pine stack entry side must be long or short")
    long_exit, short_exit = _exit_masks(frame, exit_variant)
    return pd.DataFrame(
        {
            "long_entry": long_entry,
            "short_entry": short_entry,
            "long_exit": long_exit.to_numpy(dtype=np.bool_),
            "short_exit": short_exit.to_numpy(dtype=np.bool_),
            "signal_name": candidate,
            "execution_authority": "none",
        },
        index=index,
    )


def _validated_inputs(
    features: pd.DataFrame,
    entries: pd.DataFrame,
    exit_variant: PineStackExitVariant,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    missing_features = sorted(_FEATURE_COLUMNS.difference(features.columns))
    missing_entries = sorted(_ENTRY_COLUMNS.difference(entries.columns))
    if missing_features or missing_entries:
        raise ValueError(
            f"Pine portfolio inputs missing features={missing_features} "
            f"entries={missing_entries}"
        )
    if exit_variant not in _EXIT_VARIANTS:
        raise ValueError(f"unknown Pine stack exit variant: {exit_variant}")
    index = pd.DatetimeIndex(features["bar_open_at"])
    if features.empty or index.tz is None or index.has_duplicates:
        raise ValueError("Pine portfolio features require unique aware bar times")
    if not index.is_monotonic_increasing:
        raise ValueError("Pine portfolio features must be chronological")
    signal_times = pd.DatetimeIndex(entries["signal_bar_open_at"])
    if not signal_times.isin(index).all():
        raise ValueError("Pine stack entries reference an unknown signal bar")
    if not entries["execution_authority"].eq("none").all():
        raise ValueError("Pine stack portfolio entries must be report-only")
    return features.reset_index(drop=True), index


def _validate_entry_decision(
    index: pd.DatetimeIndex,
    position: int,
    decision: pd.Timestamp,
) -> None:
    if position + 1 >= len(index) or decision != index[position + 1]:
        raise ValueError("Pine stack decision must equal the next native bar open")


def _exit_masks(
    frame: pd.DataFrame,
    variant: PineStackExitVariant,
) -> tuple[pd.Series, pd.Series]:
    long_exit = frame["cs_short_onset"].astype(bool).copy()
    short_exit = frame["cs_long_onset"].astype(bool).copy()
    if variant == "trend_or_cs":
        state = frame["trend_levels_state"].astype(int)
        long_exit |= state.eq(-1) & ~state.shift(1, fill_value=0).eq(-1)
        short_exit |= state.eq(1) & ~state.shift(1, fill_value=0).eq(1)
    elif variant == "tp80_or_cs":
        density = frame["tp_density_80_onset"].astype(bool)
        long_exit |= density
        short_exit |= density
    elif variant == "tp100_or_cs":
        density = frame["tp_density_100_onset"].astype(bool)
        long_exit |= density
        short_exit |= density
    return long_exit, short_exit
