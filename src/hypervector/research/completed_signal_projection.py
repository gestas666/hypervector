"""Shared projection of completed higher-timeframe entries onto execution bars."""

from __future__ import annotations

import numpy as np
import pandas as pd


def empty_directional_signals(
    index: pd.DatetimeIndex,
    *,
    signal_name: str,
    source_time_column: str,
) -> pd.DataFrame:
    """Return one inactive signal frame aligned to execution bars."""
    return pd.DataFrame(
        {
            "entry_direction": pd.Series(None, index=index, dtype=object),
            "long_entry": False,
            "short_entry": False,
            "long_exit": False,
            "short_exit": False,
            "signal_name": signal_name,
            "stop_price": np.nan,
            source_time_column: pd.Series(
                pd.NaT,
                index=index,
                dtype="datetime64[ns, UTC]",
            ),
        },
        index=index,
    )


def project_completed_entries(
    output: pd.DataFrame,
    state: pd.DataFrame,
    *,
    signal_hours: int,
    execution_minutes: int,
    state_stop_column: str,
    source_time_column: str,
    label: str,
) -> None:
    """Project fresh completed-bar entries for exactly next-open execution."""
    for signal_time, row in state.iterrows():
        direction = _row_direction(row)
        if direction is None:
            continue
        decision_row = (
            pd.Timestamp(signal_time)
            + pd.Timedelta(hours=signal_hours)
            - pd.Timedelta(minutes=execution_minutes)
        )
        if decision_row not in output.index:
            raise RuntimeError(f"completed {label} bar is missing its decision row")
        output.loc[decision_row, "entry_direction"] = direction
        output.loc[decision_row, f"{direction}_entry"] = True
        opposite = "long_exit" if direction == "short" else "short_exit"
        output.loc[decision_row, opposite] = True
        output.loc[decision_row, "stop_price"] = float(row[state_stop_column])
        output.loc[decision_row, source_time_column] = signal_time


def _row_direction(row: pd.Series) -> str | None:
    if bool(row["long_entry"]):
        return "long"
    if bool(row["short_entry"]):
        return "short"
    return None
