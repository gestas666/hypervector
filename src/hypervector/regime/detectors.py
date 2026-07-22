"""Tunable 3-state regime labels: up | down | range (SRS_HV1_REGIME)."""

from __future__ import annotations

import pandas as pd

REGIME_LABELS = frozenset({"up", "down", "range"})


def detect_regime_ema(
    close: pd.Series,
    *,
    fast: int = 12,
    slow: int = 48,
    range_band: float = 0.001,
) -> pd.Series:
    """EMA structure detector.

    - up: fast EMA > slow EMA and relative gap > range_band
    - down: fast EMA < slow EMA and relative gap > range_band
    - range: otherwise (including warm-up NaNs → range)
    """
    if fast >= slow:
        raise ValueError("fast must be < slow")
    c = close.astype(float)
    ema_fast = c.ewm(span=fast, adjust=False).mean()
    ema_slow = c.ewm(span=slow, adjust=False).mean()
    rel = (ema_fast - ema_slow) / ema_slow.replace(0, pd.NA)
    labels = pd.Series("range", index=c.index, dtype=object)
    labels = labels.mask(rel > range_band, "up")
    labels = labels.mask(rel < -range_band, "down")
    labels = labels.fillna("range")
    # Warm-up where EMAs undefined
    labels = labels.where(ema_slow.notna(), "range")
    if not set(labels.unique()).issubset(REGIME_LABELS):
        raise RuntimeError(f"unexpected regime labels: {set(labels.unique())}")
    return labels
