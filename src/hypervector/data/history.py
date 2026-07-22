"""HL-first history merge with Binance/Bybit backfill (SRS_HV1_DATA_*)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd

from hypervector.data.cache import ParquetCache
from hypervector.data.provenance import normalize_ohlcv, summarize_provenance

Fetcher = Callable[[str, str, int], pd.DataFrame]


def merge_history(
    hl_df: pd.DataFrame | None,
    backfills: Sequence[tuple[str, pd.DataFrame]] = (),
) -> pd.DataFrame:
    """Merge HL-max with backfill frames. HL wins on timestamp overlap.

    Backfill order in ``backfills`` is priority (first listed fills first;
    later sources only fill remaining gaps). Default design: Binance then Bybit.
    """
    pieces: list[pd.DataFrame] = []
    if hl_df is not None and len(hl_df):
        pieces.append(normalize_ohlcv(hl_df, source=None if "source" in hl_df.columns else "hl"))

    claimed: set[pd.Timestamp] = set()
    if pieces:
        claimed = set(pd.to_datetime(pieces[0]["timestamp"], utc=True))

    for name, frame in backfills:
        if frame is None or len(frame) == 0:
            continue
        bf = normalize_ohlcv(frame, source=name if "source" not in frame.columns else None)
        if "source" not in frame.columns:
            bf["source"] = name
        else:
            bf = normalize_ohlcv(bf)
            # keep existing source labels but default empty to name
            bf.loc[bf["source"].isna() | (bf["source"] == ""), "source"] = name
        ts = pd.to_datetime(bf["timestamp"], utc=True)
        mask = ~ts.isin(claimed)
        if mask.any():
            kept = bf.loc[mask].copy()
            pieces.append(kept)
            claimed |= set(pd.to_datetime(kept["timestamp"], utc=True))

    if not pieces:
        return normalize_ohlcv(
            pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "source",
                ]
            ),
            source="hl",
        )

    out = pd.concat(pieces, ignore_index=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="first")
    return out.reset_index(drop=True)


def load_or_fetch_history(
    cache: ParquetCache,
    cache_key: str,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    lookback_days: int = 90,
    hl_fetcher: Fetcher | None = None,
    backfill_fetchers: Sequence[tuple[str, Fetcher]] = (),
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Cache-first load. On miss, HL-first then backfill; write cache; return provenance."""
    if not force_refresh and cache.exists(cache_key):
        df = cache.load(cache_key)
        assert df is not None
        return df, summarize_provenance(df)

    hl_df: pd.DataFrame | None = None
    if hl_fetcher is not None:
        hl_df = hl_fetcher(symbol, timeframe, lookback_days)
        if hl_df is not None and len(hl_df):
            hl_df = normalize_ohlcv(
                hl_df, source="hl" if "source" not in hl_df.columns else None
            )

    backfills: list[tuple[str, pd.DataFrame]] = []
    for name, fetcher in backfill_fetchers:
        frame = fetcher(symbol, timeframe, lookback_days)
        if frame is not None and len(frame):
            backfills.append((name, frame))

    merged = merge_history(hl_df, backfills)
    if len(merged) == 0:
        raise RuntimeError(
            f"no history for {symbol} {timeframe} lookback={lookback_days}d"
        )
    cache.save(cache_key, merged)
    return merged, summarize_provenance(merged)
