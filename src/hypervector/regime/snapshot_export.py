"""Export canonical backend regime telemetry as per-bar JSON snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.regime.classifier import hyperliquid_native_regime_config
from hypervector.regime.ultimate import detect_ultimate_regime

SnapshotValue = str | int | float | bool | None
Snapshot = dict[str, SnapshotValue]


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.index, pd.DatetimeIndex):
        out = df.copy()
    elif "timestamp" in df.columns:
        out = df.copy()
        out.index = pd.DatetimeIndex(pd.to_datetime(out["timestamp"], utc=True))
    else:
        raise ValueError("regime snapshot bars require a DatetimeIndex or timestamp")
    if out.index.tz is None:
        raise ValueError("regime snapshot timestamps must be timezone-aware")
    out.index = out.index.tz_convert("UTC")
    return out


def _merge_book_features(
    df: pd.DataFrame,
    data_root: Path,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    candidate = (
        data_root / "cache" / "aligned" / f"{symbol}_{timeframe}_aligned_book.parquet"
    )
    if not candidate.is_file():
        return df
    book = pd.read_parquet(candidate)
    if "timestamp" not in book.columns and not isinstance(book.index, pd.DatetimeIndex):
        raise ValueError(f"aligned book cache lacks timestamps: {candidate}")
    book = _ensure_datetime_index(book)
    if book.index.has_duplicates:
        raise ValueError(
            f"aligned book cache contains duplicate timestamps: {candidate}"
        )
    if not book.index.is_monotonic_increasing:
        book = book.sort_index()
    columns = _book_columns(book)
    if not columns:
        raise ValueError(f"aligned book cache lacks supported features: {candidate}")
    joined = book[columns].reindex(df.index, method="ffill", tolerance="1min")
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = joined[column]
    return out


def _book_columns(df: pd.DataFrame) -> list[str]:
    supported = (
        "spread_bps",
        "order_pressure_index",
        "obi_5",
        "book_depth_ratio",
        "book_pressure",
    )
    return [column for column in supported if column in df.columns]


def _microstructure(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series, str]:
    pressure_name = next(
        (
            name
            for name in ("order_pressure_index", "obi_5", "book_pressure")
            if name in df.columns
        ),
        None,
    )
    unavailable = pd.Series(np.nan, index=df.index, dtype=float)
    if pressure_name is None or "spread_bps" not in df.columns:
        return unavailable, unavailable.copy(), unavailable.copy(), "not_available"
    depth = (
        df["book_depth_ratio"].astype(float)
        if "book_depth_ratio" in df.columns
        else unavailable.copy()
    )
    return (
        df[pressure_name].astype(float),
        df["spread_bps"].astype(float),
        depth,
        f"aligned_{pressure_name}",
    )


def _funding_zscore(df: pd.DataFrame) -> tuple[pd.Series, str]:
    if "funding_rate" not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float), "not_available"
    rates = df["funding_rate"].astype(float)
    mean = rates.rolling(48, min_periods=10).mean()
    standard_deviation = rates.rolling(48, min_periods=10).std().replace(0.0, np.nan)
    return (rates - mean) / standard_deviation, "bar_funding_rate"


def build_regime_snapshots(
    df: pd.DataFrame,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    data_root: Path | str = "data",
    max_bars: int = 1500,
) -> list[Snapshot]:
    """Build point-in-time snapshots from the production regime classifier."""
    if max_bars < 1:
        raise ValueError("max_bars must be >= 1")
    indexed = _ensure_datetime_index(df)
    indexed = _merge_book_features(indexed, Path(data_root), symbol, timeframe)
    regime = detect_ultimate_regime(
        indexed,
        config=hyperliquid_native_regime_config(),
    )
    opi, spread, depth, microstructure_source = _microstructure(indexed)
    funding_zscore, funding_source = _funding_zscore(indexed)
    start = max(0, len(indexed) - max_bars)
    return [
        _snapshot_row(
            indexed,
            regime,
            opi,
            spread,
            depth,
            funding_zscore,
            microstructure_source,
            funding_source,
            position,
        )
        for position in range(start, len(indexed))
    ]


def _snapshot_row(
    bars: pd.DataFrame,
    regime: pd.DataFrame,
    opi: pd.Series,
    spread: pd.Series,
    depth: pd.Series,
    funding_zscore: pd.Series,
    microstructure_source: str,
    funding_source: str,
    position: int,
) -> Snapshot:
    timestamp = bars.index[position]
    snapshot = _bar_snapshot(bars, timestamp, position)
    snapshot.update(_regime_snapshot(regime, position))
    snapshot.update(
        {
            "opi": _rounded(opi.iloc[position], 4),
            "spread_bps": _rounded(spread.iloc[position], 3),
            "bid_depth_ratio": _rounded(depth.iloc[position], 3),
            "microstructure_source": microstructure_source,
            "funding_zscore": _rounded(funding_zscore.iloc[position], 3),
            "funding_source": funding_source,
        }
    )
    return snapshot


def _bar_snapshot(
    bars: pd.DataFrame,
    timestamp: pd.Timestamp,
    position: int,
) -> Snapshot:
    return {
        "timestamp_str": timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_ms": int(timestamp.value // 1_000_000),
        "open": round(float(bars["open"].iloc[position]), 2),
        "close": round(float(bars["close"].iloc[position]), 2),
        "high": round(float(bars["high"].iloc[position]), 2),
        "low": round(float(bars["low"].iloc[position]), 2),
        "volume": round(float(bars["volume"].iloc[position]), 5),
    }


def _regime_snapshot(regime: pd.DataFrame, position: int) -> Snapshot:
    return {
        "regime_state": str(regime["regime_state"].iloc[position]),
        "regime_reason": str(regime["regime_reason"].iloc[position]),
        "regime_strength_score": _rounded(regime["confidence"].iloc[position], 4),
        "regime_score_source": ("mean_multitimeframe_ema_gap_strength_percentile_rank"),
        "confidence_is_gate": False,
        "bbwp_percentile": _rounded(regime["bbwp_percentile"].iloc[position], 2),
        "compression_ready": bool(regime["compression_ready"].iloc[position]),
        "ema_gap_bps_signed": _rounded(regime["ema_gap_bps_signed"].iloc[position], 2),
        "rsi": _rounded(regime["rsi"].iloc[position], 2),
        "rsi_ema": _rounded(regime["rsi_ema"].iloc[position], 2),
        "rsi_cross_direction": _optional_text(
            regime["rsi_cross_direction"].iloc[position]
        ),
        "tactical_breakout_direction": _optional_text(
            regime["tactical_breakout_direction"].iloc[position]
        ),
        "breakout_volume_ratio": _rounded(
            regime["breakout_volume_ratio"].iloc[position], 3
        ),
        "prior_range_high": _rounded(regime["prior_range_high"].iloc[position], 2),
        "prior_range_low": _rounded(regime["prior_range_low"].iloc[position], 2),
        "trend_1m": str(regime["state_1m"].iloc[position]),
        "trend_5m": str(regime["state_5m"].iloc[position]),
        "trend_15m": str(regime["context_15m"].iloc[position]),
        "long_weight": _rounded(regime["long_weight"].iloc[position], 2),
        "short_weight": _rounded(regime["short_weight"].iloc[position], 2),
    }


def _rounded(value: object, decimals: int) -> float | None:
    number = float(value)
    return round(number, decimals) if np.isfinite(number) else None


def _optional_text(value: object) -> str | None:
    return None if pd.isna(value) else str(value)


def export_regime_snapshots(
    df: pd.DataFrame,
    out_path: Path | str,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    data_root: Path | str = "data",
    max_bars: int = 1500,
) -> dict[str, object]:
    """Write canonical regime snapshot JSON and return its audit summary."""
    snapshots = build_regime_snapshots(
        df,
        symbol=symbol,
        timeframe=timeframe,
        data_root=data_root,
        max_bars=max_bars,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshots, allow_nan=False), encoding="utf-8")
    states = pd.Series([snapshot["regime_state"] for snapshot in snapshots])
    return _export_summary(output, symbol, timeframe, snapshots, states)


def _export_summary(
    output: Path,
    symbol: str,
    timeframe: str,
    snapshots: list[Snapshot],
    states: pd.Series,
) -> dict[str, object]:
    return {
        "ok": True,
        "out": str(output),
        "snapshots": len(snapshots),
        "symbol": symbol,
        "timeframe": timeframe,
        "first_timestamp": snapshots[0]["timestamp_str"] if snapshots else None,
        "last_timestamp": snapshots[-1]["timestamp_str"] if snapshots else None,
        "state_distribution": states.value_counts().to_dict() if snapshots else {},
    }
