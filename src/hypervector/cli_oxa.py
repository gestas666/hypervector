"""Secret-safe bounded 0xArchive acquisition commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from hypervector.data.oxa_api import OxaHistoryError


def add_oxa_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register bounded book, trade, and candle acquisition commands."""
    book = subparsers.add_parser(
        "oxa-book-fetch",
        help="Fetch bounded Hyperliquid-native L2 history from 0xArchive",
    )
    _add_window_args(book)
    book.add_argument("--depth", type=int, default=20, choices=range(1, 21))
    book.set_defaults(func=cmd_oxa_book_fetch)

    trades = subparsers.add_parser(
        "oxa-trade-fetch",
        help="Fetch bounded Hyperliquid public trades from 0xArchive",
    )
    _add_window_args(trades)
    trades.set_defaults(func=cmd_oxa_trade_fetch)

    candles = subparsers.add_parser(
        "oxa-candle-fetch",
        help="Fetch bounded Hyperliquid-native OHLCV candles from 0xArchive",
    )
    candles.add_argument("--symbol", default="BTC")
    candles.add_argument("--start", required=True, type=_parse_utc_datetime)
    candles.add_argument("--end", required=True, type=_parse_utc_datetime)
    candles.add_argument(
        "--interval",
        default="1m",
        choices=("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"),
    )
    candles.add_argument("--limit", type=int, default=10_000)
    candles.add_argument("--max-pages", type=int, default=20)
    candles.add_argument("--timeout", type=float, default=30.0)
    candles.add_argument("--install-research-cache", action="store_true")
    candles.set_defaults(func=cmd_oxa_candle_fetch)


def cmd_oxa_book_fetch(args: argparse.Namespace) -> int:
    """Acquire one explicitly bounded Hyperliquid-native L2 window."""
    from hypervector.data.oxa_history import (
        OxaBookRequest,
        acquire_and_store_orderbooks,
    )

    try:
        request = OxaBookRequest(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            depth=args.depth,
            limit=args.limit,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout,
        )
        report = acquire_and_store_orderbooks(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
        )
    except (OxaHistoryError, ValueError, OSError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_oxa_trade_fetch(args: argparse.Namespace) -> int:
    """Acquire one explicitly bounded Hyperliquid public-trade window."""
    from hypervector.data.oxa_trades import (
        OxaTradeRequest,
        acquire_and_store_trades,
    )

    try:
        request = OxaTradeRequest(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            limit=args.limit,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout,
        )
        report = acquire_and_store_trades(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
        )
    except (OxaHistoryError, ValueError, OSError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_oxa_candle_fetch(args: argparse.Namespace) -> int:
    """Acquire venue candles and optionally install an exact research cache."""
    from hypervector.data.oxa_candles import (
        OxaCandleRequest,
        acquire_and_store_candles,
    )

    try:
        request = OxaCandleRequest(
            args.symbol,
            args.start,
            args.end,
            args.interval,
            args.limit,
            args.max_pages,
            args.timeout,
        )
        report = acquire_and_store_candles(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
        )
        if args.install_research_cache:
            cache_path, gap_fills = _install_candle_cache(args, report)
            report["research_cache_path"] = cache_path
            report["research_cache_gap_fills"] = gap_fills
    except (OxaHistoryError, ValueError, OSError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def _install_candle_cache(
    args: argparse.Namespace, report: dict[str, object]
) -> tuple[str, int]:
    import pandas as pd

    from hypervector.data.cache import ParquetCache
    from hypervector.data.oxa_candles import repair_candle_cadence
    from hypervector.data.pipeline import cache_key

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
        cache_key(args.symbol, args.interval, int(duration_days)), frame
    )
    return str(installed.resolve()), gap_fills


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", default="BTC", help="Hyperliquid core asset")
    parser.add_argument("--start", required=True, type=_parse_utc_datetime)
    parser.add_argument("--end", required=True, type=_parse_utc_datetime)
    parser.add_argument("--limit", type=_bounded_page_limit, default=1000)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)


def _bounded_page_limit(value: str) -> int:
    limit = int(value)
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 1000")
    return limit


def _parse_utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid ISO-8601 timestamp: {value}"
        ) from exc
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset or Z")
    return parsed.astimezone(UTC)


def _print_failure(exc: Exception) -> int:
    print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
    return 1


def _print_success(report: dict[str, object]) -> int:
    report["venue"] = "hyperliquid"
    print(json.dumps(report, indent=2))
    return 0
