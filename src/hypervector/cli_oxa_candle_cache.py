"""Explicit one-minute research-cache installation for acquired candles."""

from __future__ import annotations

import argparse
from pathlib import Path


def validate_candle_cache_interval(args: argparse.Namespace) -> None:
    """Reject cache requests the continuity repair cannot install.

    Runs before acquisition so an unsupported interval or a partial-day window
    never spends vendor calls or publishes a bundle the cache cannot use.
    """
    if args.timeframe != "1m":
        raise ValueError(
            "research cache installation requires --timeframe 1m; "
            "omit --install-research-cache to acquire other candle intervals"
        )
    if not _whole_day_count(args).is_integer():
        raise ValueError(
            "research cache installation requires a whole-day window; "
            "omit --install-research-cache to acquire a partial-day window"
        )


# Footer origin of an installed archive window. It is not the research
# loader's own origin, so a network-enabled default load still keeps the file
# aside (``__preserved_*``) before refreshing; research commands serve it as is
# with --pin-cache.
INSTALL_ORIGIN = "oxa_install"


def install_candle_cache(
    args: argparse.Namespace, report: dict[str, object]
) -> tuple[str, int]:
    """Install a whole-day minute cache with explicitly labeled gap fills.

    The file's footer records where the window came from (bundle, exact
    start/end, install time, gap fills), so the provenance survives in the
    cache and in any preserved copy.
    """
    from datetime import UTC, datetime

    import pandas as pd

    from hypervector.data.cache import ParquetCache
    from hypervector.data.oxa_candles import repair_candle_cadence
    from hypervector.data.pipeline import cache_key

    validate_candle_cache_interval(args)
    duration_days = _whole_day_count(args)
    candles_path = report.get("candles_path")
    if not isinstance(candles_path, str):
        raise ValueError("candle acquisition did not return a Parquet path")
    frame = pd.read_parquet(candles_path)
    frame, gap_fills = repair_candle_cadence(frame, start=args.start, end=args.end)
    cache = ParquetCache(Path(args.data_root) / "cache")
    installed = cache.save(
        cache_key(args.symbol, args.timeframe, int(duration_days)),
        frame,
        metadata={
            "origin": INSTALL_ORIGIN,
            "source": "0xarchive_hyperliquid_candles",
            "symbol": str(args.symbol),
            "timeframe": str(args.timeframe),
            "window_start": args.start.isoformat(),
            "window_end": args.end.isoformat(),
            "installed_at": datetime.now(UTC).isoformat(),
            "gap_fills": int(gap_fills),
            "bundle": candles_path,
        },
    )
    return str(installed.resolve()), gap_fills


def _whole_day_count(args: argparse.Namespace) -> float:
    return (args.end - args.start).total_seconds() / 86_400
