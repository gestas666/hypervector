"""Regime detection quality metrics — reported, never gated."""

from __future__ import annotations

from typing import Any

import pandas as pd


def regime_detection_metrics(labels: pd.Series) -> dict[str, Any]:
    """Duration stats, flip rate, % time in each state."""
    if len(labels) == 0:
        return {
            "pct_up": 0.0,
            "pct_down": 0.0,
            "pct_range": 0.0,
            "flip_rate": 0.0,
            "mean_duration": 0.0,
            "n_bars": 0,
        }
    s = labels.astype(str)
    n = len(s)
    counts = s.value_counts()
    flips = int((s != s.shift(1)).sum()) - 1  # first bar is not a flip
    flips = max(flips, 0)
    # run lengths
    run_id = (s != s.shift(1)).cumsum()
    durations = s.groupby(run_id).size()
    return {
        "pct_up": float(counts.get("up", 0)) / n,
        "pct_down": float(counts.get("down", 0)) / n,
        "pct_range": float(counts.get("range", 0)) / n,
        "flip_rate": float(flips) / max(n - 1, 1),
        "mean_duration": float(durations.mean()) if len(durations) else 0.0,
        "n_bars": n,
    }
