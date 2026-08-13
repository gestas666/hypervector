"""Creator-position input normalization for Hypervelocity research reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)
from hypervector.research.hypervelocity_source_schedule import (
    merge_supplemental_positions,
)


def _optional_timestamp(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def source_positions(
    positions_path: Path,
    supplemental_path: Path | None,
) -> pd.DataFrame:
    """Load creator positions and optionally merge supplemental outcomes."""
    positions = pd.read_csv(positions_path)
    if supplemental_path is None:
        return positions
    supplemental = pd.read_csv(supplemental_path)
    logical = logical_source_positions(positions)
    merged = merge_supplemental_positions(logical, supplemental)
    exit_price = pd.to_numeric(merged.get("exit_price"), errors="coerce")
    close_ts = merged.get("close_ts", pd.Series(pd.NaT, index=merged.index))
    return pd.DataFrame(
        {
            "open_time_utc": [
                pd.Timestamp(value).isoformat() for value in merged.open_ts
            ],
            "close_time_utc": [_optional_timestamp(value) for value in close_ts],
            "side": merged.side.astype(str),
            "entry_price": pd.to_numeric(merged.entry_price, errors="raise"),
            "exit_price": exit_price,
            "status": ["closed" if pd.notna(value) else "open" for value in exit_price],
            "timestamp_provenance": merged.timestamp_provenance.astype(str),
        }
    )
