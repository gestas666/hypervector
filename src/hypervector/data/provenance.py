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

REQUIRED_SOURCES = frozenset({"hl", "hl_gap_fill", "binance", "bybit", "fixture"})


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


TIMEFRAME_SECONDS: dict[str, int] = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


def timeframe_delta(timeframe: str | None) -> pd.Timedelta | None:
    """Bar spacing for a supported research timeframe; ``None`` when unknown."""
    seconds = TIMEFRAME_SECONDS.get(timeframe or "")
    return pd.Timedelta(seconds=seconds) if seconds is not None else None


def _iso_utc(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).tz_convert("UTC").isoformat()


def summarize_provenance(
    df: pd.DataFrame, timeframe: str | None = None
) -> dict[str, Any]:
    """Composition summary: sources, fractions, bar count, window and gap stats.

    Gaps are measured in bars of ``timeframe``; when it is omitted or unknown the
    bar spacing is inferred from the most common timestamp delta. ``start`` and
    ``end`` are the first and last bar as ISO-8601 UTC strings. Every value is
    derived from the frame alone, so the summary is deterministic and JSON-safe.
    """
    expected = timeframe_delta(timeframe)
    if df.empty:
        return {
            "sources": {},
            "fractions": {},
            "bar_count": 0,
            "gaps": {"count": 0, "max_gap_bars": 0},
            "start": None,
            "end": None,
            "timeframe": timeframe,
            "bar_seconds": int(expected.total_seconds()) if expected is not None else None,
        }
    work = df if "source" in df.columns else df.assign(source="unknown")
    counts = work["source"].value_counts().to_dict()
    total = int(len(work))
    fractions = {k: float(v) / total for k, v in counts.items()}
    gaps: dict[str, int] = {"count": 0, "max_gap_bars": 0}
    start: str | None = None
    end: str | None = None
    if "timestamp" in work.columns:
        ts = pd.to_datetime(work["timestamp"], utc=True).sort_values()
        start, end = _iso_utc(ts.iloc[0]), _iso_utc(ts.iloc[-1])
        deltas = ts.diff().dropna()
        if expected is None:
            positive = deltas[deltas > pd.Timedelta(0)]
            expected = (
                positive.mode().iloc[0] if len(positive) else pd.Timedelta(minutes=1)
            )
        if total > 1:
            multi = deltas[deltas > expected * 1.5]
            gaps["count"] = int(len(multi))
            if len(multi):
                # Timedelta / Timedelta → float (not Timedelta); use round() builtin
                max_ratio = multi.max() / expected
                gaps["max_gap_bars"] = int(round(float(max_ratio)))
    bar_seconds = int(expected.total_seconds()) if expected is not None else None
    label = timeframe
    if label is None and bar_seconds is not None:
        label = next(
            (name for name, sec in TIMEFRAME_SECONDS.items() if sec == bar_seconds),
            None,
        )
    return {
        "sources": {str(k): int(v) for k, v in counts.items()},
        "fractions": fractions,
        "bar_count": total,
        "gaps": gaps,
        "start": start,
        "end": end,
        "timeframe": label,
        "bar_seconds": bar_seconds,
    }
