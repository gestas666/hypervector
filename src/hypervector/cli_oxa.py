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
    """Register bounded venue evidence acquisition commands."""
    from hypervector.cli_hip3_research import add_hip3_research_parsers
    from hypervector.cli_research_journal import add_research_journal_parsers

    _add_archive_fetch_parsers(subparsers)
    _add_context_fetch_parsers(subparsers)
    _add_research_database_parsers(subparsers)
    add_hip3_research_parsers(subparsers)
    add_research_journal_parsers(subparsers)


def _add_archive_fetch_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register L2, trade, and price archive acquisition commands."""
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

    prices = subparsers.add_parser(
        "oxa-price-fetch",
        help="Fetch bounded Hyperliquid mark/oracle prices from 0xArchive",
    )
    _add_window_args(prices)
    prices.set_defaults(func=cmd_oxa_price_fetch)


def _add_context_fetch_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register funding and candle acquisition commands."""
    funding = subparsers.add_parser(
        "hl-funding-fetch",
        help="Fetch complete official Hyperliquid hourly funding history",
    )
    funding.add_argument("--symbol", default="BTC")
    funding.add_argument("--start", required=True, type=_parse_utc_datetime)
    funding.add_argument("--end", required=True, type=_parse_utc_datetime)
    funding.set_defaults(func=cmd_hl_funding_fetch)

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


def _add_research_database_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register DuckDB ingestion and comparison commands."""
    _add_research_ingest_parsers(subparsers)
    _add_research_report_parsers(subparsers)


def _add_research_ingest_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register DuckDB data-ingestion commands."""
    database = subparsers.add_parser(
        "research-db-build",
        help="Verify and incrementally load 0xArchive evidence into DuckDB",
    )
    database.add_argument("--symbol", default="BTC")
    database.add_argument("--start", required=True, type=_parse_utc_datetime)
    database.add_argument("--end", required=True, type=_parse_utc_datetime)
    database.add_argument("--depth", type=int, default=20, choices=range(1, 21))
    database.add_argument("--market-family", choices=("core", "hip3"), default="core")
    database.add_argument("--books-only", action="store_true")
    database.add_argument("--database", type=Path)
    database.set_defaults(func=cmd_research_db_build)

    live_events = subparsers.add_parser(
        "research-db-live-event-import",
        help="Import immutable live Hyperliquid event parts into DuckDB",
    )
    live_events.add_argument("--symbol", default="BTC")
    live_events.add_argument("--database", type=Path)
    live_events.set_defaults(func=cmd_research_db_live_event_import)

    shadow = subparsers.add_parser(
        "research-db-shadow-import",
        help="Import paper/shadow ledger evidence into DuckDB for analysis",
    )
    shadow.add_argument(
        "--ledger",
        type=Path,
        help="ledger path (default: <data-root>/paper/decisions/decisions.jsonl)",
    )
    shadow.add_argument("--database", type=Path)
    shadow.set_defaults(func=cmd_research_db_shadow_import)

    labels = subparsers.add_parser(
        "research-db-regime-label-import",
        help="Import source-pinned Hypertrader labels into DuckDB",
    )
    labels.add_argument("--labels", type=Path, required=True)
    labels.add_argument("--metadata", type=Path, required=True)
    labels.add_argument("--database", type=Path)
    labels.set_defaults(func=cmd_research_db_regime_label_import)


def _add_research_report_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register DuckDB read-only reporting commands."""
    from hypervector.cli_research_reports import (
        cmd_research_db_shadow_trades,
        cmd_research_db_status,
    )

    trades = subparsers.add_parser(
        "research-db-shadow-trades",
        help="Report completed shadow trades with causal entry regimes",
    )
    trades.add_argument("--database", type=Path)
    trades.set_defaults(func=cmd_research_db_shadow_trades)

    comparison = subparsers.add_parser(
        "research-db-regime-compare",
        help="Report backend versus strict/legacy regime annotations",
    )
    comparison.add_argument("--database", type=Path)
    comparison.set_defaults(func=cmd_research_db_regime_compare)

    status = subparsers.add_parser(
        "research-db-status",
        help="Report durable DuckDB research-market row counts",
    )
    status.add_argument("--database", type=Path)
    status.set_defaults(func=cmd_research_db_status)


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


def cmd_oxa_price_fetch(args: argparse.Namespace) -> int:
    """Acquire one explicitly bounded Hyperliquid price-context window."""
    from hypervector.data.oxa_prices import (
        OxaPriceRequest,
        acquire_and_store_prices,
    )

    try:
        request = OxaPriceRequest(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            limit=args.limit,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout,
        )
        report = acquire_and_store_prices(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
        )
    except (OxaHistoryError, ValueError, OSError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_hl_funding_fetch(args: argparse.Namespace) -> int:
    """Acquire one complete official Hyperliquid funding window."""
    from hypervector.data.hl_funding_archive import (
        HlFundingRequest,
        acquire_and_store_hl_funding,
    )

    try:
        request = HlFundingRequest(args.symbol, args.start, args.end)
        report = acquire_and_store_hl_funding(
            data_root=args.data_root,
            request=request,
        )
    except (RuntimeError, ValueError, OSError) as exc:
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


def cmd_research_db_build(args: argparse.Namespace) -> int:
    """Verify and incrementally materialize an archive window in DuckDB."""
    import duckdb

    from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
    from hypervector.data.research_database import ResearchDatabase

    path = _research_database_path(args)
    try:
        config = OxaArchiveAuditConfig(
            args.symbol,
            args.start,
            args.end,
            Path(args.data_root),
            depth=args.depth,
            market_family=args.market_family,
            book_only=args.books_only,
        )
        database = ResearchDatabase(path)
        ingest = database.ingest_archive(config)
        report: dict[str, object] = {
            "ok": True,
            "database_path": str(path.resolve()),
            "ingest": ingest.to_dict(),
            "summary": database.summary(),
        }
    except (duckdb.Error, OSError, ValueError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_research_db_shadow_import(args: argparse.Namespace) -> int:
    """Idempotently import no-submit backend observations into DuckDB."""
    import duckdb

    from hypervector.data.research_database import ResearchDatabase

    path = _research_database_path(args)
    ledger = (
        Path(args.ledger)
        if args.ledger is not None
        else Path(args.data_root) / "paper" / "decisions" / "decisions.jsonl"
    )
    try:
        database = ResearchDatabase(path)
        ingest = database.ingest_shadow_ledger(ledger)
        report: dict[str, object] = {
            "ok": True,
            "report_only": True,
            "execution_authority": "none",
            "database_path": str(path.resolve()),
            "ledger_path": str(ledger.resolve()),
            "ingest": ingest.to_dict(),
            "shadow_summary": database.shadow_summary(),
        }
    except (duckdb.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_research_db_live_event_import(args: argparse.Namespace) -> int:
    """Import public live-event evidence without creating order authority."""
    import duckdb

    from hypervector.data.research_database import ResearchDatabase

    path = _research_database_path(args)
    try:
        database = ResearchDatabase(path)
        ingest = database.ingest_live_event_archive(
            Path(args.data_root), str(args.symbol)
        )
        report: dict[str, object] = {
            "ok": True,
            "report_only": True,
            "execution_authority": "none",
            "database_path": str(path.resolve()),
            "ingest": ingest.to_dict(),
        }
    except (duckdb.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_research_db_regime_label_import(args: argparse.Namespace) -> int:
    """Import exact source labels with immutable annotation-only provenance."""
    import duckdb

    from hypervector.data.research_database import ResearchDatabase

    path = _research_database_path(args)
    try:
        database = ResearchDatabase(path)
        ingest = database.ingest_hypertrader_labels(
            Path(args.labels), Path(args.metadata)
        )
        report: dict[str, object] = {
            "ok": True,
            "report_only": True,
            "execution_authority": "none",
            "database_path": str(path.resolve()),
            "ingest": ingest.to_dict(),
        }
    except (duckdb.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def cmd_research_db_regime_compare(args: argparse.Namespace) -> int:
    """Report causal source-revision disagreement without execution gates."""
    import duckdb

    from hypervector.data.research_database import ResearchDatabase

    path = _research_database_path(args)
    if not path.is_file():
        return _print_failure(
            FileNotFoundError(f"research database is missing: {path}")
        )
    try:
        report = {
            "ok": True,
            "database_path": str(path.resolve()),
            **ResearchDatabase(path).regime_comparison_summary(),
        }
    except (duckdb.Error, OSError, ValueError) as exc:
        return _print_failure(exc)
    return _print_success(report)


def _research_database_path(args: argparse.Namespace) -> Path:
    from hypervector.infra import paths_for

    if args.database is not None:
        return Path(args.database)
    return paths_for(args.data_root).research_db


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
