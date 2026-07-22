"""Live research history: HL-max first, Binance then Bybit backfill, cache-first."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector.config import DEFAULT_LOOKBACK, ResearchConfig
from hypervector.data.backfill import fetch_binance_ohlcv, fetch_bybit_ohlcv
from hypervector.data.cache import ParquetCache
from hypervector.data.history import merge_history
from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.data.provenance import normalize_ohlcv, summarize_provenance
from hypervector.infra import ensure_data_layout

logger = logging.getLogger(__name__)

_TF_BARS_PER_DAY = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24}


def cache_key(symbol: str, timeframe: str, lookback_days: int) -> str:
    return f"{symbol.upper()}_{timeframe}_{lookback_days}d"


def live_hl_fetcher(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    return fetch_hl_ohlcv(symbol, timeframe, lookback_days)


def live_binance_fetcher(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    return fetch_binance_ohlcv(symbol, timeframe, lookback_days)


def live_bybit_fetcher(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    return fetch_bybit_ohlcv(symbol, timeframe, lookback_days)


def _expected_bars(timeframe: str, lookback_days: int) -> int:
    return int(lookback_days * _TF_BARS_PER_DAY.get(timeframe, 1440))


def load_research_history(
    data_root: Path | str,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    lookback_days: int = DEFAULT_LOOKBACK,
    strict_hl_only: bool = False,
    force_refresh: bool = False,
    config: ResearchConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Cache-first live history: HL max, then Binance → Bybit gap fill.

    HL wins on timestamp overlap. Provenance is per-bar ``source``.
    Bybit is only called when HL+Binance still leave a material hole
    (<95% of expected bars for the lookback).
    """
    if config is not None:
        symbol = config.symbol
        timeframe = config.timeframe
        lookback_days = config.lookback_days
        strict_hl_only = config.strict_hl_only

    root = ensure_data_layout(data_root).root
    cache = ParquetCache(root / "cache")
    key = cache_key(symbol, timeframe, lookback_days)

    if not force_refresh and cache.exists(key):
        df = cache.load(key)
        assert df is not None
        return df, summarize_provenance(df)

    hl_df = live_hl_fetcher(symbol, timeframe, lookback_days)
    if hl_df is not None and len(hl_df):
        hl_df = normalize_ohlcv(hl_df, source="hl" if "source" not in hl_df.columns else None)
    else:
        hl_df = None

    backfills: list[tuple[str, pd.DataFrame]] = []
    if not strict_hl_only:
        bn = live_binance_fetcher(symbol, timeframe, lookback_days)
        if bn is not None and len(bn):
            backfills.append(("binance", bn))

        partial = merge_history(hl_df, backfills)
        expected = _expected_bars(timeframe, lookback_days)
        coverage = len(partial) / expected if expected else 1.0
        if coverage < 0.95:
            logger.info(
                "HL+Binance coverage %.1f%% < 95%% — fetching Bybit backfill",
                100 * coverage,
            )
            bb = live_bybit_fetcher(symbol, timeframe, lookback_days)
            if bb is not None and len(bb):
                backfills.append(("bybit", bb))
        else:
            logger.info(
                "HL+Binance coverage %.1f%% — skip Bybit",
                100 * coverage,
            )

    merged = merge_history(hl_df, backfills)
    if len(merged) == 0:
        raise RuntimeError(
            f"no history for {symbol} {timeframe} lookback={lookback_days}d"
        )
    cache.save(key, merged)
    return merged, summarize_provenance(merged)
