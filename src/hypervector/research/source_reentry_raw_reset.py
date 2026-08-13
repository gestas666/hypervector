"""Creator alignment for raw 5m resets hidden by confirmed hysteresis."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)

_LABEL_COLUMNS = frozenset(
    {
        "available_at",
        "primary_code",
        "secondary_code",
        "raw_primary_code",
        "raw_secondary_code",
    }
)


def raw_reset_reentry_evidence(
    positions: pd.DataFrame,
    labels: pd.DataFrame,
) -> dict[str, object]:
    """Measure raw reset-and-return events between creator same-side trades."""
    logical = logical_source_positions(positions)
    causal_labels = _causal_labels(labels)
    windows: list[dict[str, object]] = []
    for index in range(1, len(logical)):
        previous = logical.iloc[index - 1]
        current = logical.iloc[index]
        fact = _same_side_window(previous, current, causal_labels)
        if fact is not None:
            windows.append(fact)
    return {
        "logical_positions": len(logical),
        "same_side_nonoverlapping_reentries": len(windows),
        "raw_reset_return_windows": _count(windows, "raw_reset_return"),
        "hidden_raw_reset_return_windows": sum(
            row["raw_reset_return"] is True and row["confirmed_reset"] is False
            for row in windows
        ),
        "raw_side_aligned_at_entry": _count(windows, "raw_side_aligned_at_entry"),
        "confirmed_side_aligned_at_entry": _count(
            windows, "confirmed_side_aligned_at_entry"
        ),
        "windows": windows,
    }


def _causal_labels(labels: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_LABEL_COLUMNS - set(labels.columns))
    if missing:
        raise ValueError(f"source labels missing columns: {missing}")
    frame = labels.copy()
    frame["available_at"] = pd.to_datetime(
        frame["available_at"], utc=True, errors="raise"
    )
    if frame["available_at"].duplicated().any():
        raise ValueError("source labels contain duplicate availability timestamps")
    return frame.sort_values("available_at").reset_index(drop=True)


def _same_side_window(
    previous: pd.Series,
    current: pd.Series,
    labels: pd.DataFrame,
) -> dict[str, object] | None:
    if current["side"] != previous["side"] or pd.isna(previous["close_ts"]):
        return None
    delay = (current["open_ts"] - previous["close_ts"]).total_seconds()
    if delay < 0.0:
        return None
    selected = labels.loc[
        labels["available_at"].gt(previous["close_ts"])
        & labels["available_at"].le(current["open_ts"])
    ]
    target = str(current["side"])
    raw_sides = _sides(selected, "raw_primary_code", "raw_secondary_code")
    confirmed_sides = _sides(selected, "primary_code", "secondary_code")
    return {
        "side": target,
        "previous_close_utc": previous["close_ts"].isoformat(),
        "current_open_utc": current["open_ts"].isoformat(),
        "delay_seconds": float(delay),
        "causal_label_rows": len(selected),
        "raw_reset_return": _reset_return(raw_sides, target),
        "confirmed_reset": any(value != target for value in confirmed_sides),
        "raw_side_at_entry": raw_sides[-1] if raw_sides else None,
        "confirmed_side_at_entry": (confirmed_sides[-1] if confirmed_sides else None),
        "raw_side_aligned_at_entry": bool(raw_sides and raw_sides[-1] == target),
        "confirmed_side_aligned_at_entry": bool(
            confirmed_sides and confirmed_sides[-1] == target
        ),
    }


def _sides(
    labels: pd.DataFrame,
    primary_column: str,
    secondary_column: str,
) -> list[str | None]:
    return [
        _direction(primary, secondary)
        for primary, secondary in zip(
            labels[primary_column], labels[secondary_column], strict=True
        )
    ]


def _direction(primary: object, secondary: object) -> str | None:
    primary_code = str(primary)
    secondary_code = str(secondary)
    if primary_code == "TREND_UP" or (
        primary_code == "BREAKOUT" and secondary_code == "BK_UPWARD"
    ):
        return "long"
    if primary_code == "TREND_DOWN" or (
        primary_code == "BREAKOUT" and secondary_code == "BK_DOWNWARD"
    ):
        return "short"
    return None


def _reset_return(values: Iterable[str | None], target: str) -> bool:
    reset_seen = False
    for value in values:
        if value != target:
            reset_seen = True
        elif reset_seen:
            return True
    return False


def _count(rows: list[dict[str, object]], key: str) -> int:
    return sum(row[key] is True for row in rows)
