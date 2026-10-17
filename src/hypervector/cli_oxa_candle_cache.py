"""Explicit one-minute research-cache installation for acquired candles."""

from __future__ import annotations

import argparse
from pathlib import Path


def validate_candle_cache_interval(args: argparse.Namespace) -> None:
    """Reject intervals unsupported by the one-minute continuity repair."""
    if args.timeframe != "1m":
        raise ValueError(
            "research cache installation requires --timeframe 1m; "
            "omit --install-research-cache to acquire other candle intervals"
        )


def install_candle_cache(
    args: argparse.Namespace, report: dict[str, object]
) -> tuple[str, int]:
    """Install a whole-day minute cache with explicitly labeled gap fills."""
    import pandas as pd

    from hypervector.data.cache import ParquetCache
    from hypervector.data.oxa_candles import repair_candle_cadence
    from hypervector.data.pipeline import cache_key

    validate_candle_cache_interval(args)
    duration_days = (args.end - args.start).total_seconds() / 86_400
    if not duration_days.is_integer():
        raise ValueError("research cache installation requires a whole-day window")
    candles_path = report.get("candles_path")
    if not isinstance(candles_path, str):
        raise ValueError("candle acquisition did not return a Parquet path")
    frame = pd.read_parquet(candles_path)
    frame, gap_fills = repair_candle_cadence(frame, start=args.start, end=args.end)
    cache = ParquetCache(Path(args.data_root) / "cache")
    installed = cache.save(
        cache_key(args.symbol, args.timeframe, int(duration_days)), frame
    )
    return str(installed.resolve()), gap_fills
