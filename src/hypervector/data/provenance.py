"""Per-bar and run-level data provenance (SRS_HV1_DATA_PROVENANCE)."""

from __future__ import annotations

from typing import Any

import pandas as pd

OHLCV_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
]

REQUIRED_SOURCES = frozenset({"hl", "binance", "bybit", "fixture"})


def normalize_ohlcv(df: pd.DataFrame, source: str | None = None) -> pd.DataFrame:
    """Ensure OHLCV + source columns; optionally stamp a uniform source."""
    out = df.copy()
    if "timestamp" not in out.columns and out.index.name == "timestamp":
        out = out.reset_index()
    missing = [c for c in OHLCV_COLUMNS if c not in out.columns and c != "source"]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    if "source" not in out.columns:
        if source is None:
            raise ValueError("source column required or source= must be set")
        out["source"] = source
    elif source is not None:
        out["source"] = source
    out = out[OHLCV_COLUMNS].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = out[col].astype(float)
    out["source"] = out["source"].astype(str)
    return out.sort_values("timestamp").reset_index(drop=True)


def summarize_provenance(df: pd.DataFrame) -> dict[str, Any]:
    """Composition summary: sources, fractions, bar count, simple gap stats."""
    if df.empty:
        return {
            "sources": {},
            "fractions": {},
            "bar_count": 0,
            "gaps": {"count": 0, "max_gap_bars": 0},
        }
    work = df if "source" in df.columns else df.assign(source="unknown")
    counts = work["source"].value_counts().to_dict()
    total = int(len(work))
    fractions = {k: float(v) / total for k, v in counts.items()}
    gaps: dict[str, int] = {"count": 0, "max_gap_bars": 0}
    if "timestamp" in work.columns and total > 1:
        ts = pd.to_datetime(work["timestamp"], utc=True).sort_values()
        deltas = ts.diff().dropna()
        # 1m bars → expected 60s; count multi-bar holes
        expected = pd.Timedelta(minutes=1)
        multi = deltas[deltas > expected * 1.5]
        gaps["count"] = int(len(multi))
        if len(multi):
            # Timedelta / Timedelta → float (not Timedelta); use round() builtin
            max_ratio = multi.max() / expected
            gaps["max_gap_bars"] = int(round(float(max_ratio)))
    return {
        "sources": {str(k): int(v) for k, v in counts.items()},
        "fractions": fractions,
        "bar_count": total,
        "gaps": gaps,
    }
