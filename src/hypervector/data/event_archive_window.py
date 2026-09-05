"""Efficient bounded Parquet window reads for the event archive."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pyarrow.dataset as ds


def read_window_rows(
    root: Path,
    days: tuple[str, ...],
    dataset: str,
    timestamp_column: str,
    start: int,
    end: int,
) -> tuple[Mapping[str, object], ...]:
    """Read filtered rows across immutable parts as one Arrow dataset."""
    paths = [
        path
        for day in days
        for path in sorted((root / day / dataset).glob("part-*.parquet"))
    ]
    if not paths:
        return ()
    evidence = ds.dataset(paths, format="parquet")
    timestamp = ds.field(timestamp_column)
    rows = evidence.to_table(filter=(timestamp >= start) & (timestamp < end))
    return tuple(_mapping(row) for row in rows.to_pylist())


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("archive window row must be an object")
    return value
