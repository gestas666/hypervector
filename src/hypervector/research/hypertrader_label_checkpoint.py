"""Exact checkpoint reconstruction for pinned Hypertrader regime labels."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pandas as pd


class LabelCheckpointConfig(Protocol):
    """Configuration fields that affect checkpoint state reconstruction."""

    min_duration_bars: int
    breakout_ttl_bars: int
    breakout_cooldown_bars: int


class LabelCheckpointState(Protocol):
    """Mutable upstream state fields restored at an incremental boundary."""

    current: object | None
    pending: object | None
    pending_count: int
    transition_blocked_until: float
    _breakout_expires_at: float
    _breakout_cooldown_until: float
    _pre_breakout: object | None


def _optional_text(value: object) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _timestamp_ms(value: object) -> float:
    return float(pd.Timestamp(value).timestamp() * 1_000)


def _regime_from_row(
    row: pd.Series,
    timestamp: object,
    regime_factory: Callable[..., object],
    primary_factory: Callable[[str], object],
    *,
    raw: bool,
) -> object:
    prefix = "raw_" if raw else ""
    volume_ratio = row.get("volume_ratio")
    indicators = {} if pd.isna(volume_ratio) else {"volume_ratio": float(volume_ratio)}
    return regime_factory(
        coin="BTC",
        timeframe="5m",
        primary=primary_factory(str(row[f"{prefix}primary_code"])),
        secondary=_optional_text(row.get(f"{prefix}secondary_code")),
        confidence=float(row[f"{prefix}confidence"]),
        classified_at=_timestamp_ms(timestamp),
        indicators=indicators,
    )


def _breakout_onset(labels: pd.DataFrame) -> pd.Timestamp | None:
    breakout = labels["primary_code"].eq("BREAKOUT")
    if not breakout.any():
        return None
    position = int(breakout.to_numpy().nonzero()[0][-1])
    while position > 0 and bool(breakout.iloc[position - 1]):
        position -= 1
    return pd.Timestamp(labels.index[position])


def _validate_checkpoint(
    labels: pd.DataFrame,
    config: LabelCheckpointConfig,
    checkpoint: pd.Timestamp,
) -> None:
    required = {
        "available_at",
        "primary_code",
        "secondary_code",
        "confidence",
        "raw_primary_code",
        "raw_secondary_code",
        "raw_confidence",
        "volume_ratio",
    }
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(f"prior labels are missing columns: {sorted(missing)}")
    if labels.empty:
        raise ValueError("prior labels cannot be empty")
    if not isinstance(labels.index, pd.DatetimeIndex) or labels.index.tz is None:
        raise ValueError("prior label index must be timezone-aware")
    if not labels.index.is_monotonic_increasing or labels.index.has_duplicates:
        raise ValueError("prior label index must be ordered and unique")
    expected = pd.date_range(labels.index[0], labels.index[-1], freq="5min", tz="UTC")
    if not labels.index.equals(expected):
        raise ValueError("prior labels must be contiguous 5m rows")
    available = pd.to_datetime(labels["available_at"], utc=True)
    if available.iloc[-1] != checkpoint:
        raise ValueError("prior label checkpoint must end exactly at --start")
    if not available.reset_index(drop=True).equals(
        pd.Series(labels.index + pd.Timedelta(minutes=5))
    ):
        raise ValueError("prior label availability must equal bar close time")
    if str(labels.iloc[-1]["primary_code"]) == "UNKNOWN":
        raise ValueError("prior label checkpoint cannot end in UNKNOWN")
    if str(labels.iloc[-1]["raw_primary_code"]) == "UNKNOWN":
        raise ValueError("prior raw checkpoint cannot end in UNKNOWN")
    onset = _breakout_onset(labels)
    if onset is None:
        return
    cooldown_bars = config.breakout_ttl_bars + config.breakout_cooldown_bars
    if checkpoint < onset + pd.Timedelta(minutes=5 * cooldown_bars):
        raise ValueError("prior label checkpoint is inside breakout cooldown")


def _trailing_raw_count(labels: pd.DataFrame, primary: str) -> int:
    count = 0
    for value in reversed(labels["raw_primary_code"].astype(str).tolist()):
        if value == "UNKNOWN":
            continue
        if value != primary:
            break
        count += 1
    return count


def seed_label_state(
    state: LabelCheckpointState,
    labels: pd.DataFrame,
    config: LabelCheckpointConfig,
    regime_factory: Callable[..., object],
    primary_factory: Callable[[str], object],
    checkpoint: pd.Timestamp,
) -> None:
    """Reconstruct a non-breakout upstream state at an immutable checkpoint."""
    _validate_checkpoint(labels, config, checkpoint)
    last = labels.iloc[-1]
    state.current = _regime_from_row(
        last, labels.index[-1], regime_factory, primary_factory, raw=False
    )
    current_code = str(last["primary_code"])
    confirmed = labels["primary_code"].astype(str)
    changes = confirmed.ne(confirmed.shift())
    onset = pd.Timestamp(labels.index[changes.to_numpy().nonzero()[0][-1]])
    state.transition_blocked_until = _timestamp_ms(onset) + (
        config.min_duration_bars * 300_000
    )
    raw_code = str(last["raw_primary_code"])
    state.pending = None
    state.pending_count = 0
    if raw_code not in {"UNKNOWN", current_code}:
        state.pending = _regime_from_row(
            last, labels.index[-1], regime_factory, primary_factory, raw=True
        )
        state.pending_count = _trailing_raw_count(labels, raw_code)
    state._breakout_expires_at = 0.0
    state._breakout_cooldown_until = 0.0
    state._pre_breakout = None
