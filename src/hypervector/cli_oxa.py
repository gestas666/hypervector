"""Secret-safe bounded 0xArchive acquisition commands.

Argument parsing lives in the declarative command specs under
``hypervector/commands/specs``; this module only holds their handlers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from hypervector.data.oxa_api import OxaHistoryError
from hypervector.cli_oxa_candle_cache import (
    install_candle_cache as _install_candle_cache,
    validate_candle_cache_interval,
)


def acquisition_options(args: argparse.Namespace) -> dict[str, object]:
    """Return opt-in acquisition keywords present on the parsed command.

    ``allow_partial`` is forwarded only when explicitly requested, so a fetch
    never publishes an incomplete window unless the operator asked for the
    non-canonical ``_partial`` output.
    """
    if getattr(args, "allow_partial", False) is True:
        return {"allow_partial": True}
    return {}


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
            market_family=args.market_family,
        )
        report = acquire_and_store_orderbooks(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
            **acquisition_options(args),
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
            market_family=args.market_family,
        )
        report = acquire_and_store_trades(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
            **acquisition_options(args),
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
            market_family=args.market_family,
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
    """Acquire venue candles and optionally install an exact research cache.

    Cache-install preconditions are checked before any vendor call. An omitted
    ``max_pages`` (``None``) is derived from the window. When installation
    fails after a successful acquisition, the failure still reports the stored
    bundle so the operator can install offline on the next run.
    """
    from hypervector.data.oxa_candles import (
        OxaCandleRequest,
        acquire_and_store_candles,
        estimated_candle_pages,
    )

    try:
        if args.install_research_cache:
            validate_candle_cache_interval(args)
        request = OxaCandleRequest(
            args.symbol,
            args.start,
            args.end,
            args.timeframe,
            args.limit,
            1 if args.max_pages is None else args.max_pages,
            args.timeout,
            market_family=args.market_family,
        )
        if args.max_pages is None:
            request = replace(request, max_pages=estimated_candle_pages(request))
        report = acquire_and_store_candles(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
        )
    except (OxaHistoryError, ValueError, OSError) as exc:
        return _print_failure(exc)
    if args.install_research_cache:
        try:
            cache_path, gap_fills = _install_candle_cache(args, report)
        except (ValueError, OSError) as exc:
            return _print_failure(
                exc,
                research_cache_error=str(exc),
                acquisition={**report, "venue": "hyperliquid"},
            )
        report["research_cache_path"] = cache_path
        report["research_cache_gap_fills"] = gap_fills
        report["research_cache_hint"] = (
            "research commands refresh a cache older than a day; pass --pin-cache "
            "to run them on this installed window as is"
        )
    return _print_success(report)


def cmd_research_db_build(args: argparse.Namespace) -> int:
    """Verify and incrementally materialize an archive window in DuckDB.

    ``replace_changed`` applies bundles whose manifests changed after an
    explicit source repair (atomic per batch); ``verify_all`` re-checksums
    already-ingested bundles instead of trusting their manifest fingerprint.
    """
    import duckdb

    from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
    from hypervector.data.research_database import ResearchDatabase

    path = _research_database_path(args)
    replace_changed = getattr(args, "replace_changed", False) is True
    verify_all = getattr(args, "verify_all", False) is True
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
        if replace_changed:
            ingest = database.replace_changed_archive(config, verify_all=verify_all)
        else:
            ingest = database.ingest_archive(config, verify_all=verify_all)
        report: dict[str, object] = {
            "ok": True,
            "mode": "replace_changed" if replace_changed else "incremental",
            "verify_all": verify_all,
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
        Path(args.decisions)
        if args.decisions is not None
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


def _print_failure(exc: Exception, **context: object) -> int:
    print(json.dumps({"ok": False, "error": str(exc), **context}), file=sys.stderr)
    return 1


def _print_success(report: dict[str, object]) -> int:
    report["venue"] = "hyperliquid"
    print(json.dumps(report, indent=2))
    return 0
