"""Causal source-regime subtype features for Hypervelocity risk annotation."""

from __future__ import annotations

import numpy as np
import pandas as pd

SOURCE_FEATURE_NAMES: tuple[str, ...] = (
    "source_confidence",
    "source_volume_ratio",
    "source_state_age_minutes",
    "source_is_breakout",
    "source_is_strong",
    "source_is_weak_choppy",
    "source_is_exhaustion",
    "source_is_high_vol",
    "source_is_low_vol",
    "source_is_normal_vol",
    "source_raw_primary_agreement",
    "source_raw_secondary_agreement",
)


def _validated_labels(labels: pd.DataFrame) -> pd.DataFrame:
    required = {
        "available_at",
        "primary_code",
        "secondary_code",
        "confidence",
        "raw_primary_code",
        "raw_secondary_code",
        "volume_ratio",
    }
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(f"source feature labels missing: {sorted(missing)}")
    if not isinstance(labels.index, pd.DatetimeIndex) or labels.index.tz is None:
        raise ValueError("source feature labels require a timezone-aware source index")
    output = labels.copy()
    output["available_at"] = pd.to_datetime(output["available_at"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    available = pd.DatetimeIndex(output["available_at"])
    if (
        available.has_duplicates
        or not available.is_monotonic_increasing
        or not (available > labels.index).all()
    ):
        raise ValueError(
            "source label availability must be ordered, unique, and causal"
        )
    return output


def _state_start(labels: pd.DataFrame) -> pd.Series:
    state = labels["primary_code"].astype("string").fillna("<NA>")
    state += ":" + labels["secondary_code"].astype("string").fillna("<NA>")
    changed = state.ne(state.shift(1)).fillna(True)
    starts = labels["available_at"].where(changed).ffill()
    return pd.Series(starts.to_numpy(), index=labels.index)


def _aligned_labels(
    labels: pd.DataFrame,
    signal_times: pd.DatetimeIndex,
) -> pd.DataFrame:
    if signal_times.tz is None or signal_times.has_duplicates:
        raise ValueError("source feature signals require unique timezone-aware times")
    signals = pd.DataFrame(
        {
            "signal_time": signal_times.astype("datetime64[ns, UTC]"),
            "signal_order": np.arange(len(signal_times)),
        }
    ).sort_values("signal_time", kind="stable")
    source = labels.copy()
    source["source_state_start"] = _state_start(source).to_numpy()
    aligned = pd.merge_asof(
        signals,
        source.sort_values("available_at", kind="stable"),
        left_on="signal_time",
        right_on="available_at",
        direction="backward",
        allow_exact_matches=True,
    )
    return aligned.sort_values("signal_order", kind="stable").reset_index(drop=True)


def source_regime_features(
    labels: pd.DataFrame,
    signal_times: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Align only source labels available at or before each decision signal."""
    source = _validated_labels(labels)
    aligned = _aligned_labels(source, signal_times)
    secondary = aligned["secondary_code"].astype("string")
    primary = aligned["primary_code"].astype("string")
    state_age = (
        aligned["signal_time"] - pd.to_datetime(aligned["source_state_start"], utc=True)
    ).dt.total_seconds() / 60.0
    output = pd.DataFrame(
        {
            "source_confidence": pd.to_numeric(
                aligned["confidence"], errors="coerce"
            ).to_numpy(),
            "source_volume_ratio": pd.to_numeric(
                aligned["volume_ratio"], errors="coerce"
            ).to_numpy(),
            "source_state_age_minutes": state_age.to_numpy(),
            "source_is_breakout": primary.eq("BREAKOUT").astype(float).to_numpy(),
            "source_is_strong": secondary.str.contains("_STRONG_", na=False)
            .astype(float)
            .to_numpy(),
            "source_is_weak_choppy": secondary.str.endswith("_WEAK_CHOPPY", na=False)
            .astype(float)
            .to_numpy(),
            "source_is_exhaustion": secondary.str.contains(
                "EXHAUSTION|CAPITULATION|PARABOLIC", regex=True, na=False
            )
            .astype(float)
            .to_numpy(),
            "source_is_high_vol": secondary.str.endswith("_HIGH_VOL", na=False)
            .astype(float)
            .to_numpy(),
            "source_is_low_vol": secondary.str.endswith("_LOW_VOL", na=False)
            .astype(float)
            .to_numpy(),
            "source_is_normal_vol": secondary.str.endswith("_NORMAL_VOL", na=False)
            .astype(float)
            .to_numpy(),
            "source_raw_primary_agreement": primary.eq(
                aligned["raw_primary_code"].astype("string")
            )
            .astype(float)
            .to_numpy(),
            "source_raw_secondary_agreement": secondary.eq(
                aligned["raw_secondary_code"].astype("string")
            )
            .astype(float)
            .to_numpy(),
        },
        index=signal_times,
    )
    unavailable = aligned["available_at"].isna().to_numpy()
    output.loc[unavailable, :] = np.nan
    return output


def source_feature_coverage(rows: pd.DataFrame) -> dict[str, int]:
    """Count non-missing source-state values in assembled model rows."""
    missing = set(SOURCE_FEATURE_NAMES).difference(rows.columns)
    if missing:
        raise ValueError(f"source model rows missing features: {sorted(missing)}")
    return {name: int(rows[name].notna().sum()) for name in SOURCE_FEATURE_NAMES}
