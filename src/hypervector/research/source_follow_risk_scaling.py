"""Causal signal-level allocation profiles for source-follow research."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.research.source_follow_portfolio_models import SourceSignal

SourceSizingProfile = Literal["uniform", "weak_choppy_half"]
_WEAK_CHOPPY = "TD_WEAK_CHOPPY"


def load_source_sizing_labels(path: Path) -> pd.DataFrame:
    """Load the pinned source subtype evidence used for causal sizing."""
    if not path.is_file():
        raise FileNotFoundError(f"source sizing labels are missing: {path}")
    return pd.read_parquet(path)


def apply_source_sizing_profile(
    signals: Sequence[SourceSignal],
    profile: SourceSizingProfile,
    labels: pd.DataFrame | None,
) -> tuple[SourceSignal, ...]:
    """Apply one predeclared sizing profile without deleting source signals."""
    if profile == "uniform":
        return tuple(signals)
    if profile != "weak_choppy_half":
        raise ValueError(f"unsupported source sizing profile: {profile}")
    if labels is None:
        raise ValueError("weak_choppy_half requires exact source labels")
    secondary = _exact_secondary(signals, labels)
    return tuple(
        replace(
            signal,
            allocation_multiplier=0.5 if code == _WEAK_CHOPPY else 1.0,
        )
        for signal, code in zip(signals, secondary, strict=True)
    )


def source_sizing_summary(signals: Sequence[SourceSignal]) -> dict[str, int]:
    """Count exact full- and half-sized source decisions for audit output."""
    half = sum(signal.allocation_multiplier == 0.5 for signal in signals)
    full = sum(signal.allocation_multiplier == 1.0 for signal in signals)
    if half + full != len(signals):
        raise ValueError("source sizing summary supports only full or half size")
    return {"half_size": half, "full_size": full}


def annotate_maker_decisions_with_source_sizing(
    decisions: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    """Annotate exact source entries for the weak/choppy half-size replay."""
    if not isinstance(decisions.index, pd.DatetimeIndex) or decisions.index.tz is None:
        raise ValueError("source sizing decisions require a timezone-aware index")
    if "entry_direction" not in decisions:
        raise ValueError("source sizing decisions require entry_direction")
    result = decisions.copy()
    result["entry_allocation_multiplier"] = 1.0
    entries = result["entry_direction"].isin(("long", "short"))
    signals = tuple(
        SourceSignal((timestamp + pd.Timedelta(minutes=1)).isoformat())
        for timestamp in result.index[entries]
    )
    secondary = _exact_secondary(signals, labels)
    result.loc[entries, "entry_allocation_multiplier"] = [
        0.5 if code == _WEAK_CHOPPY else 1.0 for code in secondary
    ]
    return result


def _exact_secondary(
    signals: Sequence[SourceSignal],
    labels: pd.DataFrame,
) -> tuple[str | None, ...]:
    required = {"available_at", "secondary_code"}
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(f"source sizing labels missing: {sorted(missing)}")
    available = pd.DatetimeIndex(pd.to_datetime(labels["available_at"], utc=True))
    if available.has_duplicates or not available.is_monotonic_increasing:
        raise ValueError("source sizing labels must be ordered and unique")
    signal_times = pd.DatetimeIndex(
        pd.to_datetime([signal.decision_time_utc for signal in signals], utc=True)
    )
    absent = signal_times[~signal_times.isin(available)]
    if len(absent):
        raise ValueError(f"missing exact source labels for {len(absent)} signals")
    secondary = pd.Series(labels["secondary_code"].to_numpy(), index=available)
    values = secondary.reindex(signal_times)
    return tuple(None if pd.isna(value) else str(value) for value in values)
