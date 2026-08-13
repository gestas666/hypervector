"""Daily association statistics for regime component attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_ic_summary(feature: pd.Series, target: pd.Series) -> dict[str, object]:
    """Summarize per-UTC-day Spearman associations without pooling rows."""
    frame = pd.DataFrame({"feature": feature, "target": target}).dropna()
    daily: dict[str, float] = {}
    for day, group in frame.groupby(frame.index.floor("1D")):
        if not _has_correlation_support(group):
            continue
        value = float(group["feature"].corr(group["target"], method="spearman"))
        if np.isfinite(value):
            daily[pd.Timestamp(day).date().isoformat()] = value
    return _summarize_daily_ics(daily)


def _has_correlation_support(group: pd.DataFrame) -> bool:
    return (
        len(group) >= 3
        and group["feature"].nunique() >= 2
        and group["target"].nunique() >= 2
    )


def _summarize_daily_ics(daily: dict[str, float]) -> dict[str, object]:
    if not daily:
        return _empty_daily_ic_summary()
    values = pd.Series(daily, dtype=float)
    deviation = float(values.std(ddof=0))
    positive = float(values.gt(0.0).mean())
    negative = float(values.lt(0.0).mean())
    return {
        "valid_days": int(len(values)),
        "median_daily_ic": float(values.median()),
        "daily_ic_iqr": float(values.quantile(0.75) - values.quantile(0.25)),
        "worst_daily_ic": float(values.min()),
        "worst_day": str(values.idxmin()),
        "icir": None if deviation == 0.0 else float(values.mean() / deviation),
        "sign_consistency": max(positive, negative),
    }


def _empty_daily_ic_summary() -> dict[str, object]:
    return {
        "valid_days": 0,
        "median_daily_ic": None,
        "daily_ic_iqr": None,
        "worst_daily_ic": None,
        "worst_day": None,
        "icir": None,
        "sign_consistency": None,
    }
